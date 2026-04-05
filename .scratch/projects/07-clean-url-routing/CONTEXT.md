# Clean URL Routing — Context

- Issue reproduced: extensionless leaf page URLs return 404 while corresponding `*.html` exists in generated site.
- Implemented:
  - Clean URL rewrite middleware in `src/obsidian_ops/app.py` for extensionless non-API/non-ops GET/HEAD requests.
  - Middleware maps `/path` to `/path.html` when present, else `/path/` when `index.html` exists.
  - Regression tests in `tests/test_api.py` for leaf and directory clean URLs.
- Verification:
  - `devenv shell -- pytest tests/test_api.py -v` passed.
  - `devenv shell -- pytest tests/ -q` passed.
- Next action: commit and push.
