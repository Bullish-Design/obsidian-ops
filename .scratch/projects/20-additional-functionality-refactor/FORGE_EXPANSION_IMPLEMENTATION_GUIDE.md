# FORGE_EXPANSION_IMPLEMENTATION_GUIDE.md

## Audience

This guide is written for an engineer implementing the Forge-side changes
described in `FORGE_EXPANSION_CONCEPT.md`. It covers **only** the changes
that land in the Forge repository (this repo). Backend changes are covered
by sibling documents:

- `OBSIDIAN_OPS_EXPANSION_IMPLEMENTATION_GUIDE.md` (obsidian-ops library)
- `OBSIDIAN_AGENT_EXPANSION_IMPLEMENTATION_GUIDE.md` (obsidian-agent service)

## Ground rules

1. Follow the phases in order. Phase 0 is a pure refactor that unblocks
   every later phase; do not skip it.
2. Every step has an explicit test gate. Do not start the next step until
   the current one is green.
3. Do not add or modify files under `internal/ops/`. That package is
   deprecated. Leave it alone.
4. All runtime behavior flows through `/api/*` proxied to obsidian-agent.
   Forge must not grow its own mutation endpoints.
5. The source of truth for overlay frontend source files is
   `static/src/`. `static/ops.js` becomes a bundler output file.

## Prerequisites before starting

- Latest `main` builds and the full Go test suite is green (`go test ./...`).
  If it is not, fix the known failing tests first — new work must not be
  stacked on a red baseline.
- A working obsidian-agent backend is running locally or reachable over
  the Tailscale network for any end-to-end test step.
- Node.js 20+ installed (for the overlay bundler introduced in Phase 0).
- `templ` CLI installed (`go install github.com/a-h/templ/cmd/templ@latest`)
  for regenerating `shared_templ.go` in step 0.1.

---

# Phase 0 — Overlay modularization

Goal: Split `static/ops.js` into an ES module tree with a small bundler
step, and extend the meta-tag contract so the overlay has all the context
it needs. Ships no user-visible change.

## Step 0.1 — Extend the page context meta tags

**Why.** The overlay needs the rendered site URL and the configured base
URL to implement the editor, scope, and new-page modes without parsing
`window.location` conventions inside JS. Keeping this on the server side
preserves the "Forge renders, overlay reads" boundary.

**Files.**
- `internal/templates/shared.templ`
- `internal/templates/shared_templ.go` (regenerated)

**Change.** Inside the `if !data.IsFolder` branch, below the existing
`forge-current-file` emission at line 227–229, add two new meta tags:

```templ
if data.File.RelPath != "" {
    <meta name="forge-current-file" content={ data.File.RelPath }/>
    <meta name="forge-current-url" content={ data.File.WebPath }/>
}
<meta name="forge-site-base-url" content={ data.Site.BaseURL }/>
<meta name="forge-flat-urls" content={ flatURLsMeta(data.Site.FlatURLs) }/>
```

Add a tiny helper in `shared.templ` (or an existing helpers file) that
returns `"true"` or `"false"`:

```go
func flatURLsMeta(v bool) string {
    if v {
        return "true"
    }
    return "false"
}
```

Regenerate:

```bash
templ generate ./internal/templates
```

**Testing.**

1. Build: `go build ./...`
2. Unit: add a test in `internal/templates/shared_templ_test.go`
   (create if needed) that renders a page with a known `RelPath`,
   `WebPath`, `BaseURL`, and `FlatURLs`, then asserts all four meta tags
   appear exactly once each in the output.
3. Run: `go test ./internal/templates/...`
4. Smoke: `go run ./cmd/forge dev --input ./vault --output ./public
   --overlay-dir ./static --inject-overlay` and verify in the browser
   that `view-source` on a rendered page contains the four tags.

## Step 0.2 — Add the overlay bundler toolchain

