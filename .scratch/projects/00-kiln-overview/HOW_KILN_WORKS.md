# How Kiln Works — Developer Guide

A guide for bullish-ssg developers who need to understand the rendering engine underneath.

---

## What Kiln Is

Kiln is a Go-based static site generator purpose-built for Obsidian vaults. It converts an Obsidian vault directory into a complete static website with 1:1 feature parity — wikilinks, Canvas files, Mermaid diagrams, LaTeX math, callouts, backlinks, graph views, and full-text search all work out of the box.

- **Repository:** https://github.com/otaleghani/kiln
- **Documentation:** https://kiln.talesign.com/ (itself built with Kiln)
- **License:** MIT
- **Version:** v0.9.5 (pinned in our devenv.nix)

Kiln is a single Go binary with zero runtime dependencies. In the bullish-ssg project, it's provided via the Nix flake in `devenv.nix` — you never install it manually.

---

## Core Mental Model

```
Obsidian Vault (Markdown + assets)
        │
        ▼
   kiln generate
        │
        ▼
Static Site (HTML + CSS + JS + assets)
        │
        ▼
   kiln serve  ──►  http://localhost:8080
```

That's it. Kiln reads a directory of Markdown files, resolves all internal links, applies a theme, and writes a complete static site. No intermediate build steps, no plugins, no config required.

---

## The Five Commands

### 1. `kiln generate` — Build the site

The primary command. Converts vault to static HTML.

```bash
kiln generate --input ./docs --output ./public
```

**All flags:**

| Flag | Short | Default | Purpose |
|------|-------|---------|---------|
| `--input` | `-i` | `./vault` | Source vault directory |
| `--output` | `-o` | `./public` | Output directory for generated site |
| `--theme` | `-t` | `default` | Theme name (e.g., `nord`, `dracula`, `solarized`) |
| `--font` | `-f` | `inter` | Font family (e.g., `inter`, `jetbrains-mono`) |
| `--url` | `-u` | *(none)* | Base URL for SEO (sitemap, canonical URLs, Open Graph) |
| `--name` | `-n` | *(none)* | Site name for title tags and navigation |
| `--mode` | `-m` | `default` | Operating mode: `default` or `custom` |
| `--layout` | `-L` | *(none)* | Page layout override |
| `--flat-urls` | | `false` | Generate `note.html` instead of `note/index.html` |

**What it produces:**

```
public/
├── index.html              # From vault/index.md
├── about/
│   └── index.html          # From vault/about.md
├── blog/
│   └── my-post/
│       └── index.html      # From vault/blog/my-post.md
├── assets/                 # Copied verbatim from vault
│   └── image.png
├── css/                    # Theme styles
├── js/                     # Navigation, search, graph scripts
├── sitemap.xml             # Only when --url is provided
├── robots.txt              # Only when --url is provided
├── favicon.ico             # Preserved if present in vault
└── CNAME                   # Preserved if present in vault
```

**Critical behaviors:**
- **Kiln cleans the output directory before each build.** Everything in `--output` is deleted first.
- Files/folders starting with `.` or `_` in the vault are ignored (e.g., `.obsidian/`, `_drafts/`).
- `templates/` is ignored by default in default mode.
- Without `--url`, no sitemap.xml or robots.txt is generated.
- The `--url` should match your deployment domain exactly, with trailing slash.

### 2. `kiln serve` — Local development server

Serves the built output directory over HTTP.

```bash
kiln serve --output ./public
```

| Flag | Short | Default | Purpose |
|------|-------|---------|---------|
| `--output` | `-o` | `./public` | Directory to serve |
| `--port` | `-p` | `8080` | Port number |

**Features:**
- Clean URL support (`/about` resolves to `about/index.html`)
- Proper MIME types for all file types
- Base path handling for subdirectory deployments (e.g., `/repo-name/`)
- Custom 404 page (serves `404.html` if present)

**Note:** `kiln serve` only serves static files — it does NOT watch for changes or rebuild.

### 3. `kiln dev` — Watch + build + serve

Combines generate + file watching + serve in one command.

```bash
kiln dev --input ./docs --output ./public
```

Accepts all the same flags as `generate` plus serve flags. Rebuilds automatically when vault files change. This is the command developers use during content authoring.

### 4. `kiln doctor` — Link validation

Checks for broken references in the vault.

```bash
kiln doctor --input ./docs
```

