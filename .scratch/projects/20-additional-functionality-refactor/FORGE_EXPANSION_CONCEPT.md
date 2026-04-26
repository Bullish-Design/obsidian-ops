# FORGE_EXPANSION_CONCEPT.md

## Purpose

This document studies the two prior feature-addition reports in this project
(`FORGE_FEATURE_ADDITION.md` and `FORGE_FEATURE_ADDITION_v2.md`) against the
**actual** Forge codebase as it exists today, summarizes the v2 recommendation
as a baseline, and then proposes an independent implementation plan optimized
for the cleanest and most elegant long-term architecture across
Forge + obsidian-ops + obsidian-agent.

The three features under discussion remain:

1. A full-screen CodeMirror editor mode usable from any rendered page.
2. Precise section / block / selection targeting for LLM-assisted edits.
3. Deterministic new-page creation from the browser.

---

## Reality check: what the repos actually look like

The v1/v2 reports were written as though `obsidian-ops` owned the overlay
assets and the web app layer. The real layout today is different, and this
matters for placing code correctly.

### Forge (this repo, Go)

- Single Go binary fork of Kiln.
- `internal/server/mux.go` is the Forge-specific HTTP handler. It routes:
  - `/api/*` → `ProxyHandler` (reverse proxy to `--proxy-backend`)
  - `/ops/*` → overlay static handler (`--overlay-dir`)
  - everything else → `overlay.InjectMiddleware` → Kiln's static file server
- `internal/overlay/inject.go` injects `<link>` + `<script>` tags pointing at
  `/ops/ops.css` and `/ops/ops.js` into any rendered HTML `<head>`.
- `static/ops.js` and `static/ops.css` are the overlay frontend source of truth.
  They are mounted read-only into the Forge container at `/app/static` by
  `docker/docker-compose.yml` and exposed to the dev server via `--overlay-dir`.
- `internal/templates/shared.templ` emits a `<meta name="forge-current-file"
  content="{RelPath}">` tag on every rendered page. The overlay JS reads this
  tag to know the vault-relative path of the current note.
- `internal/ops/` is a Go port of the legacy in-process Ops runtime. Its
  `README.md` explicitly marks it **deprecated** — do not add new runtime
  dependencies on it.

### obsidian-ops (separate Python library, spec in `.scratch/projects/06`)

- Pure Python library. No HTTP server in v1 (optional in later versions).
- Owns the `Vault` class: path sandboxing, file CRUD, frontmatter, heading /
  block patching, search, Jujutsu-backed commit/undo, mutation lock.
- Import-only dependency of obsidian-agent.

### obsidian-agent (separate Python service)

- FastAPI app, imports `obsidian-ops`.
- Currently exposes `/api/apply`, `/api/undo`, `/api/health`.
- `ApplyRequest` accepts `instruction` and `current_file`. The v2 report claims
  `interface_id` is already routed — the spec in this repo does not show it
  there yet, but `static/ops.js` is already sending `interface_id: "command"`.
  The seam is present and expected.
- Owns agent loop, prompt construction, tool dispatch, LLM provider abstraction.
- Does **not** own raw filesystem mutation (that is obsidian-ops).

### Deployment topology

Docker Compose runs three containers sharing a network namespace via Tailscale:
`tailscale` → `obsidian-agent` → `forge`. A single `forge-vault` volume is
shared between `obsidian-agent` and `forge`. Forge proxies `/api/*` to
`obsidian-agent` at `http://127.0.0.1:8081`. There is exactly one backend
service responding on `/api/*` today.

This topology is important. It means that however we split routes between
"deterministic" and "semantic", the browser always sees **one backend**.

---

## Summary of the v2 recommendation

The v2 report's final ownership split is:

| Feature                     | Primary owner   | Supporting                              |
|----------------------------|-----------------|-----------------------------------------|
| Full-screen CodeMirror mode | obsidian-ops    | Forge (shell, inject, proxy)            |
| Section/item LLM targeting  | obsidian-agent  | obsidian-ops (structure, anchors); Forge frontend |
| New-page creation           | obsidian-ops    | Forge (modal UX); obsidian-agent optional |