**Why.** We are about to split `static/ops.js` into an ES module tree.
esbuild gives us a single-file bundled output with zero config. No new
runtime dependency — the output file is still a single `static/ops.js`
served by the existing overlay handler.

**Files.**
- `package.json`
- `.gitignore` (no change — `static/ops.js` stays checked in)

**Change.** Update `package.json` to add esbuild as a devDependency and a
build script:

```json
{
  "scripts": {
    "build:ops": "esbuild static/src/main.js --bundle --format=iife --target=es2020 --outfile=static/ops.js --legal-comments=none",
    "build:ops:watch": "esbuild static/src/main.js --bundle --format=iife --target=es2020 --outfile=static/ops.js --watch",
    "check:ops": "node ./scripts/check-ops-bundle.mjs"
  },
  "devDependencies": {
    "esbuild": "^0.24.0",
    "prettier": "^3.7.4",
    "prettier-plugin-go-template": "^0.0.15"
  }
}
```

Run:

```bash
npm install
```

Commit `package-lock.json`.

**Testing.**

1. `npm run build:ops` must fail with a clear "no entry point" error
   (expected — we have not created `static/src/main.js` yet).
2. `node_modules/.bin/esbuild --version` should print a version.
3. `git status` should show only `package.json` and `package-lock.json`
   as changed.

## Step 0.3 — Create the overlay module skeleton

**Why.** Establish the module tree before migrating any behavior. Every
new file in this step is an empty-but-wired stub so Phase 1+ can drop
features in without restructuring.

**Files.** Create:

```
static/src/
├── main.js
├── api.js
├── page-context.js
├── fab.js
├── state.js
├── ui/
│   ├── modal.js
│   ├── sheet.js
│   └── toast.js
└── modes/
    └── command-mode.js
```

**Contents.** Each file should export one named symbol and log a debug
message when loaded. Example:

```js
// static/src/main.js
import { installFab } from "./fab.js";
import { createState } from "./state.js";

export function bootOverlay() {
  const state = createState();
  installFab(state);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootOverlay);
} else {
  bootOverlay();
}
```

```js
// static/src/state.js
export function createState() {
  return {
    mode: "reading",   // reading|commanding|editing|scoping|templating|running
    running: false,
    currentFile: null,
    currentUrl: null,
  };
}
```

```js
// static/src/page-context.js
export function readPageContext() {
  const meta = (name) =>
    document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") ?? null;
  return {
    currentFile: meta("forge-current-file"),
    currentUrl: meta("forge-current-url"),
    siteBaseUrl: meta("forge-site-base-url"),
    flatUrls: meta("forge-flat-urls") === "true",
  };
}
```

Stub `api.js`, `fab.js`, `ui/*.js`, and `modes/command-mode.js` with
empty exports so `main.js` compiles but has no real behavior yet.

**Testing.**

1. `npm run build:ops` now completes. Inspect `static/ops.js` and verify
   it contains an IIFE with `bootOverlay`.
2. Add a tiny test script `scripts/check-ops-bundle.mjs` that reads
   `static/ops.js`, asserts `bootOverlay` is present, and exits 0.
   Wire it into `npm run check:ops`.
3. `npm run check:ops` must pass.
4. Start dev server and verify no JavaScript errors appear in the
   browser console (the overlay is now non-functional but does not
   crash).

## Step 0.4 — Port the existing command modal into `modes/command-mode.js`

**Why.** Behavior parity with the pre-refactor overlay. After this step
the user-visible surface is identical to today's `static/ops.js`, but the
source tree is modular.

**Files.**
- `static/src/modes/command-mode.js`
- `static/src/fab.js`
- `static/src/api.js`
- `static/src/ui/modal.js`

**Change.**

`api.js` centralizes every `fetch` call with a shared response parser.
Move the `parseApiResponse` logic from today's `ops.js` into a named
export:

```js
// static/src/api.js
export async function postApply(payload) { /* ... */ }
export async function postUndo() { /* ... */ }
export async function parseApiResponse(resp, ctx) { /* migrated */ }
```

`modes/command-mode.js` owns the instruction modal: build the DOM,
handle submit/undo/refresh, transition `state.mode` between
`reading` and `commanding` and `running`.

`fab.js` creates the floating button and wires its click to transition
into command mode.

`main.js` loads `command-mode.js` eagerly (it is the default behavior).
Later modes will be lazy-imported.

Delete the logic from the old `static/ops.js` — since Phase 0.3 made it
a generated file, it will be regenerated by the bundler on the next
`npm run build:ops`.

**Testing.**

1. `npm run build:ops` must succeed.
2. `npm run check:ops` must pass.
3. Unit tests for `api.js` using `vitest` or a standalone Node test
   runner. Create `static/src/__tests__/api.test.js` that asserts:
   - `parseApiResponse` returns `{ ok: false, error }` on a 500.
   - `parseApiResponse` returns parsed JSON on a 200 with a JSON body.
   - `parseApiResponse` returns `{ ok: false, error }` on a 200 with a
     non-JSON body.
4. Add `"test:ops": "node --test static/src/__tests__/*.test.js"` to
   `package.json` scripts.
5. End-to-end smoke: run `forge dev` against a demo vault with
   obsidian-agent running, click the FAB, submit a trivial instruction,
   confirm the modal transitions identically to the pre-refactor version.
6. `go test ./...` must still be green (no Go changes in this step).

## Step 0.5 — Add a CI gate that keeps the bundle in sync

**Why.** Forge's overlay handler serves `static/ops.js` directly. If the
committed bundle drifts from the source tree, production serves stale
code. A simple check prevents that class of bug.

**Files.**
- `scripts/check-ops-bundle.mjs`
- CI workflow file under `.github/workflows/`

**Change.** `scripts/check-ops-bundle.mjs` should:

1. Run the esbuild command in-process to produce a temporary build.
2. Read `static/ops.js`.
3. Compare SHA-256. On mismatch, print a diff hint and exit 1.

Add a GitHub Actions workflow `.github/workflows/overlay-check.yml`:

```yaml
name: overlay-check
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci
      - run: npm run check:ops
      - run: npm run test:ops
```

**Testing.**

1. Run `npm run check:ops` locally — must pass on a clean checkout.
2. Make a trivial edit to `static/src/main.js` without rebuilding and
   run `npm run check:ops` — must fail with the drift message.
3. Run `npm run build:ops` to regenerate and re-run `check:ops` —
   must pass again.
4. Open a throwaway PR to verify the GitHub Actions workflow runs and
   reports green.

## Step 0.6 — Turn off the always-on debug log

**Why.** `OPS_DEBUG = true` is convenient during development but is
noisy in production and muddles issue reports. Make it env-driven.

**Files.** `static/src/main.js` and any module that calls `debugLog`.

**Change.** Introduce a shared `logger.js`:

```js
// static/src/logger.js
const FLAG = document
  .querySelector('meta[name="forge-overlay-debug"]')
  ?.getAttribute("content") === "true";
export function debugLog(level, msg, details) {
  if (!FLAG) return;
  if (details !== undefined) console[level](`[ops-ui] ${msg}`, details);
  else console[level](`[ops-ui] ${msg}`);
}
```

Add an opt-in meta tag emission in `shared.templ` only when an
environment-driven builder flag is set. Default: off.

**Testing.**

1. Build with the debug flag off — confirm the browser console is
   silent during overlay use.
2. Build with the debug flag on — confirm the expected trace appears.
3. `npm run check:ops` must still pass.

---

# Phase 1 — Full-screen CodeMirror editor mode

Goal: Ship Feature 1 (deterministic source editing). No agent changes.
Depends on obsidian-agent exposing `/api/vault/files` (see the sibling
guide steps for `/api/vault/files` GET + PUT).

