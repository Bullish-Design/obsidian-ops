# Obsidian Ops — Concept Review

## 1. Review summary

The Obsidian Ops concept describes a **local-first, agent-driven operations overlay** for an Obsidian vault rendered as a website through Kiln. The user interacts through a single floating action button and modal, issuing natural-language instructions that a tool-using LLM agent executes against vault markdown files. Jujutsu provides durable history, undo, and recovery. The system is deliberately minimal: no database, no command registry, no selection toolbar, no structured workflow engine.

The concept is **coherent, well-scoped, and architecturally sound** for its stated goals. The documentation is unusually thorough for a v0 product — bordering on over-specified in places — but the core ideas are strong. The following review examines strengths, risks, gaps, internal contradictions, and areas where the documentation could be tightened.

---

## 2. What the concept gets right

### 2.1 Radical simplification as a product decision

The single strongest aspect of this concept is its disciplined rejection of complexity. The documentation repeatedly and explicitly rules out:

- command registries
- database-backed job systems
- hybrid history layers
- selection toolbars
- command-specific API endpoints

This is not accidental omission — it is a deliberate architectural stance. The concept understands that most small tools die from premature structure, and it actively guards against that. The "do not reintroduce these" sections in the implementation guide and canonical direction document are valuable guardrails.

### 2.2 The agent-first interaction model

Centering the product on a natural-language agent loop rather than a command taxonomy is the right call for a single-user local tool. It means:

- the tool surface stays small (7 tools)
- the API stays small (5 endpoints)
- the UI stays small (1 FAB + 1 modal)
- new capabilities emerge from the agent's reasoning, not from new code paths

This is a genuine architectural advantage. Adding "find related notes and link them" does not require a new endpoint, a new command handler, or a new UI element — it just requires the agent to use existing tools well.

### 2.3 Jujutsu as the durability substrate

Delegating all durable history to Jujutsu is a clean decision. It avoids:

- inventing a second version-control system
- managing SQLite migration complexity
- duplicating diff/restore logic

The "one `jj commit` per successful job" rule is particularly well-chosen. It creates clean, predictable undo boundaries and maps 1:1 to user-visible operations. This is the kind of simple invariant that makes the system easy to reason about.

### 2.4 Clear separation of durable vs. ephemeral state

The concept is explicit about what survives restart (vault files, Jujutsu history) and what does not (in-memory jobs, SSE streams, modal state). This clarity prevents the common trap of accidentally treating transient state as durable.

### 2.5 The mutation flow is well-ordered

The write protocol (acquire lock -> atomic write -> jj commit -> kiln generate -> SSE done) is a clean, linear pipeline. The distinction between "fail before write" and "fail after write" is explicitly documented, and the partial-success model (write succeeded but rebuild failed) is handled correctly.

---

## 3. Risks and concerns

### 3.1 Heavy dependence on LLM quality for core product value

The entire product value proposition rests on the local LLM (via vLLM) being good enough to:

- correctly interpret natural-language instructions
- use the 7-tool surface reliably
- produce clean markdown output
- avoid destructive edits when not requested
- summarize its own actions coherently

With a cloud-hosted frontier model, this would be a reasonable bet. With a local vLLM model, the quality ceiling is significantly lower. The concept does not address:

- **What happens when the model produces bad output?** The system prompt says "prefer minimal edits" and "do not delete content unless the user clearly intends it," but enforcement is entirely on the model's shoulders. There is no programmatic guardrail against the model rewriting an entire note when asked to "fix a typo."
- **What happens when the model fails to use tools correctly?** Malformed tool calls, hallucinated file paths, and incorrect JSON arguments are common with smaller models. The agent loop has a max-iterations guard but no per-tool validation beyond Pydantic parsing.
- **Model selection guidance is absent.** The concept specifies vLLM with an OpenAI-compatible API but says nothing about minimum model quality, recommended models, or how to evaluate whether a model is good enough for this use case.

