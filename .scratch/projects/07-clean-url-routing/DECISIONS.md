# Clean URL Routing — Decisions

1. Implemented clean URL handling as middleware in the app layer.
   - Rationale: keeps generated site untouched and fixes routing centrally without requiring kiln output changes.
2. Scoped rewrites to non-API/non-ops GET/HEAD requests without suffixes.
   - Rationale: avoids interfering with API endpoints, overlay static assets, and direct file requests.