## Step 1.1 — Add typed API wrappers for `/api/vault/*`

**Files.**
- `static/src/api.js`

**Change.** Add:

```js
export async function getSource({ path, url }) {
  const q = new URLSearchParams();
  if (path) q.set("path", path);
  else if (url) q.set("url", url);
  const resp = await fetch(`/api/vault/files?${q}`);
  return parseApiResponse(resp, "getSource");
}

export async function putSource({ path, content, expectedSha256 }) {
  const resp = await fetch(`/api/vault/files`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content, expected_sha256: expectedSha256 }),
  });
  return parseApiResponse(resp, "putSource");
}

export async function postVaultUndo() {
  const resp = await fetch(`/api/vault/undo`, { method: "POST" });
  return parseApiResponse(resp, "vaultUndo");
}
```

**Testing.**

1. Unit tests in `static/src/__tests__/api.test.js`:
   - `getSource` with both `path` and `url` builds the right query
     string (mock `fetch`).
   - `putSource` sends the expected JSON body.
2. `npm run test:ops` must pass.
3. Point the dev environment at a running obsidian-agent and run
   the test interactively from the browser console:
   `await window.forgeApi.getSource({ path: "Projects/Example.md" })`.
   (Temporarily attach `forgeApi` to `window` for manual verification;
   remove before commit.)

## Step 1.2 — Add CodeMirror 6 as a bundled dependency

**Files.**
- `package.json`
- `static/src/lib/codemirror.js`

**Change.** Install CodeMirror 6:

```bash
npm install --save codemirror @codemirror/lang-markdown @codemirror/state @codemirror/view @codemirror/commands @codemirror/search
```

Create a thin re-export module so the rest of the codebase only imports
from `./lib/codemirror.js`:

```js
// static/src/lib/codemirror.js
export { EditorState } from "@codemirror/state";
export { EditorView, keymap, lineNumbers, highlightActiveLine } from "@codemirror/view";
export { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
export { markdown } from "@codemirror/lang-markdown";
export { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
```

**Testing.**

1. `npm run build:ops` — must succeed. Inspect the resulting
   `static/ops.js` size. Expect it to grow substantially (≈150 KB).
2. `npm run check:ops` must pass.
3. Temporary smoke: import from `main.js` and call `new EditorView`
   against a hidden DOM node to confirm the bundle works in-browser.
   Remove the smoke code after verification.

## Step 1.3 — Implement `modes/editor-mode.js`

**Files.**
- `static/src/modes/editor-mode.js`
- `static/src/ui/editor-shell.js` (DOM construction helper)
- `static/ops.css` (new rules)

**Change.** The editor mode owns:

1. Mounting a full-screen container over the page with a sticky mobile
   toolbar: Back, Save, Undo, Ask AI, Scope, New.
2. Calling `getSource` on entry, showing a small loading state.
3. Creating a CodeMirror 6 `EditorView` with the markdown language,
   history, search, and line wrapping.
4. Tracking dirty state via an `updateListener`.
5. On Save, calling `putSource` with the original `sha256` as
   `expectedSha256`.
6. On 409 Conflict, presenting a dialog with "Reload remote",
   "Overwrite", and "Cancel".
7. On success, remaining in editor mode with the new `sha256` so the
   user can keep editing without another fetch.
8. Exiting editor mode cleanly (tear down CM view, remove container,
   return state to `reading`).

Style rules in `ops.css`:

```css
#ops-editor-root {
  position: fixed;
  inset: 0;
  background: var(--ops-bg);
  z-index: 10002;
  display: flex;
  flex-direction: column;
}
#ops-editor-toolbar {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  position: sticky;
  top: 0;
  background: var(--ops-bg);
  border-bottom: 1px solid #e2e8f0;
}
#ops-editor-cm { flex: 1; overflow: auto; }
@media (max-width: 640px) {
  #ops-editor-toolbar button { min-height: 44px; min-width: 44px; }
}
```