**Recommendation:** Add a section on model requirements and quality expectations. Consider adding a lightweight validation layer between the agent's proposed writes and actual file mutation (e.g., a diff preview step, or a "dry run" mode that shows proposed changes before committing).

### 3.2 The search implementation is naive

The `search_files` tool does a linear scan of all vault files matching a glob, performing case-insensitive substring search with a 240-character context window. For a vault of 10,000 files (the stated reference size), this will be slow.

More critically, the search is purely lexical. The agent cannot perform semantic search, tag-based filtering, or frontmatter queries. For instructions like "find related notes," the agent must rely on keyword guessing — which may work passably with a good model but will be fragile.

**Recommendation:** This is acceptable for v0, but the concept should acknowledge it as a known limitation and identify it as an early optimization target. A pre-built search index (even something simple like a trigram index) would dramatically improve the agent's ability to find relevant context.

### 3.3 Coarse rebuilds may become a usability bottleneck

The spec targets p50 ≤ 2s for 1,000-note vaults and p50 ≤ 8s for 10,000-note vaults. These targets are for the rebuild step alone. Combined with agent execution time (multiple LLM round-trips) and the jj commit step, end-to-end latency for a single job could easily reach 15-30 seconds for a medium vault.

Since rebuilds are triggered after every successful mutation, and the default worker concurrency is 1, this means the system can process roughly 2-4 jobs per minute at scale. This is fine for the intended use case (occasional note operations), but the concept should be explicit about this throughput ceiling.

**Recommendation:** Document expected end-to-end job latency ranges. Consider whether the rebuild step can be made non-blocking (rebuild in the background, serve stale content, notify when fresh).

### 3.4 The undo model has a subtle fragility

The undo model relies on `jj undo`, which reverses the most recent Jujutsu operation. With a single worker and one commit per job, this works cleanly. But the concept itself mentions that concurrency can be raised later, and the spec recommends a default of 2-3 workers.

If two jobs commit in sequence (Job A commits, then Job B commits), and the user clicks "undo" expecting to reverse Job A, they will actually reverse Job B. The current undo model is **last-operation, not per-file or per-job**.

The concept partially addresses this by defaulting to 1 worker, but the spec document (Section 13.4) recommends 2-3 workers, creating an internal contradiction.

**Recommendation:** Lock the default to 1 worker and make the undo limitation explicit. If concurrency is raised, undo semantics must be redesigned (likely requiring `jj restore` with specific change IDs rather than `jj undo`).

### 3.5 No authentication or access control

The concept explicitly states "no app auth" and "trusted local environment." This is reasonable for a truly local deployment, but the system serves HTTP on a network port. On a shared machine or a machine with any network exposure, this means any process or user on the network can:

- submit jobs that mutate vault files
- trigger undo operations
- read arbitrary vault content through the API

**Recommendation:** At minimum, bind to `127.0.0.1` by default (not `0.0.0.0`). Consider a simple shared-secret or token auth mechanism for the API endpoints, even if it is optional.

---

## 4. Internal contradictions and inconsistencies

### 4.1 Worker concurrency: 1 vs. 2-3

- `DECISIONS.md` (D7): "Default worker concurrency = 1"
- `ASSUMPTIONS.md`: "Low worker concurrency (default: 1)"
- `config.py` implementation: `worker_concurrency: int = Field(default=1)`
- Spec Section 13.4: "max concurrency set low, recommended default 2 or 3"
- Spec TR-JOB-001: "Default worker concurrency must be 2"
- Spec TR-JOB-002: "The system must support 3 concurrent jobs"

The canonical direction and implementation guide lock this to 1. The spec says 2-3. The implementation follows the canonical direction (correct), but the spec has not been updated to match.

### 4.2 Python version: 3.12 vs. 3.13

- Implementation guide Section 3: "Python 3.12"
- `ASSUMPTIONS.md` and `CONTEXT.md`: "Python 3.13+"

Minor inconsistency. The implementation should target 3.13 per the project-level assumptions.

### 4.3 Undo API shape