**What it checks:**
- Broken wikilinks (`[[Missing Note]]`)
- Broken aliases (`[[Note|Display Text]]` where Note doesn't exist)
- Broken heading anchors (`[[Note#Missing Section]]`)
- Missing image references (`![[missing.png]]`)
- Missing canvas files
- Renamed files with stale references

**Exit codes:** 0 = clean, non-zero = broken links found.

### 5. `kiln init` — Scaffold a new vault

```bash
kiln init --input ./my-vault
```

Creates a minimal vault with `Home.md` and a `kiln.yaml` config file with commented defaults.

---

## Two Operating Modes

### Default Mode (what we use)

Mirrors the vault 1:1 to HTML. Every `.md` file becomes an HTML page preserving the directory structure. This is the stable, production-ready mode.

```
vault/                          public/
├── index.md        ───►        ├── index.html
├── about.md                    ├── about/index.html
├── assets/                     ├── assets/
│   └── logo.png                │   └── logo.png
└── blog/                       └── blog/
    └── post.md                     └── post/index.html
```

### Custom Mode (experimental)

Treats Obsidian as a headless CMS with templates and collections. Requires `env.json`, `config.json`, and HTML template files alongside the Markdown. Still in early development as of v0.9.5 — **bullish-ssg should not rely on this mode yet.**

---

## Configuration: `kiln.yaml`

Optional. Kiln looks for `kiln.yaml` in the **current working directory** (not next to the vault). CLI flags always override config values.

```yaml
name: "My Digital Garden"
url: "https://notes.example.com"
theme: "nord"
font: "inter"
layout: "default"
input: "./vault"
output: "./public"
```

All fields are optional. Without a config file, Kiln uses CLI flags or defaults.

---

## How Kiln Resolves Wikilinks

This is the feature most relevant to bullish-ssg developers.

### Link Syntax

| Syntax | Example | Behavior |
|--------|---------|----------|
| Basic | `[[Page Name]]` | Links to `Page Name.md` |
| Aliased | `[[Page Name\|Display Text]]` | Shows "Display Text", links to `Page Name.md` |
| Heading anchor | `[[Page Name#Section]]` | Deep link to heading in `Page Name.md` |
| Block reference | `[[Page Name#^block-id]]` | Deep link to block in `Page Name.md` |
| Embedded | `![[image.png]]` | Embeds the image inline |
| Embedded note | `![[Other Note]]` | Transcludes content from another note |

### Resolution Algorithm

Kiln resolves wikilinks using Obsidian's "shortest path" algorithm:

1. **Exact filename match** — `[[Getting Started]]` matches `Getting Started.md` anywhere in the vault
2. **Path-qualified match** — `[[blog/My Post]]` matches `blog/My Post.md`
3. **Case-insensitive** — `[[getting started]]` matches `Getting Started.md`

When multiple files share the same name, the path-qualified form disambiguates.

### Heading Anchors

Headings are converted to URL anchors using GitHub-style slugification:
- Lowercase
- Spaces → hyphens
- Special characters removed
- Duplicate headings get `-1`, `-2` suffixes

### What Happens to Resolved Links

In the HTML output, wikilinks become standard `<a href="...">` tags pointing to the generated HTML paths. The link text is either the page title, the alias, or the filename.

---

## What Kiln Generates Beyond HTML

### Navigation Components
- **File explorer sidebar** — mirrors vault directory structure
- **Breadcrumbs** — path-based navigation
- **Table of contents** — auto-generated from headings per page
- **Backlinks panel** — shows all pages linking to the current page

### Graph Views
- **Global graph** — visualizes all vault connections
- **Local graph** — per-page network view showing neighbors

### Search
- **Full-text search** — client-side, works without a server
- Built from a search index generated at build time

### Tags
- Extracts `#tags` from content and frontmatter `tags:` field
- Generates tag index pages

### Theme System

Kiln ships with many built-in themes:
- `default`, `nord`, `dracula`, `solarized`, `gruvbox`, `catppuccin`, etc.
- Every theme has light and dark variants
- User can toggle light/dark mode in the UI

Themes control:
- Color scheme
- Typography (font is separately configurable)
- Layout spacing
- Component styling (callouts, code blocks, etc.)

### SEO (when `--url` is provided)
- `<meta>` tags (title, description, author)
- Open Graph tags for social sharing
- `sitemap.xml` with all pages
- `robots.txt`
- Canonical URLs
- Structured data / JSON-LD

---

## Obsidian Feature Support Matrix

| Feature | Kiln Support | Notes |
|---------|-------------|-------|
| Wikilinks | Full | All forms: basic, alias, heading, block |
| Markdown | Full | GFM + Obsidian extensions |
| Frontmatter | Full | YAML, used for page metadata |
| Callouts | Full | All types: info, warning, tip, etc. + collapsible |
| Mermaid diagrams | Full | Flowcharts, sequence, Gantt, etc. |
| LaTeX / MathJax | Full | Inline `$...$` and block `$$...$$` |
| Code blocks | Full | Syntax highlighting |
| Tables | Full | Standard Markdown tables |
| Canvas files | Full | Interactive zoom/pan diagrams |
| Image embeds | Full | `![[image.png]]` and `![](path)` |
| Note embeds/transclusion | Full | `![[Other Note]]` |
| Tags | Full | `#tag` in content and frontmatter |
| Footnotes | Full | `[^1]` style |
| Highlights | Full | `==highlighted==` |
| Strikethrough | Full | `~~text~~` |
| Task lists | Full | `- [ ]` and `- [x]` |
| Internal links to headings | Full | `[[Page#Heading]]` |
| Block references | Full | `[[Page#^block-id]]` |

---

## File Structure Kiln Expects

```
vault/
├── index.md              # Homepage — REQUIRED for default mode
├── *.md                  # Content pages (any depth)
├── *.canvas              # Canvas diagrams (optional)
├── assets/               # Images, attachments (any structure)
│   ├── *.png
│   ├── *.jpg
│   └── *.pdf
├── favicon.ico           # Preserved in output (optional)
├── CNAME                 # Preserved in output (optional)
├── _redirects            # Preserved in output (optional)
├── .obsidian/            # IGNORED — Obsidian app config
├── _drafts/              # IGNORED — underscore prefix
└── templates/            # IGNORED in default mode
```

**Rules:**
- `index.md` at vault root is the homepage
- Any `.md` file at any depth becomes a page
- Directories become URL path segments
- Files starting with `.` or `_` are ignored
- `templates/` is ignored in default mode
- Non-markdown, non-recognized files are copied as-is (assets)

---

## Subprocess Integration Details

For bullish-ssg developers writing or modifying the Kiln adapter:

### Exit Codes
- `0` — Success
- Non-zero — Error (details on stderr)

### stdout vs stderr
- `kiln generate` writes progress/success to stdout, errors to stderr
- `kiln doctor` writes diagnostic report to stdout, errors to stderr
- `kiln serve` writes server-started message to stdout

### Timing
- `kiln generate` is fast — typically <1 second for vaults under 1000 notes
- `kiln serve` blocks (runs until killed) — must be run as a subprocess or in background
- `kiln dev` also blocks — combines generate + watch + serve

### Working Directory
- Kiln looks for `kiln.yaml` in the CWD
- All relative paths in flags are resolved relative to CWD
- bullish-ssg should either:
  - Pass absolute paths via `--input`/`--output`, or
  - Set `cwd` when spawning the subprocess

---

## How This Maps to bullish-ssg

| Concept | Kiln | bullish-ssg |
|---------|------|-------------|
| Configuration | `kiln.yaml` (YAML) | `bullish-ssg.toml` (TOML) |
| Vault path | `--input` flag | `vault.link_path` resolved by `VaultResolver` |
| Output path | `--output` flag | `content.output_dir` / `deploy.site_dir` |
| Build command | `kiln generate` | `bullish-ssg build` → `KilnAdapter.build()` |
| Serve command | `kiln serve` | `bullish-ssg serve` → `KilnAdapter.serve()` |
| Link checking | `kiln doctor` | `bullish-ssg check-links` (custom Python implementation) |
| Site URL | `--url` flag | `site.url` in config |
| Site name | `--name` flag | `site.name` in config |
| Theme | `--theme` flag | Not currently exposed |
| Font | `--font` flag | Not currently exposed |
| Deploy | Manual / external | `bullish-ssg deploy` via `gh` CLI |

---

## Key Takeaways

1. **Kiln does the rendering** — bullish-ssg should never parse Markdown to HTML itself.
2. **Kiln does wikilink resolution in HTML output** — bullish-ssg's Python wikilink resolution is for pre-build validation, not rendering.
3. **Kiln cleans the output dir** — never put source files or config in the output directory.
4. **`--url` is critical for production** — without it, no SEO features are generated.
5. **Default mode is stable** — avoid custom mode for now.
6. **Kiln expects `index.md`** — the vault must have a root-level index.md or the generated site has no homepage.
7. **`kiln serve` blocks** — it's a long-running process, not a one-shot command.
8. **`kiln doctor` overlaps with `check-links`** — this is an area where bullish-ssg could delegate instead of reimplementing.
