# Refactoring obsidian-ops into Forge, an Obsidian agent service, and a thinner orchestration layer

## Executive summary

The current `obsidian-ops` codebase tightly couples three concerns into one process: (a) serving a Kiln-generated site and injecting an overlay UI, (b) running an LLM “agent loop” that edits the vault via constrained tools, and (c) rebuilding the site + versioning changes with Jujutsu, with progress streamed to the browser via SSE. fileciteturn0file0L5-L33 citeturn8view0turn19view0turn20view0turn20view2turn31view0

A clean future-state split that matches your goals is:

- **Forge (Web UI + local reverse proxy)**: run `kiln dev` as the “site engine” and put Forge in front as a lightweight reverse proxy that (1) injects the UI primitives into HTML responses (instead of rewriting files on disk) and (2) exposes same-origin `/api/*` endpoints that forward user instructions to the agent service. Kiln’s own docs explicitly position `dev` as “generate + serve + watch” in one command. citeturn26view0turn21view0turn11view0  
- **Obsidian LLM interaction (agent service library)**: extract the vault tool runtime + agent loop behind a stable interface (events in, events out). You can either keep your current OpenAI-compatible tool-calling approach (already working) or adopt an existing “agent loop” library—most directly, the emerging **Python port of `pi-agent-core`** (designed for stateful tool execution + event streaming and explicitly described as a port of the TypeScript pi-agent-core). citeturn20view2turn17view0  
- **Future obsidian-ops (orchestration library)**: a thin integration layer that wires Forge ↔ agent service ↔ vault/versioning policies and provides a cohesive CLI/config story (but keeps “serve/proxy/UI” and “agent/vault ops” independently testable).

Recommendation: keep the **agent service in Python first** (to minimize migration risk and reuse your existing hardened filesystem routines and FastAPI/SSE patterns), and implement Forge as a **reverse proxy + HTML response injector** on top of `kiln dev`. Then, optionally evolve toward a more “headless harness” protocol (Codex App Server–style) once the three-library split settles. citeturn8view0turn26view0turn28search12turn28search0turn28search4

## Current system analysis

Today, `obsidian-ops` is a single Python package (requires Python ≥3.13) using FastAPI/Uvicorn and the OpenAI Python SDK for tool-calling against an OpenAI-compatible base URL (defaulting to a vLLM-style endpoint). citeturn29view0turn20view2

At startup (FastAPI lifespan), the server:

- ensures the Jujutsu workspace is ready,  
- runs a full site rebuild via `kiln generate --input <vault> --output <site>`,  
- then post-processes every generated HTML file and injects `/ops/ops.css` + `/ops/ops.js` before `</head>`,  
- then starts a background worker that processes jobs and streams progress to the UI. citeturn8view0turn19view0turn20view0

Key coupling points that matter for the refactor:

**UI injection is currently a build-step side effect.** `inject_overlay()` walks `site_dir.rglob("*.html")` and rewrites each file, adding the overlay script and stylesheet once per file using a marker. This makes the UI “part of the generated artifact,” which conflicts with the idea of switching to `kiln dev` (which continuously regenerates output). citeturn20view0

**Serving and API share one origin by mounting the static site at `/`.** The FastAPI app mounts `/ops` for overlay assets and mounts the entire generated site at `/` using `StaticFiles(..., html=True)`, with a middleware that rewrites “clean URLs” to `.html` or `/index.html` when appropriate. citeturn8view0

**Agent loop is already “headless-ish” and streams coarse lifecycle events.** The Agent uses `openai.AsyncOpenAI(base_url=..., api_key=...)` and calls `chat.completions.create(..., tools=..., tool_choice="auto")` in a bounded loop (`max_tool_iterations`), emitting SSE status/tool updates via a callback. citeturn20view2turn8view0

**Vault operations are a separable unit with real safety properties.** `ToolRuntime.write_file()` validates vault-relative paths, uses per-file asyncio locks, writes atomically, and tracks changed files. Tools include reading/writing/listing/searching markdown, fetching a URL (with a size cap), undoing last change, and reading file history. citeturn20view3turn31view0turn31view1