**Testing.**

1. `npm run build:ops` and `npm run check:ops`.
2. Unit test in `static/src/__tests__/editor-mode.test.js`: instantiate
   the module against a `jsdom` document, stub `getSource`/`putSource`,
   and assert:
   - Entering the mode calls `getSource` exactly once.
   - Typing into the view flips dirty state.
   - Saving calls `putSource` with the original sha and updates the
     stored sha on success.
   - A 409 response triggers the conflict resolution dialog.
3. Manual end-to-end with a running agent:
   a. Open any rendered page, tap FAB → "Edit".
   b. Confirm the full markdown appears.
   c. Edit, tap Save, confirm the summary updates.
   d. Refresh and verify the rendered page reflects the edit.
   e. In another shell, edit the vault file directly. In the browser,
      tap Save to force a conflict. Confirm the dialog appears.
4. Mobile check (Chrome DevTools → device toolbar → iPhone 14): confirm
   the toolbar does not overlap the keyboard, Save/Discard targets are
   at least 44×44 px, and there is no horizontal scroll.

## Step 1.4 — Wire the editor entry point into the FAB

**Files.**
- `static/src/fab.js`
- `static/src/modes/command-mode.js`

**Change.** The FAB should expose two entry points: the existing command
modal (the default tap) and an "Edit" action. On touch devices, a small
edit icon next to the FAB is the cleanest affordance; on desktop, a
secondary button works. Tapping "Edit" dynamically imports
`./modes/editor-mode.js` and calls its `enterEditorMode(state)` export.

```js
// static/src/fab.js
import { readPageContext } from "./page-context.js";

export function installFab(state) {
  // existing FAB...
  const editBtn = document.createElement("button");
  editBtn.id = "ops-fab-edit";
  editBtn.textContent = "edit";
  editBtn.addEventListener("click", async () => {
    const { enterEditorMode } = await import("./modes/editor-mode.js");
    const ctx = readPageContext();
    enterEditorMode(state, ctx);
  });
  document.body.appendChild(editBtn);
}
```

**Testing.**

1. `npm run build:ops` — verify that the editor module is still a
   separate chunk when you add `--splitting` and `--format=esm`. Since
   we are shipping IIFE, it will remain inlined; that's acceptable.
   Confirm the bundle size is sensible.
2. Smoke: click the Edit button, confirm the editor opens; click Back,
   confirm you land on the rendered page with no console errors.
3. Accessibility: focus traversal enters the editor toolbar first, not
   mid-textarea. Add `autofocus` deliberately on the CM view after a
   short timeout so VoiceOver and NVDA announce the toolbar.

## Step 1.5 — Handle reload after save

**Why.** After saving, Forge's file watcher sees the vault write and
triggers an incremental rebuild. The editor needs a way to ask the user
to reload, or reload automatically if the SSE event stream from
Phase 4 is available.

**Files.** `static/src/modes/editor-mode.js`.

**Change.** On successful save, show a non-modal toast with a "Reload
page" button. Keep the editor open so mobile users can stay in flow.
If the user taps Reload, call `window.location.reload()`.

**Testing.**

1. Save a change, confirm the toast appears, tap Reload, confirm the
   rendered page reflects the change.
2. Save without reloading and re-save a second time — the second save
   should succeed because the editor kept the updated sha256 from the
   first save response.

## Step 1.6 — Phase 1 exit gate

**Before moving on, all of the following must hold:**

- `go test ./...` passes.
- `go vet ./...` passes.
- `npm run build:ops`, `npm run check:ops`, `npm run test:ops` all pass.
- End-to-end smoke: open → edit → save → reload round trip works on
  both desktop and mobile viewport.
- The pre-existing command modal still works.
- No console warnings or errors during idle page views.

---

# Phase 2 — Section / block / selection scope UI

