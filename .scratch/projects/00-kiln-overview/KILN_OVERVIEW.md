# Kiln Overview for Bullish-SSG Developers

## What is Kiln?

**Kiln** is a static site generator specifically designed for Obsidian vaults. It's written in Go and provides 1:1 feature parity with Obsidian, meaning if something works in Obsidian, it works in Kiln.

**Key Repository:** https://github.com/otaleghani/kiln  
**Documentation:** https://kiln.talesign.com/  
**License:** MIT

## Why Bullish-SSG Uses Kiln

Bullish-SSG is essentially a **Python wrapper and workflow orchestrator** around Kiln. Instead of reimplementing Obsidian-to-HTML rendering (a massive undertaking), we:

1. **Prepare** the vault (symlink management, validation)
2. **Orchestrate** Kiln commands via subprocess
3. **Deploy** the generated site to GitHub Pages

This gives us the best of both worlds: Kiln's battle-tested Obsidian rendering + Python's ecosystem for automation and GitHub integration.

---

## Kiln Architecture

### Core Philosophy: "Zero Config, Zero Compromise"

- **Single binary:** No Node.js, no dependencies, just one executable
- **Obsidian parity:** Wikilinks, Canvas, Mermaid, LaTeX, callouts — all work out of the box
- **Speed:** Written in Go, uses HTMX for client-side navigation
- **Standards:** Outputs vanilla HTML/CSS/JS that works anywhere

### Two Operating Modes

#### 1. Default Mode (Vault Mirror)
Takes your Obsidian vault and mirrors it 1:1 to a static site.

```
vault/                          public/
├── index.md        ───►        ├── index.html
├── about.md                    ├── about/index.html
├── assets/                     ├── assets/
└── blog/                       └── blog/
    └── post.md                     └── post/index.html
```

**Use case:** Digital gardens, documentation sites, wikis, knowledge bases

#### 2. Custom Mode (Obsidian as Headless CMS)
Transforms Obsidian into a structured content management system.

```
my-blog/
├── index.md              # Homepage content
├── index.html            # Homepage template
├── env.json              # Global site variables
└── posts/                # Collection
    ├── config.json       # Schema definition
    ├── layout.html       # Template for posts
    └── first-post.md     # Content
```

**Use case:** Blogs, portfolios, structured content sites

**Note:** Custom Mode is still in early stages (as of v0.9.5)

---

## Key Commands

### `kiln generate` — Build Your Site

**Basic usage:**
```bash
kiln generate --input ./docs --output ./public
```

**Important flags:**
- `--input, -i`: Source vault directory (default: `./vault`)
- `--output, -o`: Output directory (default: `./public`)
- `--theme, -t`: Theme name (default: `default`)
- `--font, -f`: Font family (default: `inter`)
- `--url, -u`: Base URL for SEO/sitemap
- `--name, -n`: Site name
- `--mode, -m`: `default` or `custom`
- `--layout, -L`: Page layout
- `--flat-urls`: Generate `note.html` instead of `note/index.html`

**What it generates:**
- HTML pages for every Markdown note
- CSS/JS bundles (theme, navigation, search, graphs)
- SEO files (sitemap.xml, robots.txt when URL provided)
- Static assets (images, attachments copied as-is)
- Special files (CNAME, favicon.ico, _redirects preserved)

### `kiln serve` — Local Development Server

**Basic usage:**
```bash
kiln serve --output ./public
```

**Features:**
- Serves static files with proper MIME types
- Clean URL support (`/about` → `about.html` or `about/index.html`)
- Base path handling (respects subdirectory URLs)
- Custom 404 page support (serves `404.html` if present)
- Port 8080 by default

**Why you need it:**
Browser security restrictions prevent opening HTML files directly from disk. Client-side navigation and AJAX features require a real HTTP server.

### `kiln doctor` — Link Validation

**Basic usage:**
```bash
kiln doctor --input ./docs
```

**Checks:**
- Broken wikilinks (`[[Missing Note]]`)
- Renamed files with stale references
- Missing image references
- Missing canvas files
- Handles aliases: `[[Note|Alias]]`
- Handles anchors: `[[Note#Section]]`

**Exit codes:**
- 0: No broken links
- Non-zero: Broken links found

### `kiln init` — Scaffold New Project

**Basic usage:**
```bash
kiln init --input ./vault
```

**Creates:**
```
vault/
└── Home.md           # Starter note
kiln.yaml            # Config file (commented defaults)
```

### `kiln dev` — Watch Mode (Development)

Combines build + watch + serve in one command:
```bash
kiln dev --input ./docs --output ./public
```

---

## Configuration

### `kiln.yaml` — Optional Config File

Place in project root to set defaults instead of passing flags every time:

```yaml
name: "My Digital Garden"
url: "https://notes.example.com"
theme: "nord"
font: "inter"
layout: "default"
input: "./vault"
output: "./public"
```

**CLI flags always override config values.**

---

## Obsidian Features Supported

### Content Rendering
- **Wikilinks:** `[[Page]]`, `[[Page|Alias]]`, `[[Page#Heading]]`
- **Canvas files:** Interactive zoom/pan diagrams
- **Mermaid:** Flowcharts, sequence diagrams, Gantt charts
- **Math/LaTeX:** Via MathJax
- **Callouts:** Info boxes, warnings, collapsible blocks
- **Code blocks:** Syntax highlighting
- **Tables:** Standard Markdown tables
- **Images:** Embedded and referenced

### Navigation
- **File explorer:** Sidebar mirroring vault structure
- **Global graph:** Visualize entire vault connections
- **Local graph:** Per-page network view
- **Search:** Full-text filtering
- **Tags:** Browse by topic
- **Backlinks:** See what links to current page
- **Table of contents:** Auto-generated from headings