**Repo activity indicates the architecture is still fluid but recent.** The commit log shows an initial commit on April 4, 2026 and a sequence of “step N” commits on April 5, 2026; issues and PRs are currently 0. citeturn30view0turn6view0

These observations suggest a natural separation line:

- what **should become Forge**: HTTP serving, HTML injection, UI assets, same-origin API gateway, and process management for Kiln.
- what **should become the agent library**: job execution, SSE event schemas, agent loop, tool runtime, vault policies, VCS adapter.

## Kiln capabilities relevant to Forge

Kiln’s documentation explicitly frames it as an Obsidian-vault-to-static-site generator with “parity first” support (wikilinks, canvas, LaTeX, callouts, etc.), and it emphasizes **HTMX-powered client-side navigation**. citeturn4view0turn11view0

The `kiln dev` command is especially central to your Forge goal:

- It combines `generate` + `serve` into a single workflow, performs an initial full build, then watches for changes and rebuilds while serving output on a local HTTP server (default port 8080). citeturn26view0
- It computes a dependency graph based on wikilinks and uses a filesystem watcher (via `fsnotify`) with debouncing. citeturn26view0turn21view0
- The “Incremental Builds” spec clarifies current limitations: although a ChangeSet is computed, rebuilds may still be full regenerations, the dependency graph is built once at startup, and only wikilink/markdown link dependencies are tracked. citeturn21view0

Kiln’s `hx-boost` behavior matters directly for an injected overlay UI: Kiln swaps page content without a full reload, so `DOMContentLoaded` will not fire on navigation; custom JS must listen to HTMX lifecycle events (e.g., `htmx:afterSwap`). citeturn11view0

### Component-to-Kiln feature mapping for Forge

| Kiln behavior / feature | What Forge can reuse | Practical design implication |
|---|---|---|
| `kiln dev` = build + watch + serve citeturn26view0turn21view0 | Use it as the site engine and preview server | Forge should not “own” rebuild logic; it should supervise `kiln dev` and proxy to it. |
| Clean URL support is part of Kiln’s dev/serve workflow citeturn26view0 | Avoid duplicating clean-URL rewriting in Python | Your current FastAPI clean-URL middleware can be removed if Forge proxies to Kiln. citeturn8view0 |
| HTMX `hx-boost` SPA-like navigation citeturn11view0 | Fast perceived navigation and persistent layout | Forge overlay JS must be resilient to partial swaps and re-bind on `htmx:afterSwap`. |
| `kiln.yaml` config file auto-discovery citeturn9view0 | Stable, file-based site configuration | Forge can generate/validate `kiln.yaml` rather than assembling brittle CLI flags. |
| Custom Mode templating (`layout.html`, components, `get`, etc.) citeturn10view0 | A “native” way to include extra scripts/styles | Optional alternative to injection: if you adopt Custom Mode, you can include Forge UI in templates; otherwise proxy-injection is simpler and keeps default mode. |

## Options for the Obsidian LLM agent interaction layer

Your stated goal is “server endpoint → interaction interface” akin to a headless agent that receives input over HTTP and executes against a local vault. That is already close to today’s design (jobs + SSE + tool-calling). citeturn8view0turn20view2turn31view0

Below are the most relevant “build on an existing library” options, emphasizing tool calling + streaming + state.

### pi-mono / “Pi” ecosystem

The TypeScript **pi-mono** monorepo explicitly provides layered packages: `pi-ai` (multi-provider LLM API), `pi-agent-core` (agent runtime with tool calling and state management), and higher-level apps like `pi-coding-agent`. citeturn12view0turn12view2

Relevant to your use case:

- `pi-agent-core` exposes an Agent API with `prompt()`, `steer()`, `followUp()`, `abort()`, and explicit state mutators—useful if you want the Forge UI to interrupt or queue follow-ups mid-job. citeturn16view2  
- The project has documented reliability issues typical of agent loops, e.g., a reported scenario where `pi-agent-core` could wedge indefinitely if streaming never reaches a terminal event or a tool promise never resolves (highlighting the need for timeouts and fail-closed behavior). citeturn16view3

