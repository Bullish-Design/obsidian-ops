# obsidian-ops Test Suite Improvement Guide

## Preface

A code review of the refactored `obsidian-ops` library (see project 14) identified that while the existing 108-test suite achieves 90% coverage and all tests pass, there are meaningful gaps — particularly around real-world integration testing, server endpoint coverage, and edge-case validation. This guide provides a complete, step-by-step plan for improving the test suite to production quality.

### Current State

| Metric | Value |
|--------|-------|
| Tests | 108 passing |
| Coverage | 90% overall |
| Lowest module | `server.py` at 73% |
| Bug found | `find_block` regex boundary assertions non-functional (BUG-1) |
| Test style | Unit tests with `tmp_path` fixtures; VCS mocked via `unittest.mock` |

### Goals

1. **Fix BUG-1** in `content.py` and add regression tests
2. **Add real-world integration tests** with on-disk before/after snapshots for every public `Vault` method
3. **Close server coverage gaps** — bring `server.py` from 73% to ≥90%
4. **Add edge-case tests** for uncovered code paths
5. **Generate a browsable integration report** (snapshot directories + markdown)

### Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Integration tests live in `tests/test_integration.py` | Keeps them in the standard pytest discovery path so CI runs them automatically |
| 2 | Snapshot output goes to `.scratch/projects/15-test-suite-improvements/integration/` | Browsable on disk; gitignored via `.scratch/` |
| 3 | Markdown report saved as `INTEGRATION_TEST_REPORT.md` in the same project dir | Human-readable summary alongside the snapshots |
| 4 | Integration tests use a dedicated `integration_vault` fixture | Separate from `tmp_vault` to avoid interference with existing unit tests |
| 5 | BUG-1 fix is a prerequisite — do it first | All subsequent tests should validate correct behavior |

---

## Step 0: Fix BUG-1 — `find_block` Regex Boundary Assertions

### Background

In `src/obsidian_ops/content.py` line 62, the block-reference token regex has non-functional boundary assertions:

```python
# CURRENT (broken):
token_re = re.compile(rf"(?<!\\S){re.escape(block_id)}(?!\\S)")
```

Inside an `rf"..."` string, `\\S` produces the literal two-character sequence `\S`. The regex engine then interprets `(?<!\\S)` as "not preceded by a literal backslash followed by capital-S" — not the intended "not preceded by a non-whitespace character."

### Work

1. Open `src/obsidian_ops/content.py`.
2. Find line 62 (inside `find_block`).
3. Change:
   ```python
   # BEFORE:
   token_re = re.compile(rf"(?<!\\S){re.escape(block_id)}(?!\\S)")

   # AFTER:
   token_re = re.compile(rf"(?<!\S){re.escape(block_id)}(?!\S)")
   ```
   Note: single backslash `\S` in an `rf"..."` string produces the regex metacharacter `\S` (non-whitespace class). This is the correct behavior.

4. Run existing tests to confirm nothing breaks:
   ```bash
   devenv shell -- pytest tests/test_content.py -v
   ```

### Add Regression Test

Add to `tests/test_content.py`:

```python
def test_find_block_no_substring_match() -> None:
    """Block ID must not match as a substring of a larger token."""
    text = "This has some^ref-block-extra text\n\nReal block ^ref-block\n"
    bounds = find_block(text, "^ref-block")
    assert bounds is not None
    matched = text[bounds[0] : bounds[1]]
    assert "Real block ^ref-block" in matched
    assert "extra" not in matched
```

### Verification

```bash
devenv shell -- pytest tests/test_content.py -v                    # all pass
devenv shell -- pytest tests/test_content.py -k "substring" -v     # new test passes
```

---

## Step 1: Integration Test Infrastructure

### Work

Create `tests/test_integration.py` with:

1. **A `SNAPSHOT_DIR` constant** pointing to `.scratch/projects/15-test-suite-improvements/integration/`.
2. **An `integration_vault` fixture** (module-scoped) that creates a realistic vault with:
   - `note.md` — full frontmatter, multiple heading levels, block references
   - `existing.md` — simple file for overwrite testing
   - `to-delete.md` — file that will be deleted
   - `Projects/Alpha.md` — nested directory with frontmatter
   - `Projects/Beta.md` — nested directory without frontmatter
   - `.hidden/secret.md` — dotfile directory (should be excluded from listings)
   - `_hidden_dir/internal.md` — underscore-prefixed hidden directory
   - `large-file.md` — file >512KB (for size limit testing)
3. **A `SnapshotRecorder` helper class** that:
   - Takes a test name (e.g., `"01-read-file"`)
   - Creates `SNAPSHOT_DIR/{test_name}/before/` and copies the target file(s)
   - After the operation, creates `SNAPSHOT_DIR/{test_name}/after/` and copies the target file(s)
   - For read-only operations, writes a `result.txt` with the returned value
   - For error operations, writes a `result.txt` with the exception type and message
4. **A `ReportWriter` helper class** that accumulates sections and writes `INTEGRATION_TEST_REPORT.md` at the end.

### Vault content for `note.md`

Use realistic Obsidian content so the before/after diffs are meaningful:

```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### Directory structure produced

```
.scratch/projects/15-test-suite-improvements/integration/
├── vault/                              # live vault (final state after all ops)
├── 01-read-file/
│   ├── before/note.md                  # file before operation
│   └── result.txt                      # content returned by read_file()
├── 02-write-new-file/
│   ├── before/                         # directory listing (file doesn't exist)
│   └── after/new-file.md              # newly created file
├── 03-write-overwrite/
│   ├── before/existing.md
│   └── after/existing.md
...
```

### Verification

```bash
devenv shell -- pytest tests/test_integration.py -v -k "infrastructure"  # fixture creates vault
ls .scratch/projects/15-test-suite-improvements/integration/vault/       # vault exists on disk
```

---

## Step 2: File Operation Integration Tests

### Work

Add these test functions to `tests/test_integration.py`. Each test must:
- Use `SnapshotRecorder` to capture before/after state
- Assert correctness
- Contribute a section to the report

#### Tests to implement

| Test Function | Vault Method | Before State | After State | Assertions |
|---------------|-------------|--------------|-------------|------------|
| `test_01_read_file` | `read_file("note.md")` | `note.md` exists | `note.md` unchanged | Returns full UTF-8 content; frontmatter + body present |
| `test_02_write_new_file` | `write_file("new-file.md", content)` | File does not exist | `new-file.md` created | File exists on disk with exact content |
| `test_03_write_overwrite` | `write_file("existing.md", new_content)` | `existing.md` has old content | `existing.md` has new content | Old content gone, new content present |
| `test_04_write_nested_new` | `write_file("Deep/Nested/new.md", content)` | `Deep/` doesn't exist | `Deep/Nested/new.md` created | Parent directories auto-created |
| `test_05_delete_file` | `delete_file("to-delete.md")` | `to-delete.md` exists | `to-delete.md` gone | `FileNotFoundError` on re-read |
| `test_06_list_files_default` | `list_files()` | Full vault | — | Returns `.md` files; excludes `.hidden/`, `_hidden_dir/` |
| `test_07_list_files_glob` | `list_files("Projects/*.md")` | Full vault | — | Returns only `Projects/Alpha.md`, `Projects/Beta.md` |
| `test_08_search_files` | `search_files("sprint")` | Full vault | — | Finds `note.md`; snippet contains context around match |

### Verification

```bash
devenv shell -- pytest tests/test_integration.py -v -k "test_01 or test_02 or test_03 or test_04 or test_05 or test_06 or test_07 or test_08"
```

Check snapshots:
```bash
diff .scratch/projects/15-test-suite-improvements/integration/03-write-overwrite/before/existing.md \
     .scratch/projects/15-test-suite-improvements/integration/03-write-overwrite/after/existing.md