Goal: Ship Feature 2 (precise LLM targeting). Depends on
`/api/vault/files/structure`, `/api/vault/files/anchors`, and the
extended `/api/agent/apply` contract from the sibling guide.

## Step 2.1 — Extend `api.js` with structure, anchors, and scoped apply

**Files.** `static/src/api.js`.

**Change.**

```js
export async function getStructure({ path }) { /* GET /api/vault/files/structure */ }
export async function postEnsureAnchor({ path, lineStart, lineEnd }) {
  /* POST /api/vault/files/anchors */
}
export async function postAgentApply({ instruction, interfaceId, scope, intent, allowedWriteScope }) {
  /* POST /api/agent/apply */
}
```

The legacy `postApply` that targets `/api/apply` remains as a thin
alias that calls `postAgentApply` with `interfaceId: "command"` and no
scope. Mark it deprecated in a comment and plan to remove it after the
agent-side legacy shim is retired.

**Testing.**

1. Unit tests: mock `fetch`, verify query strings, bodies, and headers.
2. Manual: with agent running, call `await window.forgeApi.getStructure({
   path: "Projects/Example.md" })` in the browser and confirm a
   `StructureView` shape.

## Step 2.2 — Introduce `modes/scope-mode.js` and the DOM targeting layer

**Files.**
- `static/src/modes/scope-mode.js`
- `static/src/targeting/dom-map.js`

**Change.** `dom-map.js` is a pure helper that walks the rendered DOM
and annotates headings, paragraphs, list items, and callouts with:

- their inferred markdown source line range (based on the
  `StructureView` response)
- a stable `data-forge-anchor` attribute if one is already present

`scope-mode.js`:

1. On entry, calls `getStructure` for the current page and caches it.
2. Injects a small gutter chip next to every heading, paragraph, and
   list item it can map.
3. On long-press or tap-and-hold, opens a bottom sheet (use
   `ui/sheet.js`) with: "Rewrite with AI", "Summarize", "Ask about
   this", "Pin to scope", "Create anchor".
4. Maintains a `pinned: EditScope[]` array in the shared state.

The module should degrade gracefully if `getStructure` fails (e.g.,
for non-markdown pages): swallow the error and do not inject chips.

**Testing.**

1. Unit test `dom-map.js` against a synthetic `jsdom` document with
   known headings, asserting every heading gets the expected line
   range.
2. Manual: visit a rendered note with multiple headings and list items,
   confirm chips appear next to each, long-press one, confirm the sheet
   opens.
3. Verify the chip overlay does not shift the original layout (use
   absolute positioning anchored to each element).

## Step 2.3 — Pinned-scope bar and multi-select

**Files.** `static/src/modes/scope-mode.js`, `static/src/ui/scope-bar.js`.

**Change.** When `pinned.length > 0`, render a sticky scope bar at the
top of the viewport with:

- Count chip ("1 heading", "3 blocks", "1 heading + 2 blocks")
- "Ask AI" primary button (opens command mode with the scope attached)
- "Clear" secondary button

Multi-scope sends a `MultiScope` request (see the agent guide for the
exact shape).

**Testing.**

1. Manual: pin one heading, confirm the bar appears, tap Clear, confirm
   it disappears. Pin two different blocks, confirm count updates.
2. Unit test: mount scope bar with fixtures of 0, 1, and 3 scopes and
   assert the rendered text.

## Step 2.4 — Wire scoped commands through command mode

**Files.** `static/src/modes/command-mode.js`, `static/src/modes/scope-mode.js`.

**Change.** When command mode is entered from a scope action, the state
carries the scope. The submit handler calls `postAgentApply` with
`interfaceId: "forge_web"` and the appropriate `scope` value. After a
successful response the overlay returns to reading mode and reloads if
`updated` is true.

**Testing.**

1. Manual: pin a heading named "## Roadmap" on a demo page. Tap "Ask
   AI", type "Rewrite as two bullet points", submit. Confirm the agent
   returns and the rebuilt page shows only the Roadmap section changed.
