# Obsidian Ops — Decisions

## D1: Jujutsu as the sole durable history layer

**Decision:** Use Jujutsu exclusively for durable history, undo, diff, and restore.

**Rationale:** The canonical direction explicitly rejects Git-first, SQLite-backed, or hybrid history models. Jujutsu provides clean change boundaries (`jj commit`), predictable undo (`jj undo`), and file history (`jj log`) with minimal wrapper complexity.

**Alternatives considered:**
- Git as primary VCS interface — rejected per canonical direction
- SQLite-backed history ledger — rejected (adds unnecessary weight)
- Custom snapshot store — rejected (duplicates VCS responsibilities)

## D2: In-memory job queue

**Decision:** Jobs are stored in memory only. Loss on restart is acceptable.

**Rationale:** v0 is local-first, single-user. Durable content history comes from Jujutsu, not the queue. Keeping the queue in memory simplifies the architecture significantly.

## D3: Generic job API, no command-specific endpoints

**Decision:** Only `POST /api/jobs`, `GET /api/jobs/{id}/stream`, `GET /api/jobs`, `POST /api/undo`, `GET /api/history`.

**Rationale:** The product accepts intent, not commands. Avoids endpoint proliferation and command taxonomy.

## D4: One `jj commit` per successful job

**Decision:** Each successful mutating job performs exactly one `jj commit -m "<summary>"`.

**Rationale:** Creates a clean, predictable history boundary. Makes `jj undo` reliable for v0 undo semantics.

## D5: `ty` as type checker instead of mypy

**Decision:** Use Astral's `ty` for type checking.

**Rationale:** 10-100x faster than mypy, from the same team as Ruff (already in the toolchain), modern Rust-based implementation.

## D6: Coarse full rebuilds after mutations

**Decision:** Run `kiln generate` for the entire vault after successful writes.

**Rationale:** Simpler implementation. Acceptable for v0 vault sizes. Can optimize to incremental rebuilds later if latency becomes a usability problem.

## D7: Default worker concurrency = 1

**Decision:** Start with a single worker.

**Rationale:** Simplifies Jujutsu undo expectations, rebuild sequencing, debugging, and user mental model. Can raise later if needed.