```

---

## Step 3: Frontmatter Integration Tests

### Work

These tests operate on `note.md` sequentially (each builds on the prior state). Use a fresh copy of `note.md` for each test to keep them independent, OR use `order` markers and document the dependency.

**Recommendation**: Give each frontmatter test its own copy of the file (e.g., `fm-get.md`, `fm-set.md`, etc.) seeded from the same template. This keeps tests independent and parallelizable.

| Test Function | Vault Method | Before State | After State | Assertions |
|---------------|-------------|--------------|-------------|------------|
| `test_09_get_frontmatter` | `get_frontmatter("fm-get.md")` | Has frontmatter | Unchanged | Returns dict with `title`, `tags`, `status`, `priority`, `metadata` |
| `test_10_set_frontmatter` | `set_frontmatter("fm-set.md", {"title": "Replaced", "new_field": true})` | Has original frontmatter | Frontmatter fully replaced | Old fields (`tags`, `status`, etc.) gone; new fields present; body unchanged byte-for-byte |
| `test_11_update_frontmatter_merge` | `update_frontmatter("fm-merge.md", {"status": "published", "reviewer": "Bob"})` | Has original frontmatter | `status` changed, `reviewer` added, others preserved | `title`, `tags`, `priority` untouched; `status` is `"published"`; `reviewer` is `"Bob"` |
| `test_12_update_frontmatter_shallow` | `update_frontmatter("fm-shallow.md", {"metadata": {"author": "New"}})` | `metadata: {author: Jane, reviewed: false}` | `metadata: {author: New}` | Nested dict replaced wholesale — `reviewed` key is gone (shallow merge, Decision #1) |
| `test_13_update_frontmatter_creates` | `update_frontmatter("no-fm.md", {"title": "Added"})` | File with no frontmatter | Frontmatter block prepended | Body content preserved; frontmatter present |
| `test_14_delete_frontmatter_field` | `delete_frontmatter_field("fm-delete.md", "priority")` | Has `priority: high` | `priority` field gone | Other fields preserved; body unchanged |
| `test_15_delete_frontmatter_field_noop` | `delete_frontmatter_field("fm-noop.md", "nonexistent")` | No such field | File unchanged | File is byte-for-byte identical before/after |

### Verification

```bash
devenv shell -- pytest tests/test_integration.py -v -k "test_09 or test_10 or test_11 or test_12 or test_13 or test_14 or test_15"
```

Inspect before/after for the shallow merge test (most interesting):
```bash
cat .scratch/projects/15-test-suite-improvements/integration/12-update-frontmatter-shallow/before/fm-shallow.md
cat .scratch/projects/15-test-suite-improvements/integration/12-update-frontmatter-shallow/after/fm-shallow.md
```

---

## Step 4: Content Patching Integration Tests

### Work

| Test Function | Vault Method | Before State | After State | Assertions |
|---------------|-------------|--------------|-------------|------------|
| `test_16_read_heading` | `read_heading("cp-heading.md", "## Agenda")` | Full note | Unchanged | Returns agenda section including `### Action Items` subheading content |
| `test_17_write_heading_replace` | `write_heading("cp-heading.md", "## Notes", "Replaced notes.\n")` | Original `## Notes` section | Section body replaced | New content between `## Notes` and `## References`; other sections untouched |
| `test_18_write_heading_append` | `write_heading("cp-append.md", "## New Section", "Appended content.\n")` | No `## New Section` | Heading + content appended at EOF | File ends with new section; existing content preserved |
| `test_19_read_block` | `read_block("cp-block.md", "^meeting-notes")` | Full note | Unchanged | Returns paragraph containing `^meeting-notes` |
| `test_20_write_block` | `write_block("cp-block.md", "^ref-block", "Updated reference paragraph. ^ref-block\n")` | Original paragraph | Paragraph replaced | Old paragraph gone; new paragraph present; `^ref-block` marker preserved |
| `test_21_write_block_list_item` | `write_block("cp-list.md", "^list-ref", "- Updated action item ^list-ref\n")` | Original list item | Single list item replaced | Only the `^list-ref` item changed; adjacent list items untouched |

### Verification

