# Implementation Guide — Plan

## Deliverable

A single `GUIDE.md` that provides a complete implementation reference for obsidian-ops.

## Planned Sections

1. Executive summary and implementation posture
2. Prerequisites and project setup
3. Module-by-module implementation (in build order)
4. Integration wiring (app.py)
5. Browser overlay (ops.js, ops.css)
6. End-to-end mutation flow walkthrough
7. Testing strategy and test code
8. Manual acceptance checklist
9. Operational notes

## Implementation Order (from Architecture)

1. config.py
2. models.py
3. locks.py
4. fs_atomic.py
5. history_jj.py
6. rebuild.py
7. page_context.py
8. inject.py
9. tools.py
10. agent.py
11. queue.py
12. app.py
13. static/ops.css
14. static/ops.js
15. tests

## Key Changes from Previous Guide

- All subprocess calls (jj, kiln) must use asyncio.to_thread() or async subprocess
- Server binds to 127.0.0.1 by default
- Worker concurrency locked to 1 (no ambiguity)
- Content size guards on read_file (256KB soft, 1MB hard)
- Python version is 3.13+
- Undo is global jj undo (not per-file)

## Status

Pending — guide not yet written.
