# Skill: E2E Neovim + Remora Testing with asciinema + agg

Detailed instructions for testing the real Neovim + Remora interaction using asciinema for terminal recording and agg for GIF generation.

---

## Table of Contents

1. [Overview](#1-overview) — What this skill covers and why it matters
2. [Prerequisites](#2-prerequisites) — Required tools, packages, and environment setup
3. [Architecture](#3-architecture) — How the pieces fit together (tmux, asciinema, agg, nv2, Remora LSP)
4. [Core Components](#4-core-components) — TmuxDriver, AsciinemaRecorder, NvimKeys, Scenario protocol
5. [Writing a Scenario](#5-writing-a-scenario) — Step-by-step guide to creating a new E2E scenario
6. [Running Scenarios](#6-running-scenarios) — CLI usage, recording, GIF generation
7. [File Layout](#7-file-layout) — Where everything lives in this repo
8. [Adapting from Remora Source](#8-adapting-from-remora-source) — Key differences when running from the example workspace
9. [Debugging](#9-debugging) — Common failures and how to diagnose them
10. [Reference: Key Sequences](#10-reference-key-sequences) — Remora leader keys and Neovim commands

---

## 1. Overview

E2E tests for Remora validate the **full user experience**: a developer opens Neovim (via `nv2`), the Remora LSP starts, agents are discovered, and user interactions (chat, rewrite, accept/reject proposals) work as expected.

The testing approach:

- **tmux** provides a headless terminal session with fixed geometry (120x35).
- **TmuxDriver** sends keystrokes to tmux and polls `capture-pane` for assertions.
- **AsciinemaRecorder** captures tmux pane snapshots as asciicast v2 (`.cast`) files in a background thread.
- **agg** converts `.cast` files to `.gif` for visual review and documentation.

This is NOT a mock or simulation. It drives a real `nv2` instance with the real Remora LSP, real agent bundles, and a real codebase. The recordings are proof that the system works.

---

## 2. Prerequisites

### Nix Packages (devenv.nix)

The following must be in this repo's `devenv.nix` packages list:

```nix
packages = [
  pkgs.git
  pkgs.uv
  pkgs.asciinema       # terminal recording
  pkgs.asciinema-agg   # .cast -> .gif converter
  pkgs.tmux            # headless terminal driver
];
```

### Python Dependencies

These are needed in the devenv venv (installed automatically via `enterShell`):

- **remora** — the Remora package itself (installed editable from `/home/andrew/Documents/Projects/remora`)
- **pydantic>=2.12** — already a project dependency
- **pytest>=7.0** — dev dependency

No additional pip packages are required. The E2E harness uses only stdlib (`subprocess`, `json`, `threading`, `time`, `re`, `shutil`, `tempfile`, `dataclasses`, `pathlib`).

### Environment

- The devenv shell must be active (`devenv shell` or `direnv allow`).
- `nv2` must be available on PATH (provided by the nixvim import in `devenv.nix`).
- `remora-lsp` must be available on PATH (installed with the remora package).
- The Remora model server must be reachable at the URL in `remora.yaml` (default: `http://remora-server:8000/v1`), OR set `REMORA_LLM_URL` to override.

### Verification

```bash
# All of these must succeed in the devenv shell:
which nv2          # Neovim wrapper from nixvim
which remora-lsp   # Remora LSP server
which tmux         # terminal multiplexer
which asciinema    # terminal recorder
which agg          # .cast -> .gif converter
```

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Scenario Runner (Python)                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. TmuxDriver.start()    — create detached tmux session (120x35)   │
│  2. AsciinemaRecorder.start() — background thread polls capture-pane │
│  3. scenario.run(driver)  — send keystrokes, wait for text/stable   │
│  4. recorder.stop()       — writes .cast file                        │
│  5. cast_to_gif()         — agg converts .cast -> .gif               │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
          │                         │
          │ tmux send-keys          │ tmux capture-pane -p -e
          ▼                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      tmux session (detached)                         │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  nv2 <file>                                                    │  │
│  │  ├── Neovim with remora plugin loaded                         │  │
│  │  │   └── remora.setup({ cmd = "remora-lsp", ... })            │  │
│  │  └── Remora LSP server (spawned by Neovim)                    │  │
│  │      ├── discovers code nodes in src/                         │  │
│  │      ├── loads bundles from /home/.../remora/agents/          │  │
│  │      └── runs agent kernel (model requests via remora.yaml)   │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### Why tmux instead of raw asciinema?

`asciinema rec` requires a real PTY. In headless / CI environments, that's fragile. Instead:

1. We create a detached tmux session with known geometry.
2. We send keys via `tmux send-keys`.
3. We read the screen via `tmux capture-pane -p -e` (with ANSI escapes).
4. The `AsciinemaRecorder` polls `capture-pane` in a background thread and writes asciicast v2 JSONL.

This is 100% reliable in headless environments and produces `.cast` files that `agg` can render to GIF.

---

## 4. Core Components

### 4.1 TmuxDriver

Manages a tmux session lifecycle.

```python
@dataclass
class TmuxDriver:
    session_name: str = ""
    cols: int = 120
    rows: int = 35
```

**Key methods:**

| Method | Description |
|--------|-------------|
| `start(working_dir=None)` | Create a detached tmux session |
| `send_keys(keys, enter=True)` | Send keystrokes (appends Enter by default) |
| `send_raw(keys)` | Send keys without Enter |
| `capture_pane()` | Return current pane text content |
| `wait_for_text(pattern, timeout=30, regex=False)` | Poll until pattern appears |
| `wait_for_stable(stable_seconds=2.0, timeout=30)` | Poll until pane stops changing |
| `kill()` | Destroy the tmux session |

**Context manager usage:**

```python
with TmuxDriver() as driver:
    driver.start(working_dir="/path/to/project")
    driver.send_keys("nv2 src/example_workspace/utils.py")
    driver.wait_for_text("def slugify")
```

### 4.2 AsciinemaRecorder

Records tmux pane snapshots as asciicast v2.

```python
@dataclass
class AsciinemaRecorder:
    output_path: Path
    cols: int = 120
    rows: int = 35
    poll_interval: float = 0.25
```

**Key methods:**

| Method | Description |
|--------|-------------|
| `start(tmux_session)` | Begin recording in a background thread |
| `stop()` | Stop recording, return path to `.cast` file |

**Recording format:** Each frame is a full-screen redraw (`\x1b[H\x1b[2J` + content) written as asciicast v2 JSONL: `[elapsed_seconds, "o", frame_data]`.

### 4.3 NvimKeys

High-level Neovim keystroke API. Encapsulates leader key identity, timing, and tmux send-keys specifics.

```python
class NvimKeys:
    LEADER = "Space"  # nv2 sets mapleader = " "
    
    def __init__(self, driver: TmuxDriver): ...
```

**Key methods:**

| Method | Keys sent | Description |
|--------|-----------|-------------|
| `open_nvim(file, wait_for=...)` | `nv2 {file}` | Launch nv2 and wait for content + LSP |
| `leader_chat()` | `<Space>rc` | Open chat input for agent at cursor |
| `leader_panel()` | `<Space>ra` | Toggle the Remora agent panel |
| `leader_rewrite()` | `<Space>rr` | Request rewrite for agent at cursor |
| `leader_accept()` | `<Space>ry` | Accept pending proposal |
| `leader_reject()` | `<Space>rn` | Reject pending proposal |
| `goto_line(n)` | `:N<Enter>` | Jump to line number |
| `goto_top()` | `gg` | Jump to top of file |
| `move_down(count)` | `j` x count | Move cursor down |
| `enter_insert()` | `i` | Enter insert mode |
| `exit_insert()` | `Escape` | Exit insert mode |
| `save()` | `:w<Enter>` | Write buffer |
| `edit_file(path)` | `:e {path}` | Open a file |
| `focus_right()` | `Ctrl-l` | Move focus to right split |
| `focus_left()` | `Ctrl-h` | Move focus to left split |
| `ex(command)` | `:{command}<Enter>` | Run an ex command |

**Timing constants:**

| Constant | Default | Purpose |
|----------|---------|---------|
| `LEADER_KEY_DELAY` | 0.3s | Between keys in a leader sequence |
| `LEADER_SETTLE` | 1.0s | After a full leader sequence |
| `MODE_SWITCH_DELAY` | 0.3s | After enter/exit insert mode |
| `EX_CMD_DELAY` | 0.5s | After an ex command |
| `LSP_STARTUP_DELAY` | 3.0s | After opening a file, for LSP init |

### 4.4 Scenario Protocol

```python
class Scenario(Protocol):
    @property
    def name(self) -> str: ...        # Short identifier (used in filenames)
    
    @property
    def description(self) -> str: ... # Human-readable description
    
    def run(self, driver: TmuxDriver) -> None: ...  # Execute the scenario
```

### 4.5 cast_to_gif

```python
def cast_to_gif(cast_path: Path, gif_path: Path | None = None, *, speed: float = 1.0, font_size: int = 14) -> Path:
```

Converts a `.cast` file to `.gif` using `agg`. If `agg` is not on PATH, raises `RuntimeError` with install instructions.

### 4.6 DemoProjectGuard

```python
class DemoProjectGuard:
    def __init__(self, files: list[Path] | None = None): ...
```

Snapshots mutable project files before a scenario runs and restores them after, ensuring scenarios that modify source files leave the project clean.

### 4.7 run_scenario

```python
def run_scenario(scenario: Scenario, *, record: bool = True, gif: bool = False, working_dir: str | Path | None = None) -> ScenarioResult:
```

Orchestrates the full lifecycle: TmuxDriver start -> optional recorder start -> scenario.run() -> recorder stop -> optional GIF conversion -> driver kill -> file restore.

---

## 5. Writing a Scenario

### Step-by-step

1. **Create a new file** in `e2e/scenarios/` (e.g., `e2e/scenarios/my_test.py`).

2. **Define a dataclass** implementing the Scenario protocol:

```python
"""My test scenario — description of what it validates."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from e2e.harness import TmuxDriver
from e2e.keys import NvimKeys

# Project root (this repo)
PROJECT_ROOT = Path(__file__).parent.parent.parent


@dataclass
class MyTestScenario:
    """Description of what this scenario tests."""

    name: str = "my_test"
    description: str = "One-line description for CLI listing"

    def run(self, driver: TmuxDriver) -> None:
        nv = NvimKeys(driver)
        target_file = PROJECT_ROOT / "src" / "example_workspace" / "utils.py"

        # Beat 1: Open nv2 on the target file
        nv.open_nvim(target_file, wait_for="def slugify")

        # Beat 2: Wait for Remora plugin to initialize
        driver.wait_for_text("[Remora]", timeout=15)

        # Beat 3: Navigate to a function
        nv.goto_line(12)  # slugify function

        # Beat 4: Chat with the agent
        nv.leader_chat()
        time.sleep(0.5)
        nv.keys("what do you do?", delay=1)
        nv.raw("Escape", delay=0.5)
        nv.raw("Enter", delay=5)

        # Beat 5: Verify response
        driver.wait_for_text("slug", timeout=15)

        # Beat 6: Final stable state
        driver.wait_for_stable(stable_seconds=2.0, timeout=10)
```

3. **Register it** in `e2e/scenarios/__init__.py`:

```python
from e2e.scenarios.my_test import MyTestScenario

ALL_SCENARIOS: dict[str, type] = {
    # ... existing scenarios ...
    "my_test": MyTestScenario,
}
```

### Scenario Design Patterns

**Pattern 1: Assert on pane content**
```python
content = driver.capture_pane()
assert "expected text" in content, f"Expected 'expected text' in pane:\n{content}"
```

**Pattern 2: Wait for text, then act**
```python
driver.wait_for_text("[Remora]", timeout=15)  # LSP ready
nv.leader_chat()                                # Now safe to interact
```

**Pattern 3: Edit + cascade**
```python
nv.goto_line(12)
nv.find_char(")")
nv.enter_insert()
nv.type_in_insert(", timeout: int = 30", enter=False)
nv.exit_insert()
nv.save()           # Triggers content_changed event -> cascade
time.sleep(8)       # Wait for cascade to propagate
```

**Pattern 4: Multi-file navigation**
```python
nv.open_nvim(file_a, wait_for="def function_a")
# ... interact with file_a ...
nv.edit_file(file_b, delay=3)  # Switch to another file
driver.wait_for_text("def function_b", timeout=10)
```

**Pattern 5: Protect mutable files**

If your scenario modifies project files (edits saved via `:w`), use `DemoProjectGuard`:

```python
from e2e.harness import DemoProjectGuard

guard = DemoProjectGuard(files=[
    PROJECT_ROOT / "src" / "example_workspace" / "utils.py",
])
guard.save()
try:
    # ... scenario that modifies utils.py ...
finally:
    guard.restore()
```

Note: `run_scenario()` already uses `DemoProjectGuard` internally with a default file list. If your scenario only modifies the standard mutable files, you don't need to manage this manually.

### Timing Guidelines

| Action | Recommended wait |
|--------|-----------------|
| After `nv.open_nvim()` | Built-in: waits for text + 3s LSP delay |
| After `nv.leader_chat()` | 0.5s before typing |
| After typing chat message + Enter | 5-10s for model response |
| After `:w` (save triggering cascade) | 5-10s for cascade propagation |
| After `nv.leader_accept/reject()` | 3s (default settle) |
| After `nv.leader_panel()` | 2s (default settle) |
| Final stabilization | `wait_for_stable(stable_seconds=2.0)` |

---

## 6. Running Scenarios

### CLI Runner

```bash
# From the repo root, inside devenv shell:

# Run all scenarios with recording
python -m e2e.run

# Run a specific scenario
python -m e2e.run --scenario startup

# List available scenarios
python -m e2e.run --list

# Record + convert to GIF
python -m e2e.run --gif

# Run without recording (faster, for debugging)
python -m e2e.run --no-record

# Combine: specific scenario with GIF output
python -m e2e.run --scenario chat --gif
```

### Startup Attach Validation (Required)

`python -m e2e.run --scenario startup` can pass without proving a live remora client attach.
For startup regressions, always run this direct headless probe and require `REMORA_CLIENTS>=1`:

```bash
devenv shell -- nv2 --headless remora_demo/companion/demo/harness.py \
  "+lua vim.defer_fn(function() local clients=vim.lsp.get_clients({name='remora'}); print('REMORA_CLIENTS=' .. tostring(#clients)); vim.cmd('qa!') end, 10000)"
```

If output contains `REMORA_CLIENTS=0`, treat startup as failed regardless of scenario PASS.

### Output

Recordings are saved to `e2e/output/`:

```
e2e/output/
├── startup_20260303_143012.cast      # asciicast v2 recording
├── startup_20260303_143012.gif       # GIF (if --gif used)
├── chat_20260303_143045.cast
└── chat_20260303_143045.gif
```

### Playback

```bash
# Play a recording in the terminal
asciinema play e2e/output/startup_20260303_143012.cast

# Play at 2x speed
asciinema play -s 2 e2e/output/startup_20260303_143012.cast

# Convert to GIF manually
agg e2e/output/startup_20260303_143012.cast e2e/output/startup.gif --speed 1.5 --font-size 14
```

---

## 7. File Layout

```
remora-example-workspace/
├── e2e/
│   ├── __init__.py              # Package docstring
│   ├── harness.py               # TmuxDriver, AsciinemaRecorder, run_scenario, cast_to_gif
│   ├── keys.py                  # NvimKeys — high-level keystroke API
│   ├── run.py                   # CLI entry point (python -m e2e.run)
│   ├── scenarios/
│   │   ├── __init__.py          # ALL_SCENARIOS registry
│   │   ├── startup.py           # LSP startup + agent discovery
│   │   ├── chat.py              # Chat with an agent
│   │   └── ...                  # Additional scenarios
│   └── output/                  # .cast and .gif files (gitignored)
├── src/
│   └── example_workspace/       # The codebase under test
│       ├── utils.py             # 5 functions (slugify, chunk_list, etc.)
│       ├── models.py            # User, Project models
│       └── service.py           # Service layer with cross-module deps
└── remora.yaml                  # Remora config (bundle_root, model URL, etc.)
```

---

## 8. Adapting from Remora Source

The E2E harness in the Remora source repo (`/home/andrew/Documents/Projects/remora/e2e/`) was designed for the `remora_demo/project/` demo codebase. When adapting it for this example workspace, the key differences are:

### 8.1 Project Root

| Remora source | Example workspace |
|---------------|-------------------|
| `DEMO_PROJECT = .../remora_demo/project` | `PROJECT_ROOT = .../remora-example-workspace` |
| `nv2 {DEMO_PROJECT}/src/configlib/loader.py` | `nv2 {PROJECT_ROOT}/src/example_workspace/utils.py` |

### 8.2 Mutable Files

Update `DemoProjectGuard` file list to reference this workspace's source files:

```python
_MUTABLE_FILES = [
    PROJECT_ROOT / "src" / "example_workspace" / "utils.py",
    PROJECT_ROOT / "src" / "example_workspace" / "models.py",
    PROJECT_ROOT / "src" / "example_workspace" / "service.py",
    PROJECT_ROOT / "tests" / "test_utils.py",
    PROJECT_ROOT / "tests" / "test_models.py",
]
```

### 8.3 Wait-for Text

Scenarios must match the actual content of this workspace's files:

| Remora demo | Example workspace |
|-------------|-------------------|
| `wait_for="def load_config"` | `wait_for="def slugify"` |
| `wait_for="class SchemaError"` | `wait_for="class User"` |

### 8.4 Working Directory

The `run.py` CLI should set `working_dir` to this repo's root, not `remora_demo/project`:

```python
WORKING_DIR = Path(__file__).parent.parent  # repo root
```

### 8.5 nv2 Command

nv2 is the same — it's provided by the shared nixvim import. The Remora plugin auto-setup in `devenv.nix` already points `extraRuntimePaths` at the remora source tree. No changes needed.

---

## 9. Debugging

### Problem: "Timed out waiting for pattern"

The most common failure. Causes:

1. **LSP didn't start** — check that `remora-lsp` is on PATH and `remora.yaml` is valid.
2. **Model server unreachable** — check `REMORA_LLM_URL` / `remora.yaml` model URL.
3. **Wrong wait_for text** — the file content doesn't match what you're looking for.
4. **Insufficient timeout** — model responses can take 10+ seconds.

**Diagnosis:** Add a `driver.capture_pane()` call and print/log the result to see what's actually on screen.

### Problem: "agg not found in PATH"

The devenv shell doesn't have `pkgs.asciinema-agg`. Verify your `devenv.nix` includes it, then re-enter the shell (`direnv reload` or `devenv shell`).

### Problem: "Failed to create tmux session"

Another tmux session with the same name may exist from a crashed run. Kill it:

```bash
tmux kill-session -t remora-e2e-*
```

### Problem: "nv2 command not found"

The nixvim devenv module isn't loaded. Verify `imports = [ /home/.../nixvim/devenv.nix ];` is in `devenv.nix`.

### Problem: Scenario passes but GIF is blank/garbled

The recorder captures ANSI escapes from `capture-pane -e`. If tmux or the terminal doesn't support 256-color, the escapes may be wrong. Verify `TERM=xterm-256color` in the tmux session.

### Inspecting a Recording

```bash
# View raw .cast file (JSONL)
head -5 e2e/output/startup_20260303_143012.cast

# First line is the header:
# {"version": 2, "width": 120, "height": 35, "timestamp": 1741012212, "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"}}

# Subsequent lines are frames:
# [0.25, "o", "\x1b[H\x1b[2J...frame content..."]
```

---

## 10. Reference: Key Sequences

### Remora Leader Keys (prefix: `<Space>r`)

| Sequence | Action |
|----------|--------|
| `<Space>rc` | Chat with agent at cursor |
| `<Space>ra` | Toggle agent panel |
| `<Space>rr` | Request rewrite for agent at cursor |
| `<Space>ry` | Accept pending proposal |
| `<Space>rn` | Reject pending proposal |

### Neovim Navigation

| Key | Action |
|-----|--------|
| `gg` | Go to top of file |
| `:N<Enter>` | Go to line N |
| `j` / `k` | Move down / up |
| `f{char}` | Jump to next occurrence of char |
| `i` | Enter insert mode |
| `Escape` | Exit insert mode |
| `:w` | Save buffer |
| `:e {path}` | Open file |
| `Ctrl-l` / `Ctrl-h` | Focus right / left split |
| `Ctrl-w {dir}` | Focus window by direction |

### tmux Commands (used internally by TmuxDriver)

| Command | Purpose |
|---------|---------|
| `tmux new-session -d -s NAME -x 120 -y 35` | Create detached session |
| `tmux send-keys -t NAME "text" Enter` | Send keystrokes |
| `tmux capture-pane -t NAME -p` | Capture pane text |
| `tmux capture-pane -t NAME -p -e` | Capture with ANSI escapes |
| `tmux kill-session -t NAME` | Destroy session |