```bash
devenv shell -- pytest tests/test_integration.py -v -k "test_16 or test_17 or test_18 or test_19 or test_20 or test_21"
```

Inspect heading replacement:
```bash
diff .scratch/projects/15-test-suite-improvements/integration/17-write-heading-replace/before/cp-heading.md \
     .scratch/projects/15-test-suite-improvements/integration/17-write-heading-replace/after/cp-heading.md
```

---

## Step 5: Error Handling Integration Tests

### Work

These tests verify that the library raises the correct exceptions with meaningful messages. No before/after file diffs — instead, capture the exception in `result.txt`.

| Test Function | Operation | Expected Exception | Assertions |
|---------------|-----------|-------------------|------------|
| `test_22_error_path_escape` | `read_file("../../etc/passwd")` | `PathError` | Message mentions "traversal" or "not allowed" |
| `test_23_error_absolute_path` | `read_file("/etc/passwd")` | `PathError` | Message mentions "absolute" |
| `test_24_error_empty_path` | `read_file("")` | `PathError` | Message mentions "empty" |
| `test_25_error_file_not_found` | `read_file("nonexistent.md")` | `FileNotFoundError` | — |
| `test_26_error_file_too_large` | `read_file("large-file.md")` | `FileTooLargeError` | File is >512KB |
| `test_27_error_block_not_found` | `write_block("note.md", "^missing", "x")` | `ContentPatchError` | Message mentions "not found" |
| `test_28_error_malformed_frontmatter` | `get_frontmatter("bad-yaml.md")` | `FrontmatterError` | File has `---\n: [invalid\n---\n` |
| `test_29_is_busy` | `is_busy()` | — | Returns `False` when idle |

### Verification

```bash
devenv shell -- pytest tests/test_integration.py -v -k "error or busy"
cat .scratch/projects/15-test-suite-improvements/integration/22-error-path-escape/result.txt
```

---

## Step 6: Server Endpoint Coverage Tests

### Background

`server.py` is at 73% coverage. The following endpoints/paths are untested or only tested via monkeypatch error injection:

**Untested endpoints:**
- `PUT /frontmatter/{path}` (`set_frontmatter`)
- `DELETE /frontmatter/{path}/{field}` (`delete_frontmatter_field`)
- `POST /content/heading/{path}/read` (`read_heading`)
- `PUT /content/heading/{path}` (`write_heading`)
- `POST /content/block/{path}/read` (`read_block`)
- `PUT /content/block/{path}` (`write_block`)
- `POST /vcs/undo`
- `GET /vcs/status`

**Untested error mappings:**
- `FileTooLargeError` → 413
- `FrontmatterError` → 422
- `ContentPatchError` → 422
- `VCSError` → 424 (precondition) vs 500 (execution)

### Work

Add to `tests/test_server.py`:

