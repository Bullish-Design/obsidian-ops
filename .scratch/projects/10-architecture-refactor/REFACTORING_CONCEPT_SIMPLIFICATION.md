# REFACTORING_CONCEPT_SIMPLIFICATION

## Purpose

This document analyzes how to simplify the architecture in `REFACTORING_CONCEPT.md` for the fastest viable MVP.

Primary requested simplification:
- Remove SSE complexity.
- Update UI only when work is complete.
- Expose an `updated` signal so users know when to refresh.

Additional simplifications are included and prioritized by implementation cost vs. complexity removed.

## Research inputs

This analysis is based on:
- `.scratch/projects/10-architecture-refactor/REFACTORING_CONCEPT.md`
- Current monolith runtime code in `src/obsidian_ops/` (`app.py`, `queue.py`, `static/ops.js`, `inject.py`, `rebuild.py`, `config.py`)
- Current tests (`tests/test_api.py`, `tests/test_queue.py`, `tests/test_inject.py`, `tests/test_demo_cli.py`)
- Demo behavior notes in `demo/obsidian-ops/README.md`

## Baseline complexity in the current concept

The current concept intentionally carries several advanced concerns at once:
- 3 repos (`forge`, `obsidian-agent`, `obsidian-ops`).
- Async jobs and progress streaming (`/api/jobs`, `/api/jobs/{id}/stream`, event fanout).
- Reverse proxy rules that must preserve SSE flush behavior.
- Process orchestration across two subprocesses plus health-check sequencing.
- Rebuild and overlay wiring split across components.

For an MVP, the highest removable complexity is SSE + job queueing.

## Simplification A (Primary): remove SSE, return only final result

### What changes

Replace the async job model with request/response operations.

Current shape:
- `POST /api/jobs` returns `job_id`.
- `GET /api/jobs/{id}/stream` streams `status/tool/result/error/done`.

Simplified shape:
- `POST /api/apply` executes instruction and returns final payload.
- `POST /api/undo` executes undo and returns final payload.

Suggested response model:

```json
{
  "ok": true,
  "updated": true,
  "summary": "Updated note and added a summary section.",
  "warning": null,
  "error": null,
  "changed_files": ["notes/example.md"]
}
```

### `updated` semantics

Use a deterministic rule:
- `updated=true` if vault content changed or undo succeeded.
- `updated=false` if no-op (agent produced no file changes).
- `ok=false` for failures; optionally keep `updated=true` only if changes were made before failure.

Keep it simple for MVP:
- Treat `ok=true && changed_files.length > 0` as `updated=true`.
- For undo success, force `updated=true`.

### UI behavior

Replace `EventSource` flow in `ops.js` with a single `fetch`:
- On submit: disable inputs and show "Running...".
- On response:
- If `ok=true` and `updated=true`, show "Updated. Refresh page.".
- If `ok=true` and `updated=false`, show "No changes made.".
- If `ok=false`, show the error.

This removes:
- Stream listeners.
- Event-type handling.
- SSE reconnect/interrupt behavior.
- Server-side broadcaster and sentinel close mechanics.

### Why this is viable

It preserves the core user value:
- User issues instruction.
- Vault updates.
- User sees whether a refresh is needed.

It drops non-essential UX polish (live progress) for MVP speed and reliability.

### Tradeoffs

- Loss of step-by-step visibility.
- Longer blocking HTTP requests.
- Harder to inspect mid-flight behavior.

Mitigation:
- Set explicit server timeout guards for model/tool execution and return clear errors.

## Additional simplification concepts (prioritized)

## 1) Keep 3-repo target, but defer to a 2-stage delivery

Stage 1 MVP:
- Build `obsidian-agent` first with synchronous endpoints (no SSE).
- Keep existing Python app as UI host temporarily or use minimal proxy.

Stage 2:
- Introduce Forge fork and full separation.

Why:
- Reduces number of moving parts introduced simultaneously.
- Keeps the long-term architecture while reducing early integration risk.

## 2) Defer reverse proxy for MVP and call agent directly from UI

MVP alternative:
- UI served on one port.
- Agent on another port.
- Browser calls agent directly with minimal CORS handling.

Why:
- Avoids proxy implementation and debugging.
- Completely removes SSE-through-proxy concerns.