Key v2 decisions:

1. Treat direct editor saves as deterministic API calls that never flow
   through the LLM loop.
2. Put a new group of raw-mutation endpoints in obsidian-ops:
   `GET /api/source`, `PUT /api/source`, `GET /api/structure`,
   `POST /api/anchors/ensure`, `POST /api/pages/create`.
3. Extend `ApplyRequest` in obsidian-agent with structured scope metadata
   (`target_mode`, `target_heading`, `target_block_id`, `selected_text`,
   `surrounding_context`, `allowed_write_scope`, `intent_mode`).
4. Use `interface_id = "forge_web"` as a first-class dispatch seam inside
   obsidian-agent for prompt enrichment and tool-restriction.
5. Keep template-based page creation strictly deterministic; allow optional
   agent participation only for prefills or post-create refinement.
6. Implementation order: editor → scoped edits → templates → anchors.

The v2 split is directionally correct. The weaknesses I see in it are:

- It describes obsidian-ops as owning a FastAPI app layer, but in the agreed
  architecture obsidian-ops is an import-only library with (at most) an
  *optional* server. Adding a second real HTTP service on `/api/*` would
  require Forge to route between two backends, or run two processes on the
  same pod.
- Selection / targeting semantics are sprinkled across a growing list of
  optional `ApplyRequest` fields rather than modeled as a cohesive value.
- The overlay frontend ("`ops.js` and `ops.css`") is described as living in
  obsidian-ops, but the source of truth is actually `forge/static/`.
- A monolithic IIFE `ops.js` will not scale to CodeMirror, selection UX,
  scope bar, template modal, and history panel. The frontend needs a real
  module boundary story.

The recommendation below addresses those four issues without throwing away
v2's ownership instincts.

---

## My recommendation: single service, split contracts, typed scopes

The guiding principle is **one deployment surface, two contracts, one
frontend module system**. We keep Forge thin, keep obsidian-ops as a pure
library, let obsidian-agent remain the only backend Forge proxies to, but
split its HTTP surface into two clearly separated route groups:

```
obsidian-agent (FastAPI, single process)
│
├── /api/vault/*     ← deterministic contract
│     thin wrappers around obsidian_ops.Vault
│     no LLM, no tool loop, predictable, idempotent where possible
│
├── /api/agent/*     ← semantic contract
│     LLM tool loop, scope-aware prompt, interface registry
│
└── /api/health      ← unchanged
```

Both groups share the same obsidian-ops `Vault` instance and therefore the
same mutation lock, path sandbox, and Jujutsu VCS. Both groups are reachable
via the exact same Forge reverse proxy. The browser does not need to know
which route is "deterministic" vs "LLM" — it just hits `/api/...`.

This preserves the architectural intent of v2 (Ops owns raw vault, Agent
owns semantics) without introducing a second process or a second proxy
target, and without forcing obsidian-ops to grow its own HTTP app.

### Why single service

- **Deployment stays unchanged.** Docker compose, Tailscale, and Forge's
  `--proxy-backend` keep working with zero topology changes.
- **One mutation lock** is trivially correct because there is one process
  holding one `Vault` instance. Two services on the same vault would force
  us to reinvent lock coordination.
- **No route splitting in Forge.** `mux.go` stays dumb: prefix match,
  proxy, done.
- **obsidian-ops stays a library.** Its surface remains importable classes.
  It never needs FastAPI, uvicorn, or route decorators in its core package.
- **The service can still be torn apart later.** If `/api/vault/*` ever
  needs to run on its own, we lift the route module out of obsidian-agent
  and mount it in an obsidian-ops optional server. Because the routes are
  a thin wrapper around library calls, the migration is mechanical.

### Why split the contracts

- Deterministic routes can be called unconditionally by the editor, the
  template picker, and any future non-LLM UI action, without paying agent
  startup cost or LLM semantics risk.