A particularly interesting path for Python-first refactoring is the **Python package `pi-agent-core`**, which describes itself as a stateful, LLM-agnostic agent loop with tool execution, event streaming, steering/follow-up queues, cancellation, and a “proxy transport.” Its PyPI page explicitly states it is **a Python port of the TypeScript `@mariozechner/pi-agent-core`** design. citeturn17view0turn16view0

This makes Pi attractive in two ways:

- You can keep the current Python server stack while adopting a more standardized agent-loop abstraction (state + events + tool dispatch) that aligns with your “headless harness” concept. citeturn17view0turn20view2  
- You can later switch the implementation to TypeScript pi-agent-core (or vice versa) while keeping the same mental model (tools + event stream + steering/follow-up). citeturn12view0turn16view2turn17view0

Caveat: the Python port is flagged as “Alpha” and is maintained by a third party (not the original pi-mono maintainer), so you should plan for either (a) forking/vendorizing or (b) treating it as architectural inspiration rather than a hard dependency. citeturn17view0turn16view0

### LangGraph / LangChain ecosystem

LangGraph is positioned as an agent-orchestration layer focused on durable execution, streaming, and human-in-the-loop workflows (with the option to use LangChain tools/models but not strictly required). citeturn18search17

Practically, LangGraph supports streaming custom progress data from inside nodes/tools using a stream writer, which maps well onto your current SSE usage pattern. citeturn18search0turn8view0 It also documents a clear representation of tool calls (`name`, `args`, `id`), consistent with tool-calling agent patterns. citeturn18search1turn18search7

Trade-off: LangGraph adds conceptual overhead (graphs/state machines) that may be unnecessary if your loop is mostly “single-agent with tools” and you mainly want separation + better state/events.

### PydanticAI

PydanticAI is a Python-native agent framework with strong ergonomics for tools (decorators), plus “toolsets” and additional features like human-in-the-loop tool approval and durable execution (as described in its docs). citeturn18search3turn18search9turn18search12

This is attractive as a “Python-first, typed tools” path that stays close to your existing Pydantic usage (`pydantic-settings`, Pydantic models for requests/events). citeturn29view0turn8view0

### LlamaIndex agents

LlamaIndex documents agents as reasoning engines that can select tools and optionally use memory modules, and it has a broad tool ecosystem (especially around retrieval). citeturn18search5turn18search2

However, if your core need is reliable filesystem tool execution + streaming lifecycle events (not RAG), LlamaIndex may be heavier than necessary.

### Codex App Server as an architecture reference point

Even if you don’t adopt it directly, **Codex App Server** is an important architectural precedent: a dedicated “agent harness” process exposing a bidirectional protocol to clients, enabling authentication, conversation history, approvals, and streamed events—explicitly to decouple UI from agent logic. citeturn28search0turn28search12turn28search4

This is conceptually aligned with what you want for “headless Opencode”-like behavior: a stable server-side agent runtime that multiple UIs (Forge now; other clients later) can talk to.

### Comparative fit summary

| Option | Language/runtime | Strength for your use case | Key risks |
|---|---|---|---|
| Keep current custom loop (refactor only) | Python | Least moving parts; already integrated with your tools + SSE + OpenAI-compatible endpoint citeturn20view2turn8view0turn31view0 | You must continue owning loop correctness (timeouts, retries, steering) and abstraction boundaries. |
| `pi-agent-core` (Python port) | Python | Ready-made agent-loop abstraction with events, tools, steering/follow-up; explicitly mirrors Pi’s design citeturn17view0turn16view0 | Alpha maturity and third-party maintenance; may require vendoring. citeturn17view0 |
| pi-mono (`pi-ai` + `pi-agent-core`) | Node/TypeScript | Mature multi-provider tooling + rich agent events and state API citeturn12view2turn16view2turn16view1 | Multi-runtime complexity (Node + Python or rewrite), and known edge cases around hangs if not bounded. citeturn16view3 |
| LangGraph | Python | Strong streaming and orchestration primitives; built for durable/HITL patterns citeturn18search17turn18search0 | Added conceptual weight if you don’t need multi-step graphs. |
| PydanticAI | Python | Very natural for typed tools + approval/durable execution citeturn18search3turn18search9 | You’ll still need to design your vault tool policy and streaming UX carefully. |
| LlamaIndex agents | Python | Broad agent + tool ecosystem, especially for retrieval citeturn18search5turn18search2 | Overkill unless you commit to heavy RAG/memory workflows. |