Tradeoff:
- Two-origin setup and CORS configuration.

## 3) Remove queue worker pattern; use one in-flight operation per request

Current code has queue + worker + broadcaster.
MVP can be:
- API handler executes run/undo inline.
- No `JobQueue`, no background consumer, no subscriber lifecycle.

Why:
- Major code and test surface reduction.
- Easier failure semantics.

Tradeoff:
- Fewer concurrency controls.

## 4) Defer `/api/history` and optional agent tools that are not core edit path

For MVP command loop, required tools are typically:
- Read/list/search/write file tools.

Can defer:
- History endpoint/tool exposure in UI path.

Why:
- Shrinks API and tool policy surface.
- Reduces error cases around VCS interactions unrelated to basic editing.

## 5) Minimize abstraction layers initially (`AgentRunner`, `VCSAdapter`, hooks)

Keep concrete classes first; introduce protocols only when there is a second implementation.

Why:
- Fewer interfaces and fixtures to maintain.
- Faster to stabilize behavior before abstraction.

Tradeoff:
- Slightly harder future swappability in early phase.

## 6) Defer Forge response-time HTML injection if static templating can cover MVP

If Kiln custom templating or a stable layout injection point is available for your site mode:
- Include overlay assets in templates.
- Skip response-body rewriting middleware initially.

Why:
- Avoids complexity around buffering/content-length semantics.

Tradeoff:
- Less generic injection coverage.

## 7) Reduce config surface to operational minimum

For MVP, keep only:
- `vault_dir`, `site_dir`
- model URL/model name/key
- server host/port

Defer tuning knobs:
- max results/iterations, advanced ports, extra runtime toggles.

Why:
- Less config drift across repos/processes.

## 8) Narrow MVP test matrix

Focus on smoke-critical flows:
- Apply success with changes.
- Apply no-op.
- Apply failure.
- Undo success.
- Health endpoint.

Defer:
- Stream-event contract tests.
- Broadcaster/subscriber tests.
- Proxy flush behavior tests (until SSE exists).

Why:
- Faster cycle time and less brittle integration overhead.

## Recommended MVP profile

If the goal is "ship fastest with minimum architecture risk", use this profile:

- No SSE.
- No job IDs.
- Synchronous `POST /api/apply` and `POST /api/undo`.
- Response contains `ok`, `updated`, `summary`, `error`, optional `warning`.
- UI shows "refresh needed" when `updated=true`.
- Keep one process boundary at first (or two without proxy).
- Add explicit operation timeout limits.

This is the smallest implementation that still proves end-to-end product value.

## Minimal API sketch

```http
POST /api/apply
{
  "instruction": "...",
  "current_url_path": "/notes/xyz"
}

200
{
  "ok": true,
  "updated": true,
  "summary": "...",
  "error": null,
  "warning": null,
  "changed_files": ["..."]
}
```

```http
POST /api/undo

200
{
  "ok": true,
  "updated": true,
  "summary": "Last change undone.",
  "error": null,
  "warning": null,
  "changed_files": []
}
```

## Migration delta from current code

Largest deletions if this MVP profile is chosen:
- Remove SSE stream route and event generator logic in API layer.
- Remove `SSEBroadcaster` and subscriber bookkeeping.
- Remove `EventSource` handling in `ops.js`.
- Collapse queue worker into direct call path.

Retained value path:
- Agent tool loop.
- Jujutsu commit/undo.
- Rebuild + overlay + manual refresh signal.

## Risks introduced by simplification and controls

Risk:
- Long-running request may timeout.

Control:
- Hard timeout around model call/tool execution and clear user-visible error.

Risk:
- Reduced transparency while operation is running.

Control:
- Show deterministic UI states: `running`, `done`, `error`, plus final summary.

Risk:
- User refreshes before build catches up.

Control:
- Keep `updated` and optional `warning` text; instruct refresh explicitly.

## Conclusion

Yes, the requested simplification is practical and aligns with MVP goals.

Removing SSE and shifting to final-result responses yields a large complexity reduction across API, UI, proxy behavior, and test burden while preserving the core workflow: issue instruction, apply changes, know when to refresh.

If desired, SSE can be reintroduced later as an additive enhancement without changing the basic operation contract.