- The semantic route can continue to evolve its `ApplyRequest` / scope
  model without dragging in editor save concerns.
- The mental model for readers of the code is clean: every route is either
  "this maps to a Vault method" or "this invokes the agent loop".

---

## Core design moves

### 1. Deterministic vault routes under `/api/vault/*`

A single `vault_routes.py` module inside obsidian-agent that imports
obsidian-ops and wires FastAPI routes. Resource-oriented naming:

| Method | Path                                        | Maps to                                      |
|--------|---------------------------------------------|----------------------------------------------|
| GET    | `/api/vault/files?path=...&url=...`         | `vault.read_file` (+ sha256 + modified_at)   |
| PUT    | `/api/vault/files`                          | `vault.write_file` with optimistic hash      |
| GET    | `/api/vault/files/structure?path=...`       | `vault.list_structure` (new)                 |
| POST   | `/api/vault/files/anchors`                  | `vault.ensure_block_id` (new)                |
| GET    | `/api/vault/pages/templates`                | template registry                            |
| POST   | `/api/vault/pages`                          | `vault.create_from_template` (new)           |
| POST   | `/api/vault/undo`                           | `vault.undo` (explicit, not agent undo)      |

Conventions:

- Every write uses optimistic concurrency (`expected_sha256`). Stale writes
  return 409 with the server's current hash so the UI can reconcile.
- Every write triggers a rebuild notification (see §4 below).
- Path resolution accepts either a vault-relative `path` *or* a site URL
  via `url`. URL-to-path resolution is a small helper module in
  obsidian-agent (`web_paths.py`) because it depends on Kiln's URL rules;
  obsidian-ops does not need to know about URLs.
- All routes return the same shape `{ ok, path, sha256, url?, warning? }`
  where meaningful. Consistent response envelopes make the overlay JS
  trivial.

### 2. Three new primitives in obsidian-ops `Vault`

These belong in the library because they operate on raw markdown and must
respect the path sandbox and mutation lock. They should not exist as ad-hoc
agent code.

#### `vault.list_structure(path) -> StructureView`

Parses a markdown file once and returns:

```python
@dataclass
class Heading:
    text: str        # "## Roadmap"
    level: int       # 2
    line_start: int  # 1-based, inclusive
    line_end: int    # inclusive; end of section or file

@dataclass
class Block:
    block_id: str    # without the leading caret
    line_start: int
    line_end: int

@dataclass
class StructureView:
    path: str
    sha256: str
    headings: list[Heading]
    blocks: list[Block]
```

Deterministic output for a given input hash. The overlay uses this to draw
margin handles and the pinned-scope bar without any DOM guessing.

#### `vault.ensure_block_id(path, line_start, line_end) -> EnsureBlockResult`

Idempotent: if the target range already ends with a `^block-id`, reuse it;
otherwise generate a short stable ID, append it, and atomically write.
Returns the block ID plus the resulting `sha256`. This is the primitive
that turns a transient selection into a durable anchor.

#### `vault.create_from_template(key, fields) -> CreatePageResult`

Reads a template definition, renders the path and body, ensures parents,
writes atomically, commits. The template **registry** is a small module
(`obsidian_ops.templates`) that loads YAML from a configurable location
(`AGENT_TEMPLATE_DIR` env var, default `<vault>/.forge/templates/`). The
registry is pure data: list → validate → render. No LLM, no globals.

This is the elegant place for templates because:

- It keeps deterministic behavior with the mutation lock on one side of the
  call stack.
- Agent tools can later expose `create_from_template` as an LLM tool
  without any plumbing changes.
- Vault-local template storage means the user can version templates as part
  of their vault, which is exactly the Obsidian mental model.

### 3. Typed `EditScope` value for the semantic contract

Rather than adding eight optional fields to `ApplyRequest`, introduce a
single cohesive type. This is the single most important shape in the
proposed design.

