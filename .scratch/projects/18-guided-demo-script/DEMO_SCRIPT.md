# Live Vault Demo Script Guide

## Table of Contents

1. Purpose and Setup
2. Runtime Paths
3. Running in Guided Mode
4. Step 01: Read the Live Note
5. Step 02: List Live Demo Files
6. Step 03: Search for "block reference"
7. Step 04: Create a New Note
8. Step 05: Update Frontmatter Fields
9. Step 06: Delete One Frontmatter Field
10. Step 07: Replace `## Agenda`
11. Step 08: Replace Paragraph Block (`^demo-block`)
12. Step 09: Replace List Item Block (`^demo-list`)
13. Step 10: Delete Temporary Note
14. Step 11: Report Lock State
15. Reset, Cleanup, and Validation

## 1. Purpose and Setup

This document mirrors the runtime behavior of `ops-live-demo run` so you can validate each step while the script is paused.

Goal:
- keep Obsidian open on the runtime vault
- run the demo in guided mode
- compare each mutation against the matching step description below
- press Enter in terminal to continue to the next step

Before running:
1. Reset runtime vault:
   - `devenv shell -- ops-live-demo reset`
2. Open this vault in Obsidian:
   - `.scratch/projects/16-live-demo-script/generated/vault`
3. Keep `live-demo/live-ops.md` open in Obsidian.

## 2. Runtime Paths

- Source vault:
  - `demo/obsidian-ops/vault`
- Runtime root:
  - `.scratch/projects/16-live-demo-script/generated`
- Runtime vault:
  - `.scratch/projects/16-live-demo-script/generated/vault`
- Primary watched file:
  - `live-demo/live-ops.md`

## 3. Running in Guided Mode

Run command:

```bash
devenv shell -- ops-live-demo run --mode guided --delay 0 --no-reset
```

Notes:
- `--mode guided` pauses after each step.
- `--delay 0` removes timed waits; you control pacing with Enter.
- `--no-reset` keeps current runtime state (use `reset` first for deterministic behavior).

Pause prompt behavior:
- After each step, script asks you to press Enter.
- While paused, inspect the vault in Obsidian and compare with the section below.

## 4. Step 01: Read the Live Note

Terminal label:
- `[Step 01] Read the live note`

What script does:
- Reads `live-demo/live-ops.md`.

Expected visible vault change:
- No file content changes.

Validation:
- Terminal prints character count read from `live-demo/live-ops.md`.

## 5. Step 02: List Live Demo Files

Terminal label:
- `[Step 02] List live-demo markdown files`

What script does:
- Lists files matching `live-demo/*.md`.

Expected visible vault change:
- No file content changes.

Validation:
- Terminal should list:
  - `live-demo/live-ops.md`
  - `live-demo/temp-to-delete.md`
  - (and later runs may include `live-demo/new-note.md`)

## 6. Step 03: Search for "block reference"

Terminal label:
- `[Step 03] Search for 'block reference' across live-demo notes`

What script does:
- Searches `live-demo/*.md` for text `block reference`.

Expected visible vault change:
- No file content changes.

Validation:
- Terminal search hits should include `live-demo/live-ops.md`.

## 7. Step 04: Create a New Note

Terminal label:
- `[Step 04] Create a new note`

What script does:
- Writes `live-demo/new-note.md` with frontmatter and generated timestamp.

Expected visible vault change:
- New file appears:
  - `live-demo/new-note.md`

Validation in Obsidian:
- Confirm file appears in file tree.
- Open file and confirm it includes title/frontmatter and a created timestamp line.

## 8. Step 05: Update Frontmatter Fields

Terminal label:
- `[Step 05] Update frontmatter fields on the live note`

What script does:
- Updates frontmatter in `live-demo/live-ops.md`:
  - `status: in-review`
  - adds/updates `last_demo_run: <timestamp>`

Expected visible vault change:
- `live-demo/live-ops.md` frontmatter changes.

Validation in Obsidian:
- Confirm `status` changed from `draft` to `in-review`.
- Confirm `last_demo_run` exists.

## 9. Step 06: Delete One Frontmatter Field

Terminal label:
- `[Step 06] Delete one frontmatter field`

What script does:
- Deletes `owner` field from frontmatter in `live-demo/live-ops.md`.

Expected visible vault change:
- `owner` is removed.

Validation in Obsidian:
- Confirm no `owner` field remains in frontmatter.

## 10. Step 07: Replace `## Agenda`

Terminal label:
- `[Step 07] Replace the ## Agenda section`

What script does:
- Replaces body under `## Agenda` with a new bullet list.

Expected visible vault change:
- Agenda items become:
  - Confirm vault path in Obsidian
  - Observe file writes
  - Observe block update
  - Observe deletion

Validation in Obsidian:
- Confirm old agenda bullets are gone.
- Confirm new four bullets are present.

## 11. Step 08: Replace Paragraph Block (`^demo-block`)

Terminal label:
- `[Step 08] Replace a paragraph block by block-id`

What script does:
- Rewrites paragraph containing `^demo-block` with timestamped text.

Expected visible vault change:
- Paragraph with marker `^demo-block` is replaced.

Validation in Obsidian:
- Find `^demo-block` and confirm updated sentence with demo timestamp.

## 12. Step 09: Replace List Item Block (`^demo-list`)

Terminal label:
- `[Step 09] Replace a list item block by block-id`

What script does:
- Replaces list item containing `^demo-list`.

Expected visible vault change:
- Item changes to:
  - `- Updated checklist item written by live demo ^demo-list`

Validation in Obsidian:
- Confirm only that list item changed.
- Adjacent list items should remain.

## 13. Step 10: Delete Temporary Note

Terminal label:
- `[Step 10] Delete the temporary note`

What script does:
- Deletes `live-demo/temp-to-delete.md`.

Expected visible vault change:
- File disappears from vault tree.

Validation in Obsidian:
- Confirm `temp-to-delete.md` is removed.

## 14. Step 11: Report Lock State

Terminal label:
- `[Step 11] Report lock state`

What script does:
- Prints `vault.is_busy()`.

Expected visible vault change:
- No file changes.

Validation:
- Terminal should print:
  - `is_busy() -> False`

## 15. Reset, Cleanup, and Validation

Reset to baseline:

```bash
devenv shell -- ops-live-demo reset
```

Cleanup runtime artifacts:

```bash
devenv shell -- ops-live-demo cleanup
```

Check runtime state:

```bash
devenv shell -- ops-live-demo status
```

Expected post-cleanup status:
- `Exists: False` for runtime vault.