## Proposed target architecture and library boundaries

This section describes one recommended “future state” that satisfies your three-library goal while minimizing friction with your current working system.

### Forge

**Purpose**: A minimal web UI (chat-like command box + status feed) that runs on the vault machine and is reachable over your tailnet; it also acts as a reverse proxy to the Kiln dev server so all UI + site + APIs share one origin.

**Key design choice**: **inject UI into HTTP responses, not into generated files.** This replaces today’s `inject_overlay(site_dir)` post-processing pass. citeturn20view0turn8view0

**How Forge “builds on `kiln dev`” (concretely)**:

- Forge spawns/supervises `kiln dev` (configured input/output/port) as a child process and proxies all non-API traffic to it. Kiln docs describe `dev` as the combined “build/watch/serve” loop. citeturn26view0turn21view0  
- Forge injects a `<link>` + `<script>` (or a single `<script type="module">`) into proxied HTML responses so every page gets the same UI primitives. This parallels your current injection, but at the HTTP layer. citeturn20view0turn11view0  
- Because Kiln uses HTMX navigation, Forge’s injected JS must initialize on both first load and on `htmx:afterSwap`. citeturn11view0

**Minimal public surface** (as a library):

- `ForgeServer(config).run()` (starts proxy + API + UI assets + supervises kiln dev)
- a small typed “job/events” contract (shared with agent library)

### Obsidian LLM interaction library

**Purpose**: Provide the server-side interaction contract for “LLM ↔ vault,” including tool policy, concurrency control, versioning strategy, and event streaming.

**A strong refactor target is to extract today’s `ToolRuntime` + versioning adapter + agent loop behind interface boundaries:**

- `VaultAdapter` (read/write/list/search/rename/etc.)  
- `HistoryAdapter` (`commit`, `undo`, `diff`, `log`) — currently Jujutsu-backed citeturn8view0turn31view1  
- `AgentRunner` (tool calling loop + timeouts + model config) citeturn20view2turn29view0  
- `EventSink` (emits structured events that Forge streams to the browser)

This is where adopting a framework can pay off:

- If you adopt **Python `pi-agent-core`**, it already models the agent as a stateful wrapper around an `agent_loop()` with tool execution and a two-level event system (agent lifecycle events + assistant streaming primitives). citeturn17view0turn16view0  
- If you keep your current architecture, implement two missing hardening items that Pi’s ecosystem and issues highlight: **bounded tool execution** and **bounded model streaming** (timeouts, fail-closed). citeturn16view3turn20view2

### Future obsidian-ops (orchestration library)

**Purpose**: Wire Forge and the agent library together and provide a coherent “product” entrypoint (CLI + settings + defaults). In the future, this may add richer workflows (queue policies, multi-user sessions), but initially it should mostly do dependency injection.

Concretely, this layer would:

- load settings (vault path, model config, versioning config, kiln config),  
- construct `AgentService` (vault tools + LLM runner),  
- construct `ForgeServer` and pass the `AgentService` to its `/api/*` routes.

### End-to-end flow diagram