```python
class FileScope(BaseModel):
    kind: Literal["file"] = "file"
    path: str

class HeadingScope(BaseModel):
    kind: Literal["heading"] = "heading"
    path: str
    heading: str              # exact markdown, e.g. "## Roadmap"

class BlockScope(BaseModel):
    kind: Literal["block"] = "block"
    path: str
    block_id: str             # without caret

class SelectionScope(BaseModel):
    kind: Literal["selection"] = "selection"
    path: str
    text: str
    line_start: int
    line_end: int
    context_before: str | None = None
    context_after: str | None = None

class MultiScope(BaseModel):
    kind: Literal["multi"] = "multi"
    path: str
    scopes: list[HeadingScope | BlockScope | SelectionScope]

EditScope = Annotated[
    FileScope | HeadingScope | BlockScope | SelectionScope | MultiScope,
    Field(discriminator="kind"),
]

class ApplyRequest(BaseModel):
    instruction: str
    interface_id: str = "command"
    scope: EditScope | None = None
    intent: Literal["rewrite", "summarize", "insert_below",
                    "annotate", "extract_tasks"] | None = None
    allowed_write_scope: Literal["target_only", "target_plus_frontmatter",
                                 "unrestricted"] = "target_only"
```

Why this is better than eight optional fields:

- **Invariants are type-enforced.** A `BlockScope` cannot exist without a
  `block_id`, and the compiler / pydantic prevents nonsense combinations
  like "block_id with heading set".
- **Pattern matching in the agent becomes the natural dispatch mechanism.**
  `match scope:` lines read like the spec.
- **Prompt construction and tool-policy selection can both dispatch on one
  tagged union.** No boolean soup.
- **Frontwards compatible.** Adding a `TableCellScope` later is a new
  variant, not a new column in every request.

### 4. Interface registry as real dispatch, not string checks

The `interface_id` seam should become an actual registry, not a growing
`if/elif` chain.

```python
class InterfaceProfile(Protocol):
    id: str
    def allowed_tools(self, scope: EditScope | None) -> list[Tool]: ...
    def build_prompt(self, request: ApplyRequest) -> str: ...

INTERFACES: dict[str, InterfaceProfile] = {
    "command":   CommandProfile(),   # full toolset, generic prompt
    "forge_web": ForgeWebProfile(),  # scope-restricted tools + prompt
}
```

For `forge_web`:

- If `scope` is a `BlockScope`, expose only `read_block`, `write_block`,
  and read-only helpers. Do **not** expose `write_file`.
- If `scope` is a `HeadingScope`, expose only heading and frontmatter tools.
- If `scope` is a `SelectionScope`, expose heading/block tools plus the
  generic whole-file fallback, but the prompt constrains the model to
  rewrite only the quoted range.
- If `scope` is `None` or `FileScope`, fall back to the existing full
  toolset with a gentler prompt.

This is where "precise section targeting" becomes structurally safe instead
of prompt-dependent. A model that never sees `write_file` literally cannot
rewrite the whole file.

### 5. A rebuild notification seam instead of synchronous rebuilds

The v2 recommendation asks Obsidian-Ops to "trigger rebuild" after each
source save. In the real architecture, rebuilds happen in **Forge** via the
file watcher (`internal/watch`). The agent should not try to drive Kiln's
build pipeline directly.

Two options; I recommend the first:

1. **Rely on the existing watcher.** Any atomic write into the shared
   `forge-vault` volume is already seen by `internal/watch` and kicks an
   `IncrementalBuild`. Source saves become rebuild-triggering automatically
   and the API simply returns after the atomic write. The browser then
   polls the rendered page or receives an SSE "build finished" event.

2. **Add a lightweight `/internal/rebuild-hint` endpoint on Forge** that
   the agent pings after a write. This is only worth doing if we find the
   watcher introduces too much latency or misses events.

Option 1 is strictly simpler and matches how the system already behaves for
agent-driven edits. No new code needed.