- Spec Section 12.4: Undo request includes `file_path` or `change_id`
- Implementation guide Section 16: Undo endpoint takes no body, performs a global `jj undo`
- Canonical direction: "undo the most recent relevant change"

The spec envisions per-file or per-change undo. The implementation performs global undo. These are different semantics.

### 4.4 The spec has not been fully aligned with the canonical direction

The canonical direction document (Section 9) itself notes that the spec, architecture, README, and implementation guide all need alignment. The spec in particular retains:

- references to 2-3 worker concurrency
- a `POST /api/rebuild` endpoint not present in the canonical API surface
- protected-path configuration not mentioned elsewhere
- concurrency test requirements (TR-JOB-002, TR-TEST-003) that assume multi-worker operation

The spec appears to represent an earlier, slightly more ambitious version of the product that has not been fully reconciled with the simplified canonical direction.

---

## 5. Documentation assessment

### 5.1 Redundancy

The 11 documents contain substantial repetition. The core product loop ("render vault -> open modal -> describe intent -> run agent -> mutate files -> record history -> rebuild -> refresh or undo") is restated verbatim in at least 7 documents. The "what this is not" list appears in 5 documents. The tool surface is defined 4 times.

This repetition was likely valuable during the concept development process (anchoring decisions across iterations), but it creates a maintenance burden. If a decision changes, it must be updated in many places.

**Recommendation:** For implementation purposes, treat `CANONICAL_DIRECTION_SIMPLIFIED_OBSIDIAN_OPS.md` as the authoritative document. Treat the implementation guide as the build reference. Treat the spec as a source of detailed requirements (particularly Section 30 metrics and Section 31 functional requirements) but be aware it has not been fully aligned.

### 5.2 What is well-documented

- Architectural decisions and their rationale
- Non-goals and explicit exclusions
- The mutation/write protocol
- Failure modes and recovery model
- Testing strategy (unit, integration, acceptance)
- Performance metrics and targets (spec Section 30)
- Functional requirements (spec Section 31)

### 5.3 What is under-documented

- **Model requirements and quality expectations** — no guidance on what local LLM capabilities are needed
- **Kiln specifics** — Kiln is referenced throughout but its CLI interface, configuration, and behavior are never specified. The concept assumes `kiln generate --input <vault> --output <site>` without verifying this is the actual API.
- **Error recovery UX** — what does the user see and do when the agent produces bad output that was already committed? The undo flow covers the mechanism, but the user-facing guidance is thin.
- **Deployment and startup** — how does the user actually start the system? The concept mentions environment variables but no CLI entrypoint, systemd unit, or startup script.
- **Vault structure assumptions** — the spec mentions `Sources/`, `Notes/`, `Projects/`, `Templates/` directories but does not specify whether these are required, recommended, or just examples.
- **Content size limits** — the spec mentions TR-AGENT-002 (256 KB soft / 1 MB hard) but the tools implementation has no size guards.

---

## 6. Architectural observations

### 6.1 The synchronous Jujutsu and Kiln calls are a bottleneck

Both `history_jj.py` and `rebuild.py` use synchronous `subprocess.run()` calls. In an async FastAPI application with async workers, these blocking calls will tie up the event loop during:

- `jj commit` (up to 120s timeout)
- `jj undo` (up to 120s timeout)
- `kiln generate` (up to 180s timeout)

With a single worker, this is tolerable but suboptimal. With multiple workers, it would starve the event loop.

**Recommendation:** Wrap subprocess calls in `asyncio.to_thread()` or use `asyncio.create_subprocess_exec()`.

### 6.2 The overlay injection model is fragile

The `inject.py` approach of string-replacing `</head>` or `</body>` in HTML files after every rebuild is simple but:

- it modifies files on disk, which could interfere with caching or content hashing
- it must re-run after every rebuild, adding latency
- it assumes Kiln output contains `</head>` or `</body>` tags

A middleware-based injection (inserting the overlay at serve time rather than at build time) would be more robust and would not require post-build file modification.