```mermaid
flowchart LR
  subgraph Client["Browser on tailnet"]
    Page["Kiln-rendered page"]
    Overlay["Forge overlay UI (injected JS)\n- command input\n- status stream\n- optional steer/follow-up"]
  end

  subgraph Forge["Forge (reverse proxy + API gateway)"]
    Proxy["HTTP reverse proxy\nHTML response injection"]
    API["/api/* endpoints\njobs + SSE"]
    KilnProc["Supervised child process:\nkiln dev --input VAULT --output PUBLIC --port P"]
  end

  subgraph AgentSvc["Obsidian LLM interaction service"]
    Runner["Agent runner\n(tool-calling loop, timeouts)"]
    Tools["Vault tools runtime\n(read/write/list/search/etc.)"]
    History["VCS adapter\n(commit/undo/diff/log)"]
  end

  subgraph FS["Local filesystem"]
    Vault["Obsidian vault directory"]
    Public["Kiln output directory"]
  end

  Page <-- HTMX nav --> Proxy
  Overlay -->|POST /api/jobs| API --> Runner
  Runner --> Tools --> Vault
  Runner --> History --> Vault
  Vault -->|file changes| KilnProc --> Public
  API -->|SSE /api/jobs/{id}/stream| Overlay
  Proxy -->|proxies site| KilnProc
```

This diagram is grounded in: current obsidian-ops’ job/SSE model and tool-calling loop citeturn8view0turn20view2turn31view0, plus Kiln’s documented `dev` workflow (build + watch + serve) and HTMX navigation constraints. citeturn26view0turn21view0turn11view0

### Mapping current obsidian-ops modules to the proposed split

| Current module | Future home | Rationale |
|---|---|---|
| `app.py` citeturn8view0 | Forge (server/proxy) + obsidian-ops (wiring) | Today it combines serving + API + worker. Split proxy/UI from agent orchestration. |
| `inject.py` citeturn20view0 | Forge | Replace disk rewrite with HTTP response injection (or optional Kiln templating/custom mode). |
| `rebuild.py` citeturn19view0 | Forge (process supervision) | Replace `kiln generate` per job with supervised `kiln dev`. |
| `agent.py` citeturn20view2 | Obsidian LLM interaction | Core agent loop belongs in the agent service library. |
| `tools.py` + `fs_atomic.py` (via usage) citeturn20view3turn31view2 | Obsidian LLM interaction (possibly a subpackage like `vault_ops`) | Vault safety guarantees are core to the agent domain, independent of UI. |
| `queue.py` | Either (a) agent library or (b) obsidian-ops wiring | If Forge becomes a thin gateway, job queue may live with agent service; if Forge owns API, queue can stay there but depend only on agent interface. |
| `page_context.py` | Forge + agent shared utility | Needed to translate URL context to vault file paths when the user submits a command. citeturn8view0 |

## Migration roadmap and risk analysis

A pragmatic refactor sequence (minimizing big-bang rewrites) is:

Start by extracting stable interfaces  
Define a small internal protocol: `JobRequest (instruction, current_url_path, maybe current_file_path)` and `AgentEvent` types that can be streamed over SSE. This matches your current `/api/jobs` + `/api/jobs/{id}/stream` shape. citeturn8view0turn20view2

Lift “vault ops + policy” into its own library  
Move `ToolRuntime` and filesystem safety primitives into “Obsidian LLM interaction” as the first standalone package. Keep behavior identical: path validation, per-file locks, atomic writes, and the existing tool set. citeturn20view3turn31view0

Swap rebuild strategy from `kiln generate` to supervised `kiln dev`  
Introduce a Forge prototype that launches `kiln dev` and proxies it. Use Kiln’s own config discovery (`kiln.yaml`) to simplify and stabilize. citeturn26view0turn9view0  
At this point you can delete or deprecate `KilnRebuilder.rebuild()` and the “rebuild after every job” logic (while still keeping “commit/undo” in the agent service). citeturn19view0turn8view0

Replace disk-based injection with proxy-based injection  
Implement HTML response modification in Forge rather than mutating every output file, eliminating the need for `inject_overlay(site_dir)` entirely. citeturn20view0turn21view0