*Optional polish:* expose a tiny SSE endpoint on Forge (`/ops/events`) that
streams `{ type: "rebuilt", files: [...] }` after each incremental build,
and have the overlay subscribe to it. This replaces manual "Save & Refresh"
buttons with automatic reloads and is much nicer on mobile.

### 6. Frontend architecture: split the overlay into ES modules with a tiny build step

`static/ops.js` is 296 lines of IIFE today and will not survive the new
feature set cleanly. Recommended structure:

```
static/
├── ops.css                 # still the single compiled stylesheet
├── ops.js                  # generated bundle, entry for injector
└── src/
    ├── main.js             # bootstraps overlay, mounts FAB
    ├── api.js              # fetch wrappers for /api/vault/* and /api/agent/*
    ├── page-context.js     # reads meta tag, resolves current file + URL
    ├── fab.js              # the floating button + mode switcher
    ├── modes/
    │   ├── command-mode.js # existing instruction modal (current behavior)
    │   ├── editor-mode.js  # CodeMirror 6 full-screen editor
    │   ├── scope-mode.js   # selection, margin handles, scope bar
    │   └── new-page-mode.js# templates modal
    ├── ui/
    │   ├── toast.js
    │   ├── sheet.js        # mobile action sheet primitive
    │   └── modal.js
    └── lib/
        └── codemirror.js   # re-export of bundled CodeMirror 6
```

Build step:

- Use **esbuild** (single dev dep, zero config) to bundle `src/main.js` →
  `static/ops.js`. Output is a single file, so Forge's existing overlay
  handler keeps working without any server change.
- `static/ops.js` becomes generated output. Add it to git or build it on
  demand — either is fine; committing it keeps runtime deploy unchanged.
- Alternative, lower-overhead: do not bundle; use native ES modules served
  under `/ops/src/*`. This works because Forge already serves the entire
  overlay directory. CodeMirror 6 distributes as ES modules so this is
  viable. The downside is one extra round trip tree per module load on
  mobile. If mobile latency matters, prefer esbuild.

The key point is that whichever approach we pick, we stop treating
`ops.js` as a single growing file.

#### Lazy loading

Editor mode, scope mode, and new-page mode should all be lazy-loaded on
first use. The initial overlay payload stays tiny (~10 KB) for readers
who never enter an edit mode. CodeMirror 6 is ~100 KB gzipped and should
only load when the user taps "Edit".

#### Single state machine

Overlay state becomes a small finite-state machine:

```
reading ─tap:Edit→ editing ─save→ reading
reading ─tap:FAB→ commanding ─submit→ running → reading|error
reading ─select text→ scoping ─action→ commanding
reading ─tap:New→ templating ─create→ reading
```

One state variable, one transition function. No flags scattered across
closures. This is elegance by constraint.

### 7. Keep the `meta name="forge-current-file"` contract and extend it

`internal/templates/shared.templ` emits `forge-current-file`. For the new
features the overlay also needs the site URL slug (for redirecting after
create) and any configured template namespace. Extend the template once:

```html
<meta name="forge-current-file"    content="{{ data.File.RelPath }}">
<meta name="forge-current-url"     content="{{ data.File.WebPath }}">
<meta name="forge-site-prefix"     content="{{ data.Site.BaseURL }}">
```

Any further per-page metadata the overlay needs should come from this meta
tag set, not from URL parsing in JS. This keeps the "Forge renders, overlay
reads" contract crisp.

### 8. Templates as a vault-local concern

Templates live in `<vault>/.forge/templates/*.yaml`. Example:

```yaml
id: project
label: Project
path: "Projects/{{ slug(title) }}.md"
body: |
  ---
  type: project
  status: active
  created: {{ today }}
  ---

  # {{ title }}

  ## Goal

  ## Next actions

  ## Notes
```

Rendering uses a deliberately small helper set: `slug`, `today`, `now`, and
`field(name)` for user-provided fields. No Jinja, no complex expressions.
Deterministic templates should feel like form fills, not programs.

