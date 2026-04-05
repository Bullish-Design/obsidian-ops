# Kiln Integration Review

An analysis of how well bullish-ssg integrates with Kiln, where it duplicates Kiln's functionality, where it underutilizes Kiln, and what should change.

**Date:** 2026-04-03

---

## Executive Summary

bullish-ssg wraps Kiln through a thin subprocess adapter (`render/kiln.py`). The adapter works but **passes wrong CLI flags**, **omits most of Kiln's configuration options**, and **reimplements link validation that Kiln already provides** via `kiln doctor`. The integration is functional for dry-run demos but would fail on a real `kiln generate` call due to the flag mismatch.

### Scorecard

| Area | Grade | Summary |
|------|-------|---------|
| Subprocess execution | **B+** | Clean adapter pattern, good error handling, mockable runner |
| CLI flag correctness | **F** | Uses `--source` instead of `--input`; will fail at runtime |
| Config passthrough | **D** | Doesn't pass `--url`, `--name`, `--theme`, `--font` to Kiln |
| `kiln doctor` usage | **F** | Not used at all; reimplemented from scratch in Python |
| `kiln dev` usage | **F** | Not exposed; would be the ideal `serve` implementation |
| `kiln.yaml` generation | **F** | Not implemented; could bridge bullish-ssg.toml → kiln.yaml |
| Build pipeline | **C** | Works structurally but missing critical flag passthrough |
| Serve pipeline | **C-** | Passes `--source` (wrong flag) and serves vault dir instead of built output |
| Deployment pipeline | **B+** | Good — this is bullish-ssg's own value-add, not a Kiln concern |

---

## 1. Critical Bug: Wrong CLI Flags

**This is the single most important finding.**

### `KilnAdapter.build()` — Line 109

```python
command.extend(["--source", str(source_dir)])
```

Kiln's `generate` command uses `--input` / `-i`, **not** `--source`. The flag `--source` doesn't exist in Kiln. This means every non-dry-run `bullish-ssg build` will fail with an unknown flag error.

**Fix:**

```python
command.extend(["--input", str(source_dir)])
```

### `KilnAdapter.serve()` — Line 150

```python
command.extend(["--source", str(source_dir)])
```

Same problem. Kiln's `serve` command uses `--output` / `-o` (it serves the built directory, not the source vault). The current code also passes the vault path instead of the output directory, which is a semantic error even if the flag were correct.

**Fix:**

```python
# serve takes the built output dir, not the source vault
command.extend(["--output", str(output_dir)])
```

And the `serve()` method signature should accept `output_dir`, not `source_dir`.

### `KilnAdapter.serve()` — Port flag

```python
command.extend(["--port", str(port)])
```

Kiln's serve uses `--port` / `-p` — this one is correct. But the default port in bullish-ssg is `8000` while Kiln defaults to `8080`. Minor inconsistency, not a bug.

### `KilnAdapter.build()` — Config flag

```python
command.extend(["--config", str(config_file)])
```

Kiln doesn't have a `--config` flag. It looks for `kiln.yaml` in the CWD automatically. This code path is never triggered (no caller passes `config_file`), but it would fail if used.

---

## 2. Missing Kiln Configuration Passthrough

The `bullish-ssg.toml` config has `site.url` and `site.name`, but these are **never passed to Kiln**. This means:

| bullish-ssg config | Kiln flag | Currently passed? | Impact |
|--------------------|-----------|--------------------|--------|
| `site.url` | `--url` | **No** | No sitemap.xml, no canonical URLs, no Open Graph tags |
| `site.name` | `--name` | **No** | No site title in navigation/HTML |
| *(not in config)* | `--theme` | **No** | Always uses Kiln's default theme |
| *(not in config)* | `--font` | **No** | Always uses Kiln's default font |
| *(not in config)* | `--layout` | **No** | Always uses default layout |
| *(not in config)* | `--mode` | **No** | Always uses default mode (correct for now) |
| *(not in config)* | `--flat-urls` | **No** | Always uses directory-style URLs |

### Impact

Without `--url`, a Kiln-generated site has:
- No `sitemap.xml`
- No `robots.txt`
- No canonical URLs
- No Open Graph tags
- Broken SEO

Without `--name`, the site has no title in the browser tab or navigation header.

### Recommendation