```python
# --- Missing endpoint tests ---

def test_set_frontmatter(client: TestClient) -> None:
    """PUT /frontmatter/{path} replaces all frontmatter."""
    response = client.put("/frontmatter/note.md", json={"title": "Replaced"})
    assert response.status_code == 200
    check = client.get("/frontmatter/note.md")
    fm = check.json()["frontmatter"]
    assert fm["title"] == "Replaced"
    assert "tags" not in fm  # old fields gone


def test_delete_frontmatter_field(client: TestClient) -> None:
    """DELETE /frontmatter/{path}/{field} removes one field."""
    response = client.delete("/frontmatter/note.md/status")
    assert response.status_code == 200
    check = client.get("/frontmatter/note.md")
    assert "status" not in check.json()["frontmatter"]


def test_read_heading(client: TestClient) -> None:
    """POST /content/heading/{path}/read returns section content."""
    response = client.post("/content/heading/note.md/read", json={"heading": "## Summary"})
    assert response.status_code == 200
    assert response.json()["content"] is not None


def test_write_heading(client: TestClient) -> None:
    """PUT /content/heading/{path} replaces heading section."""
    response = client.put("/content/heading/note.md", json={"heading": "## Summary", "content": "New summary.\n"})
    assert response.status_code == 200
    check = client.post("/content/heading/note.md/read", json={"heading": "## Summary"})
    assert "New summary." in check.json()["content"]


def test_read_block(client: TestClient) -> None:
    """POST /content/block/{path}/read returns block content."""
    response = client.post("/content/block/note.md/read", json={"block_id": "^ref-block"})
    assert response.status_code == 200
    assert response.json()["content"] is not None


def test_write_block(client: TestClient) -> None:
    """PUT /content/block/{path} replaces block content."""
    response = client.put("/content/block/note.md", json={"block_id": "^ref-block", "content": "Updated ^ref-block\n"})
    assert response.status_code == 200
    check = client.post("/content/block/note.md/read", json={"block_id": "^ref-block"})
    assert "Updated" in check.json()["content"]


def test_vcs_status(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /vcs/status returns status string."""
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "vcs_status", lambda: "Working copy changes:\nM note.md\n")
    response = client.get("/vcs/status")
    assert response.status_code == 200
    assert "note.md" in response.json()["status"]


def test_vcs_undo(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /vcs/undo calls undo."""
    called = []
    monkeypatch.setattr(vault := client.app.state.vault, "undo", lambda: called.append(True))
    response = client.post("/vcs/undo")
    assert response.status_code == 200
    assert called


# --- Missing error mapping tests ---

def test_file_too_large_returns_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from obsidian_ops.errors import FileTooLargeError
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "read_file", lambda _: (_ for _ in ()).throw(FileTooLargeError("too big")))
    response = client.get("/files/note.md")
    assert response.status_code == 413


def test_frontmatter_error_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from obsidian_ops.errors import FrontmatterError
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "get_frontmatter", lambda _: (_ for _ in ()).throw(FrontmatterError("bad yaml")))
    response = client.get("/frontmatter/note.md")
    assert response.status_code == 422


def test_content_patch_error_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from obsidian_ops.errors import ContentPatchError
    vault = client.app.state.vault
    def boom(payload):
        raise ContentPatchError("not found")
    monkeypatch.setattr(vault, "write_block", lambda *a: (_ for _ in ()).throw(ContentPatchError("not found")))
    response = client.put("/content/block/note.md", json={"block_id": "^x", "content": "y"})
    assert response.status_code == 422


def test_vcs_error_precondition_returns_424(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from obsidian_ops.errors import VCSError
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "commit", lambda _: (_ for _ in ()).throw(VCSError("jj binary not found")))
    response = client.post("/vcs/commit", json={"message": "x"})
    assert response.status_code == 424


def test_vcs_error_execution_returns_500(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from obsidian_ops.errors import VCSError
    vault = client.app.state.vault
    monkeypatch.setattr(vault, "commit", lambda _: (_ for _ in ()).throw(VCSError("jj command failed: merge conflict")))
    response = client.post("/vcs/commit", json={"message": "x"})
    assert response.status_code == 500
```

### Verification

```bash
devenv shell -- pytest tests/test_server.py -v                                          # all pass
devenv shell -- pytest tests/test_server.py --cov=obsidian_ops.server --cov-report=term-missing  # ≥90%
```

---

## Step 7: Edge-Case Unit Tests for Uncovered Lines

### Background

Coverage report shows specific uncovered lines. Add targeted tests for each.

### Work

#### `frontmatter.py` uncovered lines

Add to `tests/test_frontmatter.py`:

```python
def test_parse_frontmatter_crlf_body_separator() -> None:
    """Line 41: body separator is \\r\\n after closing ---."""
    text = "---\ntitle: Test\n---\r\nBody here."
    data, body = parse_frontmatter(text)
    assert data == {"title": "Test"}
    assert body == "Body here."


def test_parse_frontmatter_none_yaml_block() -> None:
    """Line 53: YAML block that loads as None (e.g., just a comment)."""
    text = "---\n# just a comment\n---\nBody."
    data, body = parse_frontmatter(text)
    assert data == {}
    assert body == "Body."


def test_parse_frontmatter_non_dict_raises() -> None:
    """Line 55: YAML that deserializes to a list, not a dict."""
    text = "---\n- item1\n- item2\n---\nBody."
    with pytest.raises(FrontmatterError, match="mapping"):
        parse_frontmatter(text)
```