2. Regression: confirm that tapping the FAB directly (not from a scope
   action) still sends an unscoped command with `interfaceId:
   "command"`.

## Step 2.5 — Anchor-ensure UX

**Files.** `static/src/modes/scope-mode.js`.

**Change.** In the action sheet, the "Create anchor" action calls
`postEnsureAnchor` for the long-pressed block and, on success, swaps
the pinned scope from a selection scope to a block scope using the
returned `block_id`. This upgrades brittle text-based targeting into
durable structural targeting.

**Testing.**

1. Manual: long-press a paragraph that has no `^block-id`. Tap "Create
   anchor". Confirm a toast reports the new anchor. View the markdown
   source (via editor mode) and confirm `^forge-xxx` was appended.
2. Re-run a scoped edit against that block. Confirm the edit lands in
   the right paragraph even after intervening edits.

## Step 2.6 — Phase 2 exit gate

- Structure API works for every renderable markdown page.
- Chips render non-destructively on all kinds of content (headings,
  paragraphs, list items, callouts).
- Multi-scope edits round-trip end-to-end.
- `go test ./...`, `go vet ./...`, `npm run check:ops`,
  `npm run test:ops` all pass.

---

# Phase 3 — Template-based new page creation

Goal: Ship Feature 3. Depends on `/api/vault/pages/templates` and
`/api/vault/pages` from the sibling guide.

## Step 3.1 — Add API wrappers

**Files.** `static/src/api.js`.

**Change.**

```js
export async function getTemplates() { /* GET /api/vault/pages/templates */ }
export async function createPage({ id, fields, parent }) {
  /* POST /api/vault/pages */
}
```

**Testing.** Unit tests with mocked fetch.

## Step 3.2 — Implement `modes/new-page-mode.js`

**Files.**
- `static/src/modes/new-page-mode.js`
- `static/src/ui/form.js` (shared form field primitives: text, select, textarea)

**Change.** On entry:

1. Call `getTemplates()` (cache for the session).
2. Render a bottom sheet on mobile or a centered modal on desktop
   with a template picker and a dynamic form for the chosen template's
   declared `fields`.
3. On submit, call `createPage`. On success, navigate to the returned
   `url`.

**Testing.**

1. Unit test: render with a fixture template list, choose each option,
   confirm the form fields update and that missing required fields
   block submission.
2. Manual: tap New, pick Project, enter a title, submit. Confirm the
   browser lands on the newly-created rendered page.

## Step 3.3 — Contextual quick-create from the current page

**Why.** Inline "New task from this project" actions are high value
and cheap once template creation works.

**Files.** `static/src/modes/new-page-mode.js`.

**Change.** When new-page mode is opened from a scope action (e.g., a
paragraph is pinned), pass the pinned content and current file as
`context` fields: `source_page`, `selection`. The template body can
reference these via `{{ context.source_page }}`.

**Testing.**

1. Manual: pin a paragraph, tap "Create task from selection", confirm
   the task note is created with a backlink to the source page.
2. Confirm the selection text appears in the new note body per the
   template.

## Step 3.4 — Phase 3 exit gate

- New-page mode round-trips from tap → fill → create → navigate.
- Contextual creation preserves the source file reference.
- No regression in editor mode, scope mode, or command mode.
- All test gates pass.

---

# Phase 4 — Polish (optional but recommended)

## Step 4.1 — Add an SSE rebuild event stream

**Why.** Today the editor has to prompt the user to reload after save.
If Forge emits a rebuild event, the editor can react automatically.

**Files.**
- `internal/overlay/events.go` (new)
- `internal/watch/watcher.go` (add a rebuild callback hook)
- `internal/cli/dev.go` (wire the events handler into `ForgeConfig`)
- `internal/server/mux.go` (route `/ops/events` to the events handler)

**Change.** `events.go` implements a minimal broadcast SSE endpoint:

```go
type Broker struct {
    mu     sync.Mutex
    subs   map[chan []byte]struct{}
}
func (b *Broker) Publish(payload []byte) { /* fan-out */ }
func (b *Broker) Handler() http.Handler { /* SSE writer */ }
```

In `dev.go`, after a successful `IncrementalBuild`, call
`broker.Publish([]byte(`{"type":"rebuilt"}`))`. Hang the broker off
`ForgeConfig` and surface it to `mux.go` as a new route
`/ops/events`.

**Testing.**

1. New Go test in `internal/overlay/events_test.go`:
   - Subscribe via the handler.
   - Call `Publish`.
   - Assert the subscribed channel receives the event within 100 ms.
   - Test cleanup on client disconnect.
2. Manual: open a rendered page and run `curl -N
   http://localhost:8080/ops/events`. Edit a file in the vault; confirm
   the curl output shows a `data: {"type":"rebuilt"}` line.

## Step 4.2 — Overlay subscribes to `/ops/events`

**Files.** `static/src/events.js` (new), `static/src/main.js`.

**Change.** `events.js` opens an `EventSource` to `/ops/events` and
exposes an emitter. `main.js` wires rebuild events to an overlay-level
callback that:

- In reading mode: silently reloads the page if the current path
  matches.
- In editor mode: shows a non-modal "Vault rebuilt" toast.

**Testing.**

1. Unit test `events.js` with a mocked `EventSource`, asserting
   handlers fire on `message` events.
2. Manual: open a page, edit the underlying markdown externally,
   confirm the page reloads automatically within ~1 second.

## Step 4.3 — LocalStorage draft autosave for editor mode

**Files.** `static/src/modes/editor-mode.js`.

**Change.** Throttle draft writes to `localStorage` keyed by
`path:sha256`. On entry, check for a matching draft that is newer than
the fetched `modified_at` and offer to restore it.

**Testing.**

1. Manual: edit, switch tabs, kill the browser, reopen, confirm the
   draft restore prompt appears.
2. Verify that saving clears the draft entry.

---

# Global test matrix

Run these before every commit on this project and in CI for every PR:

| Gate                         | Command                                      |
|-----------------------------|----------------------------------------------|
| Go build                    | `go build ./...`                             |
| Go vet                      | `go vet ./...`                               |
| Go tests                    | `go test ./...`                              |
| Templ up-to-date            | `templ generate ./internal/templates && git diff --exit-code` |
| Overlay bundle up-to-date   | `npm run check:ops`                          |
| Overlay unit tests          | `npm run test:ops`                           |
| Prettier                    | `npx prettier --check static/src`            |

Merges into `main` also run an end-to-end smoke using
`demo/run_demo.sh` that exercises command, editor, scope, and new-page
flows against a local obsidian-agent container.

---

# Rollout sequence summary

```
Phase 0 — Overlay modularization (no UX change)
  0.1 meta tags
  0.2 bundler
  0.3 module skeleton
  0.4 port command modal
  0.5 CI drift gate
  0.6 debug log opt-in

Phase 1 — Editor mode
  1.1 API wrappers
  1.2 CodeMirror 6
  1.3 editor-mode module
  1.4 FAB wiring
  1.5 reload toast
  1.6 exit gate

Phase 2 — Scope targeting
  2.1 API wrappers
  2.2 dom-map + scope-mode
  2.3 scope bar
  2.4 command mode + scope wiring
  2.5 anchor-ensure
  2.6 exit gate

Phase 3 — New page creation
  3.1 API wrappers
  3.2 new-page-mode module
  3.3 contextual quick-create
  3.4 exit gate

Phase 4 — Polish
  4.1 /ops/events broker
  4.2 overlay subscription
  4.3 localStorage drafts
```

Each phase is independently releasable. A shipped Phase 1 already
delivers Feature 1 end to end; do not wait for later phases before
merging and deploying.