The `BuildManager.build_from_config()` should pass the full BullishConfig (or at least the site config) to the KilnAdapter, which should construct the complete command:

```python
command = [
    "kiln", "generate",
    "--input", str(source_dir),
    "--output", str(output_dir),
]
if url:
    command.extend(["--url", url])
if name:
    command.extend(["--name", name])
if theme:
    command.extend(["--theme", theme])
if font:
    command.extend(["--font", font])
```

This also means `bullish-ssg.toml` should gain optional `[render]` or `[kiln]` section for theme/font/layout.

---

## 3. Duplicated Functionality: Link Checking

### What bullish-ssg does

`bullish-ssg check-links` runs a complete Python wikilink validation pipeline:

1. `ContentDiscovery` scans the vault for markdown files
2. `WikilinkParser` (regex) extracts all `[[wikilinks]]` with line numbers
3. `PageIndex` builds a slug-to-path index
4. `WikilinkResolver` resolves each link against the index
5. `HeadingExtractor` validates heading anchors by parsing markdown headings
6. Reports broken links, missing headings, unpublished page references

This is **~520 lines of Python** across `validate/wikilinks.py` and parts of `validate/rules.py`.

### What Kiln already does

`kiln doctor --input ./docs` does the same thing natively:
- Checks broken wikilinks
- Handles aliases (`[[Page|Alias]]`)
- Handles heading anchors (`[[Page#Section]]`)
- Checks image references
- Checks canvas files
- Returns non-zero exit on broken links

### Analysis

| Capability | bullish-ssg Python | kiln doctor |
|-----------|-------------------|-------------|
| Basic wikilink resolution | Yes | Yes |
| Alias handling | Yes | Yes |
| Heading anchor validation | Yes | Yes |
| Block reference validation | Warning only | Yes |
| Image reference checking | **No** | Yes |
| Canvas file checking | **No** | Yes |
| Line number reporting | Yes | Unknown |
| Unpublished/draft page detection | Yes | **No** |
| Orphan page detection | Yes | **No** |
| Custom ignore patterns | Yes | Partial (`.` and `_` prefix) |
| Speed | Slower (Python I/O) | Faster (Go, optimized) |

### Recommendation

**Hybrid approach:** Use `kiln doctor` as the primary link checker and supplement with Python-only checks for bullish-ssg-specific concerns:

1. **Delegate to Kiln:** Basic wikilink resolution, heading anchors, image references, canvas files
2. **Keep in Python:** Unpublished/draft page warnings, orphan detection, custom ignore pattern filtering, frontmatter validation

This would:
- Reduce ~300 lines of Python wikilink resolution code
- Get image/canvas checking for free
- Stay in sync with Kiln's actual resolution algorithm (avoiding drift)
- Keep bullish-ssg-specific validation that Kiln can't do

Implementation sketch:

```python
class CheckLinksCommand:
    def run(self):
        # Step 1: Run kiln doctor for link resolution
        result = self.runner.run(["kiln", "doctor", "--input", str(vault_path)])
        # Parse kiln doctor output for broken link diagnostics

        # Step 2: Run Python-only supplemental checks
        # - Unpublished/draft page reference detection
        # - Orphan page detection
        # - Custom ignore pattern enforcement
```

---

## 4. Missing `kiln dev` Integration

Kiln's `kiln dev` command combines build + file watching + serve in one process. It auto-rebuilds when vault files change.

bullish-ssg's `serve` command currently:
1. Resolves the vault path
2. Calls `KilnAdapter.serve()` which passes the vault path as `--source` (wrong)

It should instead either:
- **Option A:** Call `kiln dev --input <vault> --output <site>` — gets watch + rebuild + serve in one command
- **Option B:** Call `kiln generate` then `kiln serve --output <site>` — two-step but correct

Option A is clearly better for development workflows. The bullish-ssg `serve` command should wrap `kiln dev`, not `kiln serve`.

---

## 5. Missing `kiln.yaml` Bridge

Kiln supports an optional `kiln.yaml` config file. bullish-ssg already has a rich config in `bullish-ssg.toml`. There's an opportunity to generate a `kiln.yaml` from the bullish-ssg config before invoking Kiln commands, so that Kiln picks up all settings automatically.

