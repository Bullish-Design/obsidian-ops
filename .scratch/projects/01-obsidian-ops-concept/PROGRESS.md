# Obsidian Ops — Progress

| Task | Status | Notes |
|------|--------|-------|
| Scaffold project structure | done | src/obsidian_ops/, tests/, static/ created |
| Create pyproject.toml | done | obsidian-ops name, ty typechecker |
| Update .tmuxp.yaml | done | Reflects obsidian-ops repo name |
| config.py | done | Settings model with from_env() |
| models.py | done | JobState, JobRequest, ProgressEvent, JobRecord, JobSummary |
| locks.py | done | PathLocks with async per-file locking |
| fs_atomic.py | done | atomic_write_text, read_text |
| history_jj.py | done | JujutsuHistory wrapper (commit, undo, history, diff) |
| rebuild.py | done | run_kiln_generate wrapper |
| page_context.py | done | infer_markdown_path_from_url |
| inject.py | done | inject_overlay for HTML files |
| tools.py | done | ToolRuntime with read/write/list/search/fetch/history |
| agent.py | done | run_agent_job with OpenAI tool-use loop |
| queue.py | done | InMemoryJobQueue with SSE subscriber support |
| app.py | done | Full FastAPI app with all routes |
| static/ops.css | done | FAB + modal styling |
| static/ops.js | done | Browser overlay with FAB, modal, SSE |
| Unit tests | pending | atomic, page_context, queue, inject |
| Integration tests | pending | API, Jujutsu |
| Manual acceptance | pending | Real vault test pass |