### 6.3 The page context resolver is minimal but brittle

The `infer_markdown_path_from_url` function makes assumptions about how Kiln maps vault paths to URLs. If Kiln uses any non-trivial URL scheme (slugification, flattening, custom routing), this will break silently and the agent will operate on the wrong file or fail to resolve context.

**Recommendation:** This is acknowledged as a known simplification. When Kiln exposes a source manifest or reverse-lookup API, replace this immediately.

---

## 7. Feasibility assessment

### 7.1 Is this buildable?

Yes. The concept describes a system of approximately 10-12 Python modules, 2 static assets, and 5 API endpoints. The implementation guide includes complete reference code for every module. The project has already been scaffolded (per `CONTEXT.md` and `PROGRESS.md`) with all source files created.

The remaining work is testing and validation.

### 7.2 Is this useful?

Conditionally. The product value depends almost entirely on the quality of the local LLM. With a capable model (e.g., a 70B+ parameter model with strong tool-use capabilities), this could be a genuinely useful daily tool for vault maintenance. With a weaker model, it will produce frustrating results that the user must undo frequently.

The concept is honest about this dependency but does not provide guidance on the minimum viable model quality.

### 7.3 Is this maintainable?

Yes. The deliberately small codebase (~12 files, no database, no migration system) is easy to reason about. The clear boundary between durable state (vault + Jujutsu) and ephemeral state (everything else) means the system can always be recovered by restarting the server.

### 7.4 Estimated scope to v0

Based on the scaffolded code and remaining tasks (unit tests, integration tests, manual acceptance):

- Testing and validation: moderate effort
- First real-vault acceptance: depends on model quality and Kiln/Jujutsu setup
- The concept is well within reach of a single developer

---

## 8. Recommendations

### 8.1 Critical (address before shipping v0)

1. **Wrap subprocess calls in async.** The synchronous `subprocess.run()` calls for Jujutsu and Kiln will block the event loop. Use `asyncio.to_thread()` or `asyncio.create_subprocess_exec()`.

2. **Bind to 127.0.0.1 by default.** The concept says "local-first" but does not specify the bind address. Binding to all interfaces by default would be an unnecessary security exposure.

3. **Reconcile worker concurrency.** Lock the default to 1 across all documents. If the spec's concurrency test requirements are retained, document that they apply to a future version.

### 8.2 Important (address early in v0 lifecycle)

4. **Add model quality guidance.** Document minimum recommended model capabilities (tool-use support, context window size, instruction-following quality). Provide a known-good model recommendation.

5. **Add content size guards to tools.** The spec requires them (TR-AGENT-002). The implementation currently reads files of any size into memory and sends them to the model without limit.

6. **Add a diff preview or dry-run mode.** Given the dependence on LLM quality, giving the user a chance to review proposed changes before they are committed would significantly increase trust in the system.

7. **Harden the undo semantics documentation.** Make it explicit that undo reverses the single most recent Jujutsu operation, and that this only works reliably with concurrency=1.

### 8.3 Nice-to-have (post-v0)

8. **Consider middleware-based overlay injection** instead of post-build file modification.

9. **Build a simple search index** to replace the linear-scan search implementation.

10. **Add a `/api/preview` endpoint** that returns proposed changes as a diff before committing.

11. **Add structured logging** per spec TR-OBS-001 (currently not implemented in the scaffolded code).

---

## 9. Verdict

The Obsidian Ops concept is a **well-designed, deliberately minimal, agent-first local tool** with a clear product identity and strong architectural discipline. Its greatest strength is its willingness to reject complexity — the "do not reintroduce these" lists are as valuable as the feature specifications.

The primary risk is the dependence on local LLM quality for core product value, which is acknowledged but not mitigated. The secondary risk is the internal inconsistency between the spec document and the canonical direction, which should be reconciled.

The concept is ready for implementation. The scaffolding is already complete. The remaining work is testing, validation, and the items identified in Section 8.1 above.