```python
def generate_kiln_config(config: BullishConfig, output_path: Path) -> None:
    """Generate kiln.yaml from bullish-ssg config."""
    kiln_config = {
        "name": config.site.name,
        "url": config.site.url,
        "input": str(config.vault.link_path),
        "output": str(config.content.output_dir),
    }
    # Add optional render settings if present
    if hasattr(config, 'render'):
        if config.render.theme:
            kiln_config["theme"] = config.render.theme
        if config.render.font:
            kiln_config["font"] = config.render.font

    output_path.write_text(yaml.dump(kiln_config))
```

This would eliminate the need to pass every flag on the command line and ensure Kiln always has the full configuration.

---

## 6. Serve Architecture Is Wrong

The current `serve` flow:

```
CLI serve command
  → resolve vault path
  → KilnAdapter.serve(source_dir=vault_path, port=8000)
  → kiln serve --source <vault_path> --port 8000
```

Problems:
1. `--source` is not a valid Kiln flag
2. `kiln serve` serves an already-built output directory, not a source vault
3. The vault path is passed instead of the output directory
4. No build step happens before serve

Correct flow should be:

```
CLI serve command
  → resolve vault path
  → KilnAdapter.build(input_dir=vault_path, output_dir=output_dir)  # build first
  → KilnAdapter.serve(output_dir=output_dir, port=8000)
  → kiln serve --output <output_dir> --port 8000
```

Or better, just use `kiln dev`:

```
CLI serve command
  → resolve vault path
  → kiln dev --input <vault_path> --output <output_dir> --port 8000
```

---

## 7. Content Classification: Useful or Redundant?

bullish-ssg has a content classification system (`content/classify.py`) that:
- Infers content type (doc/post/page) from path and frontmatter
- Generates slugs with normalization
- Builds permalinks (e.g., `/blog/2026/01/15/my-post/`)
- Detects slug collisions

### Does Kiln need this?

**No.** Kiln in default mode mirrors the vault directory structure 1:1. It does NOT use content types, slugs, or permalink patterns. A file at `blog/my-post.md` becomes `blog/my-post/index.html` — that's it. No date-based routing, no type inference.

### When would it matter?

Content classification would matter for:
- **Kiln custom mode** — where templates and collections define routing (experimental)
- **RSS/Atom feed generation** — if bullish-ssg generates feeds, it needs to know what's a "post"
- **Sitemap generation** — different priority for posts vs. docs (but Kiln generates sitemaps)
- **A future bullish-ssg feature** that processes content beyond what Kiln does

### Recommendation

The classification system is **premature but not harmful**. It's well-tested code that may become useful when bullish-ssg supports custom mode or generates its own feeds. Don't remove it, but don't treat its permalink output as authoritative for the actual site URLs — Kiln determines those.

---

## 8. Frontmatter Parsing: Useful or Redundant?

bullish-ssg parses frontmatter (`content/frontmatter.py`) to extract metadata for validation and classification.

### Does Kiln use frontmatter?

Yes — Kiln reads frontmatter for:
- Page titles
- Tags
- Any metadata needed by templates (custom mode)

But Kiln handles this internally. bullish-ssg's frontmatter parsing is used for **pre-build validation**, not rendering. This is a legitimate use case — validating content before passing it to Kiln is exactly the value bullish-ssg adds.

**Verdict:** Keep it. Frontmatter parsing for validation is appropriate.

---

## 9. Content Discovery: Useful or Redundant?

bullish-ssg discovers content files (`content/discovery.py`) with configurable ignore patterns.

### Does Kiln discover files?

Yes — Kiln scans the input directory and processes all `.md` files (ignoring `.`/`_` prefixed and `templates/`).

### Why bullish-ssg needs its own discovery

- **Custom ignore patterns** — bullish-ssg supports user-configurable glob patterns beyond Kiln's fixed rules
- **Validation scope** — needs to enumerate files to run frontmatter/link checks
- **Classification** — needs file list to classify content types

**Verdict:** Keep it. Discovery with configurable ignore patterns is valuable for the validation pipeline.

---

## 10. Prioritized Recommendations