#### `sandbox.py` uncovered lines

Add to `tests/test_sandbox.py`:

```python
def test_validate_path_dot_resolves_to_root(tmp_path: Path) -> None:
    """Line 38: path that normalizes to '.' (vault root itself)."""
    with pytest.raises(PathError, match="vault root"):
        validate_path(tmp_path, "./")


def test_validate_path_new_file_parent_escape(tmp_path: Path) -> None:
    """Line 57: non-existent file whose resolved parent is outside root."""
    # Create a symlink to an outside directory
    outside = tmp_path.parent / "outside_sandbox"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "escape_link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not available")
    with pytest.raises(PathError, match="parent escapes"):
        validate_path(tmp_path, "escape_link/secret.md")
```

#### `search.py` uncovered lines

Add to `tests/test_search.py`:

```python
def test_walk_vault_zero_max_results(tmp_vault: Path) -> None:
    """Line 22: max_results <= 0 returns empty list."""
    result = walk_vault(tmp_vault, "*.md", max_results=0)
    assert result == []


def test_search_content_nonexistent_file(tmp_vault: Path) -> None:
    """Line 50: file in list doesn't exist on disk — silently skipped."""
    result = search_content(tmp_vault, "test", ["ghost.md"], max_results=10)
    assert result == []


def test_search_content_empty_query(tmp_vault: Path) -> None:
    """Line 58 (approx): empty query returns empty list."""
    result = search_content(tmp_vault, "", ["note.md"], max_results=10)
    assert result == []
```

#### `content.py` uncovered lines

Add to `tests/test_content.py`:

```python
def test_find_heading_non_heading_exact_match() -> None:
    """Line 43: text that matches the heading string but isn't a heading (no # prefix)."""
    text = "## Summary\nContent\n\nSummary\nNot a heading.\n"
    bounds = find_heading(text, "## Summary")
    assert bounds is not None
    # Should match the real heading, not the bare word "Summary"


def test_find_block_multi_line_paragraph() -> None:
    """Line 77: block ref in a multi-line paragraph walks back to paragraph start."""
    text = "Unrelated.\n\nFirst line of paragraph.\nSecond line.\nThird line with ^block-id\n\nAfter.\n"
    bounds = find_block(text, "^block-id")
    assert bounds is not None
    block = text[bounds[0] : bounds[1]]
    assert block.startswith("First line of paragraph.")
    assert "^block-id" in block
```

### Verification

```bash
devenv shell -- pytest tests/ -v                                                    # all pass
devenv shell -- pytest tests/ --cov=obsidian_ops --cov-report=term-missing          # coverage improved
```

---

## Step 8: Integration Test Report Generator

### Work

Add a report-generation fixture to `tests/test_integration.py` that runs after all integration tests and produces:

1. **Snapshot directories** at `.scratch/projects/15-test-suite-improvements/integration/`
2. **`INTEGRATION_TEST_REPORT.md`** at `.scratch/projects/15-test-suite-improvements/`

#### Report format

Each test gets a section like:

````markdown
## 03 — Write File (Overwrite)

**Method**: `vault.write_file("existing.md", "New content here.\n")`
**Result**: PASS

### Before (`existing.md`)
```markdown
---
title: Existing File
---

Original content that will be overwritten.
```

### After (`existing.md`)
```markdown
New content here.
```
````

For read-only operations:

````markdown
## 01 — Read File

**Method**: `vault.read_file("note.md")`
**Result**: PASS

### File Content (unchanged)
```markdown
---
title: Meeting Notes
...
```

### Returned Value
```
(full file content)
```
````

For error operations:

````markdown
## 22 — Error: Path Escape

**Method**: `vault.read_file("../../etc/passwd")`
**Result**: PASS (raised PathError)

