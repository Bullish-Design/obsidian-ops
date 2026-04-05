# Obsidian Ops — Assumptions

## Product Audience

- Single local user managing their own Obsidian vault
- Trusted local environment (no auth required)
- User is comfortable with markdown-based note-taking

## User Scenarios

- Clean up / reorganize a note
- Summarize a page into a new note
- Find related notes and add links
- Save a URL as a source note with summary
- Build an index page from a folder
- Undo a bad result

## Constraints

- Local-first, single-user deployment
- Python 3.13+
- FastAPI as the web framework
- Kiln as the vault renderer
- Jujutsu as the durable history / undo layer
- vLLM providing an OpenAI-compatible Chat API endpoint
- In-memory job queue (loss on restart is acceptable)
- Low worker concurrency (default: 1)

## Invariants

- Vault markdown files are the canonical source of truth
- All file writes must be atomic
- All successful mutations must be recorded in Jujutsu history
- All successful mutations must trigger a Kiln rebuild
- Per-file locks prevent concurrent mutations to the same file
- No command-specific public API endpoints — only generic job submission
- No database-backed job system in v0
- No selection-toolbar UX in v0

## Technical Assumptions

- The vault is already inside a Jujutsu workspace (`.jj/` exists)
- The site output directory can be blown away and regenerated
- URL-to-file path inference works by mirroring vault structure (v0 simplicity)
- One `jj commit` per successful app job for clean undo semantics