### UI/UX
- **Themes:** Large collection (Nord, Dracula, Solarized, etc.)
- **Fonts:** Typography options (Inter, JetBrains Mono, etc.)
- **Light/Dark mode:** Every theme has both variants
- **Layouts:** Control page structure
- **Client-side navigation:** HTMX-powered instant page loads

### SEO
- Auto-generated meta tags
- Open Graph tags for social sharing
- Sitemap.xml (when URL provided)
- Robots.txt
- Canonical URLs
- Structured data

---

## Deployment Options

Kiln outputs standard static files deployable anywhere:

- **GitHub Pages:** Native support
- **Netlify:** Drag-and-drop or CI/CD
- **Vercel:** Git integration
- **Cloudflare Pages:** Edge deployment
- **Any web server:** Nginx, Apache, Caddy

---

## Integration Points for Bullish-SSG

### Where Bullish-SSG Fits

```
┌─────────────────────────────────────────────┐
│        Bullish-SSG (Python)                 │
│  ┌──────────────────────────────────────┐  │
│  │  • Vault management (symlinks)        │  │
│  │  • Content validation               │  │
│  │  • Configuration (TOML)             │  │
│  │  • GitHub Pages deployment          │  │
│  └──────────────────────────────────────┘  │
└─────────────────────┬───────────────────────┘
                      │ Subprocess calls
                      ▼
┌─────────────────────────────────────────────┐
│            Kiln (Go binary)                 │
│  ┌──────────────────────────────────────┐  │
│  │  • Markdown → HTML conversion       │  │
│  │  • Wikilink resolution              │  │
│  │  • Theme/CSS/JS generation        │  │
│  │  • Static site output               │  │
│  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### Command Mapping

| Bullish-SSG | Kiln Equivalent | Purpose |
|-------------|-----------------|---------|
| `build` | `kiln generate` | Compile vault to static site |
| `serve` | `kiln serve` | Local development server |
| `validate` | Custom validation | Frontmatter, structure checks |
| `check-links` | `kiln doctor` | Broken link detection |
| `deploy` | `gh pages deploy` | GitHub Pages deployment |

### Key Files Kiln Expects

Kiln works with standard Obsidian vault structure:

```
vault/
├── index.md              # Homepage (required)
├── *.md                  # Content notes
├── *.canvas              # Canvas diagrams
├── assets/               # Images, attachments
│   └── *.png
├── templates/            # Templates (ignored by default)
└── .obsidian/            # Obsidian config (ignored)
```

**Notes:**
- Files/folders starting with `.` or `_` are ignored
- `templates/` folder is typically excluded
- Images can be in vault root or `assets/` folder
- Canvas files (`.canvas`) are JSON format

---

## Development Workflow

### Typical Kiln Workflow

```bash
# 1. Install Kiln
go install github.com/otaleghani/kiln/cmd/kiln@latest

# 2. Scaffold project
kiln init --input ./my-vault

# 3. Check for broken links
kiln doctor --input ./my-vault

# 4. Build the site
kiln generate \
  --input ./my-vault \
  --output ./public \
  --name "My Notes" \
  --url "https://notes.example.com" \
  --theme nord

# 5. Preview locally
kiln serve --output ./public --port 8080

# 6. Deploy
# (Copy ./public contents to your static host)
```

### Development Mode

```bash
# Auto-rebuild on changes
kiln dev --input ./my-vault --output ./public
```

---

## Installation

### Via Go (Recommended)

```bash
go install github.com/otaleghani/kiln/cmd/kiln@latest
```

### Pre-compiled Binaries

Available for:
- macOS (Intel & Apple Silicon)
- Linux (x86_64, ARM64)
- Windows (x86_64)

Download from [GitHub Releases](https://github.com/otaleghani/kiln/releases)

### Verify Installation

```bash
kiln --version
```

---

## Important Notes for Bullish-SSG

### Version Compatibility

- Kiln is actively developed (v0.9.5 as of March 2026)
- Custom Mode is still experimental
- Default Mode is stable and production-ready

### Configuration File Location

Kiln looks for `kiln.yaml` in the **current working directory**, not necessarily next to the vault. Bullish-SSG should:

1. Change to the project root before running Kiln commands
2. Or pass full paths via `--input` and `--output` flags
3. Or generate a temporary `kiln.yaml` in the working directory

### Subprocess Integration

Kiln commands return exit codes:
- `0` = Success
- Non-zero = Error (check stderr for details)

Bullish-SSG should capture both stdout and stderr for debugging.

### Output Directory Behavior

- **Kiln cleans the output directory before each build**
- Any files in `--output` will be deleted
- Don't use the output directory for source files

### URL Handling

- Always provide `--url` for production builds
- Required for sitemap.xml and canonical URLs
- Should match your deployment domain exactly
- Example: `https://username.github.io/repo-name/`

---

## Resources

- **GitHub:** https://github.com/otaleghani/kiln
- **Documentation:** https://kiln.talesign.com/
- **Demo:** https://kiln.talesign.com/ (Kiln's own docs, built with Kiln)
- **Issues:** https://github.com/otaleghani/kiln/issues
- **Roadmap:** Check GitHub issues for planned features

---

## Summary

Kiln is the rendering engine that powers Bullish-SSG. As a developer on this project:

1. **Don't reimplement rendering** — delegate to Kiln
2. **Understand Kiln's expectations** — standard Obsidian vault structure
3. **Use subprocess calls** — Kiln is a separate binary
4. **Handle exit codes** — check for errors
5. **Respect the output directory** — it's cleaned on each build
6. **Provide URLs for production** — needed for SEO features

Kiln handles the hard work of Obsidian-to-HTML conversion. Bullish-SSG handles the workflow: vault management, validation, and deployment.
