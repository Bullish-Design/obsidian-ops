# Plan

NO SUBAGENTS: All implementation, testing, and git operations will be done directly in this session.

1. Step 0: Overhaul `pyproject.toml`, scaffold `__init__.py` + `conftest.py`, sync deps, validate baseline, commit, push.
2. Step 1: Implement `errors.py`, export exceptions, validate, commit, push.
3. Step 2: Implement `lock.py` + `tests/test_lock.py`, validate, commit, push.
4. Step 3: Implement `sandbox.py` + `tests/test_sandbox.py`, validate, commit, push.
5. Step 4: Implement `search.py` + `tests/test_search.py`, validate, commit, push.
6. Step 5: Implement `vault.py` core file ops + `tests/test_vault.py`, validate, commit, push.
7. Step 6: Implement `frontmatter.py` + frontmatter vault methods + `tests/test_frontmatter.py`, validate, commit, push.
8. Step 7: Implement `content.py` + content vault methods + `tests/test_content.py`, validate, commit, push.
9. Step 8: Implement `vcs.py` + VCS vault methods + `tests/test_vcs.py`, validate, commit, push.
10. Step 9: Finalize public API exports in `__init__.py`, run full validation + coverage, commit, push.
11. Step 10: Implement optional HTTP server + `tests/test_server.py`, validate, commit, push.
12. Step 11: Run full integration cleanup checks (tests, coverage, ruff), final commit, push.

NO SUBAGENTS: This plan must be executed directly without delegation.