`vault.create_from_template` validates that the rendered path stays under
the vault root (via the existing sandbox), then writes atomically, commits
with a clear message like `ops: create project 'Website refresh'`, and
returns `{ path, sha256, url }`.

---

## End-to-end walkthrough of each feature

### Feature 1: Full-screen CodeMirror editor mode

1. User taps the overlay "Edit" action on any rendered page.
2. `editor-mode.js` reads `meta[name=forge-current-file]` for the path and
   calls `GET /api/vault/files?path=...`.
3. Response includes `content` and `sha256`. The module mounts a CodeMirror
   6 instance over the page in a full-screen container with a sticky mobile
   toolbar (Back, Save, Undo, Ask AI, Scope, New).
4. On Save, the module calls `PUT /api/vault/files` with the full content
   and the `expected_sha256` it received. On 409 the UI offers "Reload"
   or "Overwrite".
5. Because the watcher sees the atomic write, Forge rebuilds the page.
   The editor subscribes to `/ops/events` (if implemented) or the user
   taps "Reload" (if not). Either way the render updates.
6. Undo routes through `POST /api/vault/undo`, which wraps `vault.undo()`.

No agent involvement. Ever.

### Feature 2: Section/item targeting for LLM edits

1. User long-presses a heading or selects text.
2. `scope-mode.js` requests `GET /api/vault/files/structure?path=...` on
   first entry into scope mode and caches the result. It maps the DOM
   selection to a `Heading`, `Block`, or line range.
3. If the target is a block without a stable ID, the overlay offers an
   "Anchor this block" action that calls `POST /api/vault/files/anchors`.
   Future edits become robust.
4. The user taps "Ask AI about this". The overlay sends:
   ```json
   {
     "instruction": "Rewrite as a bullet list",
     "interface_id": "forge_web",
     "scope": { "kind": "heading", "path": "...", "heading": "## Roadmap" },
     "allowed_write_scope": "target_only"
   }
   ```
   to `POST /api/agent/apply`.
5. Agent dispatches on `interface_id="forge_web"`, constructs a
   `ForgeWebProfile` prompt, exposes only heading/frontmatter tools, and
   runs the loop. The model physically cannot rewrite the whole file
   because `write_file` is not in its toolset for this request.
6. On success the overlay receives the usual `OperationResult` envelope
   and reloads the page (or waits for the SSE rebuild event).

### Feature 3: New-page creation

1. User taps "New" in the overlay.
2. `new-page-mode.js` calls `GET /api/vault/pages/templates` once per
   session and caches.
3. User picks a template, fills required fields (title at minimum), taps
   Create.
4. Overlay calls `POST /api/vault/pages` with
   `{ id: "project", fields: { title: "..." } }`.
5. Server renders path + body, writes atomically, commits, returns
   `{ path, sha256, url }`.
6. Overlay navigates to the returned `url`. Forge has already rebuilt.

---

## File-level change plan

### Forge (Go, this repo)

No runtime code change is strictly required. Suggested small additions:

- `internal/templates/shared.templ` — add `forge-current-url` and
  `forge-site-prefix` meta tags (§7). Regenerate `shared_templ.go`.
- `static/src/*` — new overlay module tree (§6).
- `static/ops.js` — becomes the bundled output of `static/src/main.js`.
- `package.json` — add `esbuild` as a devDependency and a `build:ops`
  script. Optional, only if we go with bundling.
- `internal/watch` — unchanged; it already picks up vault writes.
- Optional: `internal/overlay/events.go` — a tiny SSE endpoint at
  `/ops/events` that publishes rebuild notifications from the watcher.
- Do **not** touch `internal/ops/`. It remains deprecated.

### obsidian-ops (Python library)

Additions only, no breaking changes:

- `obsidian_ops/structure.py` — `list_structure(path)` with `Heading` /
  `Block` / `StructureView` dataclasses.
- `obsidian_ops/anchors.py` — `ensure_block_id(path, line_start, line_end)`
  using the existing atomic write + lock.