### Exception
```
PathError: path traversal is not allowed
```
````

### Implementation approach

Use a module-scoped `report_collector` fixture (list of dicts) that each test appends to. A `session`-scoped finalizer writes the report and snapshots after all tests complete. Alternatively, use `pytest`'s `tmp_path_factory` for the vault and a conftest-level fixture for report generation.

### Verification

```bash
devenv shell -- pytest tests/test_integration.py -v
cat .scratch/projects/15-test-suite-improvements/INTEGRATION_TEST_REPORT.md
ls .scratch/projects/15-test-suite-improvements/integration/
```

---

## Step 9: Final Verification & Cleanup

### Work

1. Run the full test suite:
   ```bash
   devenv shell -- pytest tests/ -v
   ```

2. Run coverage and verify targets:
   ```bash
   devenv shell -- pytest tests/ --cov=obsidian_ops --cov-report=term-missing
   ```

   **Targets:**
   | Module | Target |
   |--------|--------|
   | `content.py` | ≥98% |
   | `frontmatter.py` | ≥95% |
   | `sandbox.py` | ≥97% |
   | `search.py` | ≥97% |
   | `server.py` | ≥90% |
   | `vault.py` | ≥98% |
   | **Overall** | **≥93%** |

3. Run linter:
   ```bash
   devenv shell -- ruff check src/ tests/
   devenv shell -- ruff format --check src/ tests/
   ```

4. Verify the integration report is complete and readable:
   ```bash
   wc -l .scratch/projects/15-test-suite-improvements/INTEGRATION_TEST_REPORT.md  # should be substantial
   ls .scratch/projects/15-test-suite-improvements/integration/ | wc -l           # ~30 directories
   ```

5. Spot-check a few before/after diffs:
   ```bash
   diff .scratch/projects/15-test-suite-improvements/integration/10-set-frontmatter/before/fm-set.md \
        .scratch/projects/15-test-suite-improvements/integration/10-set-frontmatter/after/fm-set.md
   ```

### Acceptance Checklist

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | BUG-1 fixed | `test_find_block_no_substring_match` passes |
| 2 | All existing tests still pass | `pytest tests/` — 108+ tests, 0 failures |
| 3 | Integration tests pass | `pytest tests/test_integration.py` — all pass |
| 4 | Server coverage ≥90% | `--cov=obsidian_ops.server` output |
| 5 | Overall coverage ≥93% | `--cov=obsidian_ops` output |
| 6 | Snapshot directories exist | `ls integration/` shows numbered dirs with before/after |
| 7 | Integration report generated | `INTEGRATION_TEST_REPORT.md` exists with all sections |
| 8 | Ruff clean | `ruff check` reports 0 violations |
| 9 | Every public Vault method exercised in integration tests | Manual check against `vault.py` public API |

---

## File Creation/Modification Order

```
Step 0:  MODIFY  src/obsidian_ops/content.py          (fix BUG-1, 1 line)
         MODIFY  tests/test_content.py                (add regression test)

Step 1:  CREATE  tests/test_integration.py            (infrastructure + fixtures)

Step 2:  MODIFY  tests/test_integration.py            (add file operation tests)

Step 3:  MODIFY  tests/test_integration.py            (add frontmatter tests)

Step 4:  MODIFY  tests/test_integration.py            (add content patching tests)

Step 5:  MODIFY  tests/test_integration.py            (add error handling tests)

Step 6:  MODIFY  tests/test_server.py                 (add endpoint + error mapping tests)

Step 7:  MODIFY  tests/test_content.py                (edge-case tests)
         MODIFY  tests/test_frontmatter.py            (edge-case tests)
         MODIFY  tests/test_sandbox.py                (edge-case tests)
         MODIFY  tests/test_search.py                 (edge-case tests)

Step 8:  MODIFY  tests/test_integration.py            (add report generator)

Step 9:  (verification only, no file changes)
```

Each step is independently verifiable. Do not proceed to the next step until all tests for the current step pass.
