# Clean URL Routing — Assumptions

- Generated Kiln output uses `*.html` files for many leaf pages.
- Browser/nav links use extensionless paths (e.g. `/guides/getting-started`).
- Server should map extensionless paths to `.html` or `/index.html` without affecting `/api` and `/ops`.