- `obsidian_ops/templates.py` — template registry loader and renderer.
- `obsidian_ops/vault.py` — expose `list_structure`, `ensure_block_id`,
  and `create_from_template` on the `Vault` class. These compose existing
  primitives; no new sandbox logic.
- Tests for each new primitive, including a sandbox escape attempt in
  `create_from_template` (rendered path tries `..`).

### obsidian-agent (Python service)

Restructure the app module to reflect the two contracts:

- `obsidian_agent/app.py` — mounts two routers:
  - `vault_router` at `/api/vault`
  - `agent_router` at `/api/agent`
  - plus legacy `/api/apply` / `/api/undo` aliases forwarding to the new
    routes, so `static/ops.js` keeps working during migration.
- `obsidian_agent/routes/vault_routes.py` — thin wrappers around
  `obsidian_ops.Vault` and the web-path resolver.
- `obsidian_agent/routes/agent_routes.py` — the existing agent loop, but
  dispatched through `interfaces/`.
- `obsidian_agent/web_paths.py` — URL → vault path resolution, using the
  same Kiln-style rules Forge uses (clean URLs, `flat` vs pretty).
- `obsidian_agent/scope.py` — the `EditScope` tagged union (§3).
- `obsidian_agent/interfaces/__init__.py` — `InterfaceProfile` protocol.
- `obsidian_agent/interfaces/command.py` — existing behavior, renamed.
- `obsidian_agent/interfaces/forge_web.py` — new scope-aware profile.
- `obsidian_agent/prompt.py` — profile-delegated prompt construction.
- `obsidian_agent/tools.py` — unchanged tool definitions, but the set
  exposed per request is chosen by the `InterfaceProfile`.

### Docker

No change. Both contracts live in the same obsidian-agent container, so the
existing compose file and proxy backend URL keep working.

---

## Implementation phases

Each phase is independently shippable and adds user-visible value.

### Phase 0: plumbing and parity

- Extend the `shared.templ` meta tags.
- Introduce `static/src/` module tree and rebuild `ops.js` with identical
  behavior to today (command modal + undo). Strictly a refactor.
- Add `esbuild` build step (or native ESM) and CI check that `ops.js` is
  in sync with `src/`.
- Add a failing CI gate for `go test ./...` on `internal/overlay`,
  `internal/server`, and `internal/proxy`.

Ship nothing user-visible; prevents all later phases from drowning in the
monolith.

### Phase 1: deterministic vault contract + editor mode

- In obsidian-ops: add `list_structure`, `ensure_block_id`,
  `create_from_template` (templates phase can be minimal here).
- In obsidian-agent: add `routes/vault_routes.py` with
  `GET/PUT /api/vault/files` (at minimum) and the web-path resolver.
- In Forge: add `editor-mode.js`, lazy-load CodeMirror 6, full-screen
  takeover with mobile toolbar, optimistic-concurrency save.
- No agent changes.

Ships the biggest mobile UX win first.

### Phase 2: semantic contract with scope + interface registry

- In obsidian-agent: add `scope.py`, `interfaces/*`, rewire `/api/apply`
  to `/api/agent/apply` with the new `ApplyRequest` shape. Keep a
  back-compat shim for the old shape.
- In obsidian-agent: implement `forge_web` profile with scope-restricted
  tools and scope-aware prompt.
- In Forge: add `scope-mode.js`, selection menu, margin handles on
  headings and list items, pinned scope bar.
- In obsidian-ops: add the structure + anchors endpoints' backing methods
  if not already added in Phase 1.

Ships precise LLM edits.

### Phase 3: templated creation

- In obsidian-ops: finalize `templates.py`, ship a default template set
  under `<vault>/.forge/templates/`.
- In obsidian-agent: add `GET /api/vault/pages/templates` and
  `POST /api/vault/pages`.
- In Forge: add `new-page-mode.js` modal.

Ships fast deterministic page creation.

### Phase 4: polish