Harden the agent loop with bounded execution  
If you keep your custom loop, add explicit timeouts for both model requests and tool execution (the Pi ecosystem has highlighted the failure mode where missing terminal events can wedge an agent loop). citeturn16view3turn20view2  
If you adopt `pi-agent-core` (Python), validate that its cancellation/timeout story matches your requirements; it documents cooperative cancellation and an explicit abort/reset model. citeturn17view0turn16view0

Security and prompt-injection stance for network tools  
Today’s toolset includes `fetch_url`, which returns remote text into the agent context (capped at 120KB but still untrusted). citeturn31view0turn31view1 In agent literature, this can enable indirect prompt injection; if you keep `fetch_url`, treat its output as untrusted and consider adding filtering/quoting, or require explicit approval for it. citeturn15academia40turn15academia41

Key risks to plan for:

- HTMX navigation edge cases: injected overlay must survive partial swaps and not depend on `DOMContentLoaded` alone. citeturn11view0  
- Kiln dev “incremental” limitations: current docs indicate that rebuild triggers may still run a full generation, and the dependency graph may not update dynamically. This affects your perceived latency after agent edits. citeturn21view0  
- Multi-runtime complexity if choosing TypeScript pi-mono directly: powerful, but adds operational surface area (Node process + Python process or rewrite). citeturn12view0turn12view2  
- Authentication: current obsidian-ops endpoints appear unauthenticated in `app.py`; with tailnet-only assumptions this may be acceptable initially, but consider at least a shared secret header or tailnet ACL-based restriction as you productize. citeturn8view0

## Prioritized references and primary sources

Primary sources for current obsidian-ops behavior  
- Attached deep research report summary of current end-to-end flow (UI overlay + SSE + Jujutsu + Kiln rebuild loop). fileciteturn0file0L5-L33  
- `app.py` (FastAPI lifespan, routes, SSE stream, static mounts, clean URL rewriting). citeturn8view0  
- `rebuild.py` (`kiln generate` wrapper). citeturn19view0  
- `inject.py` (HTML file injection of `/ops/ops.css` + `/ops/ops.js`). citeturn20view0  
- `agent.py` (OpenAI-compatible tool-calling loop via `openai.AsyncOpenAI`). citeturn20view2  
- `tools.py` (tool runtime, including `fetch_url` size cap and tool definitions). citeturn31view0turn31view1  
- `pyproject.toml` (Python ≥3.13 and core dependencies). citeturn29view0  
- Commit history (dates and stepwise build-up, April 4–5 2026). citeturn30view0turn6view0  

Primary sources for Kiln features Forge should build on  
- Kiln homepage (scope, HTMX client-side navigation, single-binary claim). citeturn4view0  
- Kiln `dev` command doc (build + watch + serve, flags, watcher, dependency graph). citeturn26view0  
- Incremental Builds doc (pipeline details and current limitations). citeturn21view0  
- HTMX navigation notes (must listen to HTMX events, not only `DOMContentLoaded`). citeturn11view0  
- Custom Mode templating (optional “native injection” path). citeturn10view0  

Primary sources for agent framework options  
- pi-mono package inventory (pi-ai, pi-agent-core, etc.). citeturn12view0  
- pi-ai README (tool calling + streaming/event model). citeturn12view2  
- pi-agent-core API surface (`prompt`, `steer`, `followUp`, `abort`, etc.). citeturn16view2turn16view1  
- pi-agent-core hang risk discussion (need for timeouts/fail-closed behavior). citeturn16view3  
- Python `pi-agent-core` PyPI page (agent loop architecture + explicit “Python port” statement). citeturn17view0  
- LangGraph: durable execution/streaming positioning and custom streaming events. citeturn18search17turn18search0turn18search1  
- PydanticAI: tools registration/toolsets and HITL/durable execution claims. citeturn18search3turn18search9turn18search12  
- LlamaIndex: definition of agents and tools. citeturn18search5turn18search2  
- Codex App Server as a “headless harness” reference architecture (protocol + streamed events + approvals). citeturn28search12turn28search0turn28search4