### Critical (blocks real builds)

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| C1 | Fix `--source` → `--input` in `KilnAdapter.build()` | 5 min | Builds will actually work |
| C2 | Fix `serve()` to pass output dir with `--output`, not vault dir with `--source` | 15 min | Serve will actually work |
| C3 | Remove `--config` flag (Kiln doesn't have it) | 5 min | Prevents confusing errors |
| C4 | Pass `--url` and `--name` from bullish-ssg config to `kiln generate` | 30 min | SEO, sitemap, site title |

### High (significant improvement)

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| H1 | Add `--theme` and `--font` config options | 1 hr | Users can customize site appearance |
| H2 | Use `kiln dev` for `bullish-ssg serve` instead of `kiln serve` | 1 hr | Auto-rebuild on changes |
| H3 | Delegate primary link checking to `kiln doctor` | 2-3 hrs | More correct, less code, image/canvas checks for free |
| H4 | Build before serve (or use `kiln dev`) | 30 min | Serve actually shows generated site |

### Medium (nice to have)

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| M1 | Generate `kiln.yaml` from bullish-ssg.toml | 1-2 hrs | Clean config bridge |
| M2 | Add `[render]` or `[kiln]` section to config schema | 1 hr | Expose theme/font/layout/flat-urls |
| M3 | Keep Python wikilink validation as supplemental (unpublished/orphan detection) | 1 hr | Best of both worlds |
| M4 | Expose `kiln doctor` as a separate diagnostic in `validate` output | 1 hr | More complete health check |

### Low (future consideration)

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| L1 | Support Kiln custom mode when it stabilizes | TBD | Enables blog/portfolio templates |
| L2 | Pass `--flat-urls` option from config | 15 min | Niche URL style preference |
| L3 | Generate RSS/Atom feeds using classification data | 4-6 hrs | Adds value beyond what Kiln provides |

---

## 11. Summary: What bullish-ssg Should Delegate vs. Own

### Delegate to Kiln (don't reimplement)

| Capability | Current State | Should Be |
|-----------|---------------|-----------|
| Markdown → HTML rendering | Delegated (correct) | Keep delegated |
| Wikilink resolution (in HTML) | Delegated (correct) | Keep delegated |
| Theme/styling | Not exposed | Pass through to Kiln |
| Search index | Delegated (correct) | Keep delegated |
| Navigation (sidebar, graph, backlinks) | Delegated (correct) | Keep delegated |
| SEO (sitemap, meta tags) | **Broken** (no --url passed) | Fix: pass --url/--name |
| Link validation | **Reimplemented in Python** | Delegate primary check to `kiln doctor` |
| Serve / dev server | **Broken** (wrong flags) | Fix: use `kiln dev` or `kiln serve --output` |

### Own (bullish-ssg value-add)

| Capability | Current State | Assessment |
|-----------|---------------|------------|
| Vault symlink management | Implemented | Kiln has no equivalent — keep |
| TOML-based configuration | Implemented | Richer than kiln.yaml — keep |
| GitHub Pages deployment | Implemented | Kiln has no deploy — keep |
| Pre-build validation (frontmatter) | Implemented | Kiln doesn't validate before build — keep |
| Unpublished/draft page detection | Implemented | Kiln doesn't track publish state — keep |
| Orphan page detection | Implemented | Kiln doesn't check orphans — keep |
| Custom ignore patterns | Implemented | Kiln's ignore rules are fixed — keep |
| Content classification | Implemented (premature) | Not used by Kiln default mode — keep for future |
| Idempotent project scaffolding | Implemented | Richer than `kiln init` — keep |
| CI workflow generation | Implemented | Kiln has no CI support — keep |

### The ideal architecture

```
bullish-ssg (Python orchestrator)
├── init          → own scaffolding (richer than kiln init)
├── link-vault    → own symlink management (Kiln has nothing)
├── validate      → own frontmatter/structure validation + kiln doctor for links
├── check-links   → kiln doctor + supplemental unpublished/orphan checks
├── build         → kiln generate (with full flag passthrough)
├── serve         → kiln dev (build + watch + serve)
└── deploy        → gh pages deploy (Kiln has nothing)
```

bullish-ssg's value is the **workflow orchestration** layer: managing vaults, validating before build, deploying after build, and providing a single config file. Kiln's value is the **rendering engine**. The integration should be a clean division — bullish-ssg prepares and validates, Kiln renders, bullish-ssg deploys.

Right now, the integration is structurally correct but broken at the flag level, and it reimplements too much of what Kiln already does well.