- Optional SSE `/ops/events` for auto-reload after rebuild.
- Draft autosave in `localStorage`.
- Multi-scope pinning for cross-section edits.
- Expose `create_from_template` to the agent toolset under `forge_web`
  with a restrictive prompt so the LLM can assist creation without
  improvising file paths.

---

## Design calls that set this apart from v1/v2

1. **Single backend service with two mounted routers.** Keeps obsidian-ops a
   library, keeps Forge's proxy dumb, and prevents the "two backends, one
   vault" mutation-lock problem.
2. **`EditScope` as a discriminated union, not loose fields.** Makes scope
   semantics type-enforced and allows elegant `match` dispatch in the agent.
3. **Interface registry as real dispatch.** Tool restriction stops being a
   prompt hope and becomes a structural guarantee: the model receives
   only the tools it is allowed to use.
4. **Vault-local YAML templates with a minimal render language.** Keeps
   templates in the user's vault, under version control, and outside
   Python code.
5. **Rely on the existing file watcher for rebuilds.** No synchronous
   rebuild coupling between agent routes and Kiln. Less code, less drift.
6. **ES module overlay with lazy-loaded modes.** `ops.js` stops being a
   single file; CodeMirror never loads on pages where the user doesn't
   edit.
7. **Meta-tag contract extension instead of URL parsing in JS.** Keeps the
   "Forge renders, overlay reads" boundary crisp and single-sourced.
8. **`internal/ops/` stays deprecated.** No Go re-implementation of
   Python-side features. One runtime, one mutation path.

---

## Risks and mitigations

| Risk                                                 | Mitigation                                                                                              |
|------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| Mounting two routers in one service blurs ownership  | Enforce the split with a lint rule / code review guideline: `vault_routes` never imports `agent.*`.     |
| `EditScope` union churn as new variants appear       | Cover every variant with a snapshot test of the generated prompt + allowed toolset. Add new variants only with a profile update. |
| CodeMirror 6 bundle size hurts first render          | Lazy-load editor mode; bundle only the langs we use (markdown + search).                                |
| Save races between editor and agent                  | Optimistic concurrency hashes in both contracts. Agent and editor both route through the same `Vault` mutation lock. |
| Template path injection                              | `create_from_template` pushes the rendered path through the existing sandbox before writing.           |
| Watcher latency on mobile                            | Optional SSE rebuild event (§5). Start without it; add only if measured latency hurts.                  |
| Frontend complexity balloons                         | Cap overlay modes at four (command, editor, scope, new). Anything larger becomes a real app, not an overlay. |

---

## Acceptance summary

- **Feature 1** ships when a user can tap Edit on any rendered page, see a
  full-screen CodeMirror 6 editor with the page's markdown, save with
  optimistic concurrency, see the rebuilt page, and undo via
  `/api/vault/undo` — all without the LLM running.
- **Feature 2** ships when a user can long-press a heading or select text,
  send a scoped edit to the agent, and the agent model is structurally
  prevented from modifying anything outside the scope because its tool set
  does not contain the tools that would allow it.
- **Feature 3** ships when a user can tap New, pick a template, fill the
  title, and land on a rebuilt page created from a vault-local YAML
  template, with no LLM involvement by default.

---

## Closing recommendation

The v2 report's ownership instincts are right: Forge is the shell,
obsidian-ops owns raw mutation, obsidian-agent owns semantic edits. The two
refinements that turn that into the cleanest possible codebase are:

1. **One service, two contracts.** Mount `/api/vault/*` and
   `/api/agent/*` inside the existing obsidian-agent process. No second
   backend, no route splitting in Forge, no second mutation lock.
2. **Typed `EditScope` + interface registry + structural tool restriction.**
   Make "edit only this section" a property of the agent's tool graph, not
   of a prompt paragraph.

Everything else in this plan — the ESM overlay, the vault-local templates,
the meta-tag contract, the watcher-based rebuild seam — follows from
holding those two lines.
