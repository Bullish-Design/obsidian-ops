# Skill: E2E Live Scenario Verification & Refinement

Iterative methodology for running E2E Neovim + Remora scenarios against a real LLM server, examining output, writing structured test reports, and refining the test infrastructure until scenarios reliably validate the intended behavior.

---

## Table of Contents

1. [Overview](#1-overview) — What this skill covers and when to use it
2. [Prerequisites](#2-prerequisites) — What must be true before starting a verification cycle
3. [The Verification Loop](#3-the-verification-loop) — The core run-examine-report-fix cycle
4. [Running a Scenario](#4-running-a-scenario) — Commands, environment, expected output
5. [Examining Output](#5-examining-output) — How to parse .cast files, read pane captures, and extract evidence
6. [Writing a Test Report](#6-writing-a-test-report) — The three-section report format with examples
7. [Diagnosing Failures](#7-diagnosing-failures) — Common failure modes and how to investigate each
8. [Fixing Scenarios](#8-fixing-scenarios) — Patterns for timing, content matching, and assertion fixes
9. [Fixing keys.py](#9-fixing-keyspy) — When and how to modify the keystroke API
10. [Adding Visual Verification Helpers](#10-adding-visual-verification-helpers) — Higher-level abstractions for keys.py
11. [Re-verification](#11-re-verification) — Running fixed scenarios and confirming the fix
12. [Cast File Reference](#12-cast-file-reference) — Asciicast v2 format, parsing, frame extraction
13. [Checklist](#13-checklist) — Quick-reference checklist for each verification pass

---

## 1. Overview

This skill covers the **iterative verification cycle** for E2E scenarios that run against a real vLLM model server. It is complementary to the `e2e-neovim-testing.md` skill, which covers *writing* scenarios and the harness architecture. This skill covers *running* them against production-like infrastructure and systematically improving them.

### When to Use This Skill

- You have written E2E scenarios and need to verify they work with **real model responses** (not just harness infrastructure tests).
- A scenario is failing or producing unexpected results and you need a structured approach to diagnose and fix it.
- You need to add new visual verification capabilities to `keys.py` based on what you observe in real runs.
- You are onboarding a new scenario and want to validate its behavior end-to-end before declaring it ready.

### Key Principle: Observe First, Assert Second

E2E tests against a real LLM are **non-deterministic** by nature. Model responses vary. Timing varies. The correct approach is:

1. **Run without assertions** — let the scenario execute, record everything.
2. **Examine the recording** — understand what *actually* happens (pane content, timing, UI transitions).
3. **Write assertions that match reality** — not what you *hope* happens, but what you *observed* happens.
4. **Use tolerant patterns** — regex, substring matching, wait-for-stable instead of exact-match.

---

## 2. Prerequisites

Before starting a live verification cycle, confirm ALL of the following:

### 2.1 Environment

```bash
# All commands run inside devenv shell
devenv shell -- which nv2          # Neovim wrapper
devenv shell -- which remora-lsp   # Remora LSP server
devenv shell -- which tmux         # terminal multiplexer
devenv shell -- which asciinema    # recorder (optional for playback)
devenv shell -- which agg          # .cast -> .gif converter
```

### 2.2 Model Server

```bash
# Must return a JSON response with the model list
devenv shell -- curl -s http://remora-server:8000/v1/models
```

Expected output includes `"id":"Qwen/Qwen3-4B-Instruct-2507-FP8"`. If the server is unreachable, **stop** — no live scenarios will work.

### 2.3 Clean State

```bash
# Kill any leftover tmux sessions from crashed runs
tmux ls 2>&1 | grep "remora-e2e" && tmux kill-server || echo "Clean"

# Verify no stale .remora/ state is interfering
ls -la .remora/ 2>/dev/null   # May or may not exist; that's fine
```

### 2.4 Harness Infrastructure

```bash
# Confirm the harness unit tests still pass
devenv shell -- python -m pytest tests/test_e2e_harness.py -q
```

If the harness tests fail, fix them before running live scenarios.

### 2.5 Smoke Test

```bash
# Run the smoke scenario to verify the basic pipeline works
devenv shell -- python -m e2e.run -s smoke
```

This does not require Remora or the model server. If smoke fails, the problem is in the tmux/recording infrastructure, not the scenarios.

---

## 3. The Verification Loop

The core methodology is a tight loop repeated **per scenario**:

```
+-------------------------------------------+
|  1. RUN the scenario                      |
|     devenv shell -- python -m e2e.run     |
|     -s <name> --gif                       |
+-------------------------------------------+
|  2. EXAMINE the output                    |
|     - Read the .cast file (JSONL)         |
|     - Strip ANSI to see plain text        |
|     - Check timestamps for timing         |
|     - Look at the GIF visually            |
+-------------------------------------------+
|  3. REPORT findings                       |
|     - Pre-test expectations               |
|     - Post-test observations              |
|     - Changes needed                      |
+-------------------------------------------+
|  4. FIX the scenario / keys.py            |
|     - Adjust timing constants             |
|     - Fix content patterns                |
|     - Add missing waits                   |
|     - Improve assertions                  |
+-------------------------------------------+
|  5. RE-RUN -- go back to step 1           |
|     Loop until the scenario passes        |
|     reliably and tests the right things   |
+-------------------------------------------+
```

### Iteration Discipline

- **One scenario at a time.** Do not try to fix all three at once.
- **Order: startup -> chat -> discovery.** Each builds on the previous. If startup doesn't work, chat definitely won't.
- **Keep notes per iteration.** Each re-run should produce a new observation in the test report (append, don't overwrite).
- **Maximum 5 iterations per scenario.** If it's not converging, document the issue in `ISSUES.md` and move on.

---

## 4. Running a Scenario

### Basic Run (with recording)

```bash
devenv shell -- python -m e2e.run -s startup
```

This produces:
- Console output showing PASS/FAIL, duration, recording path
- A `.cast` file in `e2e/output/` (e.g., `startup_20260303_143012.cast`)

### Run with GIF

```bash
devenv shell -- python -m e2e.run -s startup --gif
```

Also produces a `.gif` alongside the `.cast`. Useful for visual review.

### Run without Recording (faster debugging)

```bash
devenv shell -- python -m e2e.run -s startup --no-record
```

Skips the recorder thread. Use when iterating quickly on assertion logic.

### What the Runner Does

1. Creates a `TmuxDriver` with a fresh detached session (120x35).
2. Starts an `AsciinemaRecorder` (background thread polling `capture-pane`).
3. Calls `scenario.run(driver)` — the scenario sends keystrokes and makes assertions.
4. Stops the recorder, optionally converts to GIF.
5. Kills the tmux session.
6. Restores any modified project files via `ProjectGuard`.

### Interpreting Results

| Output | Meaning |
|--------|---------|
| `[PASS] startup (18.3s)` | Scenario completed without exceptions |
| `[FAIL] startup (31.2s)` | An assertion or timeout raised an exception |
| `Error: Timed out after 15s waiting for pattern: '[Remora]'` | The expected text never appeared on screen |
| `Error: Expected 'def slugify' in pane` | Assertion failed -- file content not visible |

**IMPORTANT:** A `[PASS]` only means no exceptions were raised. It does NOT mean the scenario tested the right things. You must still examine the recording to verify the scenario actually exercised the intended behavior.

---

## 5. Examining Output

After a run, you need to examine what actually happened. There are three sources of truth:

### 5.1 Console Output

The runner prints the result. For failures, the error message is the first clue. For passes, the duration tells you if timing was reasonable.

### 5.2 The .cast File (Primary Evidence)

The `.cast` file is asciicast v2 JSONL. Each line after the header is a frame:

```json
[elapsed_seconds, "o", "frame_content_with_ansi_escapes"]
```

#### Reading the raw .cast file

```bash
# View the header
head -1 e2e/output/startup_20260303_143012.cast

# Count frames
wc -l e2e/output/startup_20260303_143012.cast

# View last 3 frames (most interesting -- final state)
tail -3 e2e/output/startup_20260303_143012.cast
```

#### Extracting plain text from frames

The frames contain ANSI escape sequences. To see what the user would see, strip them:

```python
import json, re

def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)

def read_cast_frames(cast_path: str) -> list[tuple[float, str]]:
    """Parse a .cast file and return (timestamp, plain_text) tuples."""
    frames = []
    with open(cast_path) as f:
        next(f)  # skip header
        for line in f:
            ts, _type, data = json.loads(line)
            plain = strip_ansi(data)
            # Remove the screen-reset prefix
            plain = plain.replace('\x1b[H\x1b[2J', '')
            frames.append((ts, plain))
    return frames
```

#### What to look for in frames

| Question | How to answer |
|----------|--------------|
| Did nv2 open the file? | Look for file content (`def slugify`, `class User`) in early frames |
| Did `[Remora]` appear? | Search frames for the literal string `[Remora]` |
| Did the agent panel open? | Look for a vertical split -- content appearing in the right half |
| Did a chat response appear? | Search for response text after the chat message was sent |
| What was the timing? | Compare timestamps of key frames (file open -> Remora init -> response) |

### 5.3 The GIF (Visual Confirmation)

If you generated a GIF, open it to see the full recording visually. This is the most intuitive way to verify what happened but is not parseable programmatically.

### 5.4 One-Shot Pane Capture (during development)

When iterating, you can add temporary `print(driver.capture_pane())` calls inside a scenario to dump the current screen state to the console. Remove these before finalizing.

---

## 6. Writing a Test Report

Each scenario gets a test report with **exactly three sections**. Write these to the project directory (e.g., `.scratch/projects/verify-e2e-live/startup-report.md`).

### Format

```markdown
# Test Report: <scenario_name>

## Run Info
- **Date**: YYYY-MM-DD HH:MM
- **Result**: PASS / FAIL
- **Duration**: X.Xs
- **Cast file**: e2e/output/<name>_<timestamp>.cast
- **Iteration**: N (which attempt this is)

## 1. Pre-Test Expectations

What you expected to see before running the scenario. Be specific:

- Expected nv2 to open `src/example_workspace/utils.py` within 5s
- Expected `[Remora]` notification to appear within 15s of file open
- Expected `def slugify` visible in the pane after file loads
- Expected pane to stabilize within 2s after LSP finishes

## 2. Post-Test Observations

What actually happened, based on examining the .cast file and console output:

- nv2 opened the file in 2.3s -- `def slugify` visible at frame timestamp 2.3
- `[Remora]` appeared at timestamp 8.7 -- within the 15s timeout
- After `[Remora]`, the pane showed extmarks/virtual text on lines 5-15
- Pane stabilized at timestamp 12.1 -- total scenario duration 14.2s
- **Unexpected**: saw an error notification "[Remora] connection failed" at 6.2s
  before the successful connection at 8.7s (retry behavior)

## 3. Changes / Fixes / Improvements

Based on observations, what needs to change:

- **Timing**: increase `LSP_STARTUP_DELAY` from 3s to 5s -- LSP init takes ~6s
- **Assertion**: change `wait_for_text("[Remora]", timeout=15)` to use regex
  `r"\[Remora\].*(?:ready|connected|discovered)"` to distinguish success from errors
- **New helper needed**: `wait_for_agent_ready()` that waits for both `[Remora]`
  AND a stable pane, since `[Remora]` appears before agents are fully discovered
- **Scenario flow**: add a `capture_pane()` after `wait_for_stable()` and assert
  on specific agent markers (virtual text, extmarks) not just file content
```

### Report Rules

1. **Be factual.** Report what you observed, not what you wished happened.
2. **Include timestamps.** Reference .cast frame timestamps for key events.
3. **Quote actual content.** Copy-paste relevant pane content snippets.
4. **Append iterations.** On re-runs, add a new section `## Iteration 2` (etc.) below the original report rather than overwriting. This preserves the history of what was tried.

---

## 7. Diagnosing Failures

### 7.1 Timeout Failures

**Symptom:** `Timed out after Xs waiting for pattern: 'XXX'`

**Diagnosis steps:**

1. Look at the .cast file's last few frames -- what IS on screen?
2. Check if the expected text appears in a slightly different form (e.g., `[Remora] ready` vs `[Remora] connected`).
3. Check timestamps -- is the operation just slow, or did it never happen?
4. Check if nv2 even started -- look for the Neovim UI (status line, line numbers) in early frames.

**Common causes:**

| Cause | Fix |
|-------|-----|
| Timeout too short | Increase timeout (model responses take 5-30s) |
| Wrong pattern text | Update to match actual output |
| nv2 failed to start | Check that the file path is correct and nv2 is on PATH |
| LSP failed to connect | Check remora.yaml, model server reachability |
| Model server slow/down | Verify with `curl` before running |

### 7.2 Assertion Failures

**Symptom:** `AssertionError: Expected 'X' in pane, got: ...`

**Diagnosis:** The assertion includes the actual pane content. Read it carefully:

- Is the expected text there but with different whitespace or wrapping?
- Is the pane showing an error instead of the expected content?
- Is the assertion running before the content has appeared (race condition)?

**Fix:** Add a `wait_for_text()` or `wait_for_stable()` before the assertion.

### 7.3 Keystroke Failures

**Symptom:** Scenario runs but doesn't do what you expected (e.g., chat message not sent, panel not opened).

**Diagnosis:** Look at the .cast frames around the time the keystroke was sent:

- Did the leader key sequence arrive? (Look for which-key popup or mode change)
- Was Neovim in the right mode? (Normal mode required for leader keys)
- Did the input focus go to the right place?

**Common causes:**

| Cause | Fix |
|-------|-----|
| Neovim was in insert mode | Add `exit_insert()` or `raw("Escape")` before leader keys |
| Leader key timing too fast | Increase `LEADER_KEY_DELAY` |
| which-key ate the keystrokes | Increase `LEADER_KEY_DELAY` to > 0.3s |
| Focus was in wrong pane/window | Add explicit `focus_left()` / `focus_right()` |

### 7.4 Non-Deterministic Failures

**Symptom:** Scenario passes sometimes, fails other times.

**Diagnosis:** This almost always means a timing issue. Run the scenario 3 times and compare .cast timestamps:

- Find the step that varies most in timing.
- The assertion or wait before the next step isn't tolerant enough.

**Fix:** Replace `time.sleep(N)` with `wait_for_text()` or `wait_for_stable()`. Avoid hard-coded sleeps for anything model-dependent.

---

## 8. Fixing Scenarios

### 8.1 Timing Fixes

**Problem:** Hard-coded `time.sleep()` that's sometimes too short.

**Fix:** Replace with event-driven waits:

```python
# BAD: fragile timing
nv.leader_chat()
time.sleep(5)
# Hope the input is ready...

# GOOD: event-driven
nv.leader_chat()
driver.wait_for_text(":", timeout=5)  # Wait for command-line prompt
# OR
driver.wait_for_stable(stable_seconds=0.5, timeout=5)  # Wait for UI to settle
```

### 8.2 Content Matching Fixes

**Problem:** Exact string match fails because content varies.

**Fix:** Use regex or substring:

```python
# BAD: brittle exact match
driver.wait_for_text("[Remora] discovered 5 agents")

# GOOD: tolerant pattern
driver.wait_for_text(r"\[Remora\].*discover", timeout=15, regex=True)
```

### 8.3 Assertion Fixes

**Problem:** Assertion runs before content is ready.

**Fix:** Always wait, then capture, then assert:

```python
# BAD: capture immediately after keystroke
nv.edit_file(service_file)
content = driver.capture_pane()
assert "def create_user" in content  # Might fail -- file not loaded yet

# GOOD: wait for content, then assert
nv.edit_file(service_file, delay=0)  # Don't use edit_file's built-in delay
driver.wait_for_text("def create_user", timeout=10)
content = driver.capture_pane()
assert "def create_user" in content  # Now guaranteed
```

### 8.4 Adding Robustness to the Chat Flow

The chat flow is the most fragile because it involves:
1. Leader key sequence -> which-key popup -> command mode
2. Typing text into an input prompt
3. Sending the message (Enter)
4. Waiting for an LLM response (non-deterministic timing + content)

**Pattern for robust chat testing:**

```python
# Position cursor on the code node
nv.goto_line(12)
time.sleep(0.3)

# Open chat -- verify input prompt appears
nv.leader_chat()
driver.wait_for_stable(stable_seconds=0.5, timeout=5)

# Type message (the input prompt may be in insert mode or command-line mode
# depending on the Remora plugin implementation)
nv.keys("what do you do?", enter=False, delay=0.5)

# Send the message
nv.raw("Enter", delay=0)

# Wait for response -- use a broad pattern since LLM output varies
driver.wait_for_text(
    r"(slug|text|string|convert|function|takes|returns)",
    timeout=30,
    regex=True,
)
```

---

## 9. Fixing keys.py

### When to Modify keys.py

Modify `e2e/keys.py` when:

1. **A timing constant is wrong for ALL scenarios** -- change the default, not per-call overrides.
2. **A new keystroke pattern is needed** -- e.g., a leader key not yet implemented.
3. **A higher-level helper is needed** -- a reusable multi-step operation.

Do NOT modify keys.py for scenario-specific timing -- use per-call overrides instead:

```python
# Scenario-specific: pass delay to the method
nv.leader_chat(settle=2.0)  # This scenario needs extra settle time

# NOT: change the default in keys.py for one scenario
```

### Adding a New Method

Follow the existing patterns:

```python
def leader_status(self, settle: float = 2.0) -> None:
    """``<Space>rs`` -- show agent status."""
    self._leader_seq("r", "s", settle=settle)
```

### Changing Timing Constants

If multiple scenarios need different default timing, the constant is wrong. Look at real .cast timestamps to determine the right value:

```python
# Measured from .cast files:
# - LSP init takes 3-8s across runs
# - So LSP_STARTUP_DELAY = 5.0 is a better default than 3.0
LSP_STARTUP_DELAY = 5.0
```

---

## 10. Adding Visual Verification Helpers

The goal is to make scenario code read like a **script describing what the user sees**, not a sequence of raw keystrokes. These helpers go in `keys.py` as methods on `NvimKeys`.

### Pattern: Composite Wait

```python
def wait_for_remora_ready(self, timeout: float = 30.0) -> str:
    """Wait for Remora LSP to initialize and agents to be discovered.

    Waits for [Remora] notification, then waits for the pane to
    stabilize (agents discovered, virtual text rendered).

    Returns the stable pane content.
    """
    self.driver.wait_for_text("[Remora]", timeout=timeout)
    return self.driver.wait_for_stable(stable_seconds=2.0, timeout=timeout)
```

### Pattern: Assert With Context

```python
def assert_pane_contains(
    self,
    pattern: str,
    *,
    regex: bool = False,
    msg: str = "",
) -> str:
    """Capture pane and assert pattern is present.

    Returns the pane content on success. On failure, includes the
    full pane content in the assertion message for diagnosis.
    """
    content = self.driver.capture_pane()
    if regex:
        import re
        if not re.search(pattern, content):
            raise AssertionError(
                f"{msg or 'Pattern not found'}: {pattern!r}\n"
                f"Pane content:\n{content}"
            )
    else:
        if pattern not in content:
            raise AssertionError(
                f"{msg or 'Text not found'}: {pattern!r}\n"
                f"Pane content:\n{content}"
            )
    return content
```

### Pattern: Chat Cycle

```python
def chat_and_wait(
    self,
    message: str,
    *,
    response_pattern: str = "",
    response_timeout: float = 30.0,
    regex: bool = False,
) -> str:
    """Full chat cycle: open chat, type message, send, wait for response.

    Args:
        message: The chat message to send.
        response_pattern: Text or regex to wait for in the response.
            If empty, waits for pane to stabilize instead.
        response_timeout: How long to wait for the response.
        regex: Whether response_pattern is a regex.

    Returns:
        The pane content after the response appears.
    """
    self.leader_chat()
    self.driver.wait_for_stable(stable_seconds=0.5, timeout=5)
    self.keys(message, enter=False, delay=0.5)
    self.raw("Enter", delay=0)

    if response_pattern:
        return self.driver.wait_for_text(
            response_pattern,
            timeout=response_timeout,
            regex=regex,
        )
    else:
        return self.driver.wait_for_stable(
            stable_seconds=3.0,
            timeout=response_timeout,
        )
```

### Pattern: Panel Verification

```python
def open_panel_and_verify(
    self,
    expected_content: str = "",
    *,
    regex: bool = False,
    timeout: float = 10.0,
) -> str:
    """Open the Remora agent panel and optionally verify its content.

    Opens <Space>ra, focuses right into the panel, waits for stable
    content, optionally asserts on content, then focuses back left.

    Returns the pane content after panel is open.
    """
    self.leader_panel()
    self.focus_right(delay=0.5)
    content = self.driver.wait_for_stable(
        stable_seconds=1.0,
        timeout=timeout,
    )
    if expected_content:
        if regex:
            import re
            assert re.search(expected_content, content), (
                f"Panel content mismatch: {expected_content!r}\n"
                f"Pane content:\n{content}"
            )
        else:
            assert expected_content in content, (
                f"Panel content mismatch: {expected_content!r}\n"
                f"Pane content:\n{content}"
            )
    self.focus_left(delay=0.3)
    return content
```

### Pattern: Pane Snapshot for Comparison

```python
def snapshot(self) -> str:
    """Capture and return the current pane content.

    Useful for before/after comparisons:

        before = nv.snapshot()
        nv.save()
        time.sleep(5)
        after = nv.snapshot()
        assert before != after, "Expected pane to change after save"
    """
    return self.driver.capture_pane()
```

### Pattern: Open File and Wait for Ready

```python
def open_file_and_wait(
    self,
    file: str | Path,
    *,
    wait_for: str = "",
    wait_for_remora: bool = True,
    timeout: float = 30.0,
) -> str:
    """Open a file in nv2 and wait for it to be fully ready.

    Combines open_nvim + optional Remora init wait into one call.

    Args:
        file: Path to the file to open.
        wait_for: Text to confirm file is loaded (e.g., "def slugify").
        wait_for_remora: Whether to also wait for [Remora] notification.
        timeout: Max wait time.

    Returns:
        The stable pane content.
    """
    self.open_nvim(file, wait_for=wait_for, timeout=timeout, lsp_delay=0)
    if wait_for_remora:
        self.driver.wait_for_text("[Remora]", timeout=timeout)
    return self.driver.wait_for_stable(stable_seconds=2.0, timeout=timeout)
```

### Design Principles for Helpers

1. **Return pane content.** Every helper that waits should return what it saw -- callers can assert on it or ignore it.
2. **Accept timeouts.** Never hard-code timeouts inside helpers. Always accept a parameter with a generous default.
3. **Use wait-for, not sleep.** Helpers must be event-driven. `time.sleep()` inside helpers is a code smell (except for tiny keystroke delays).
4. **Compose, don't duplicate.** Helpers should call existing NvimKeys methods and TmuxDriver methods, not re-implement keystroke logic.
5. **Fail with context.** When a helper raises, include the pane content in the error so diagnosis doesn't require re-running.

---

## 11. Re-verification

After fixing a scenario or keys.py:

1. **Re-run the same scenario.** Same command as before.
2. **Examine the new .cast file.** Compare with the previous run's .cast -- did the fix help?
3. **Append to the test report.** Add an `## Iteration N` section documenting what changed and what the result was.
4. **Check for regressions.** If you changed `keys.py`, re-run ALL scenarios (not just the one you fixed) to make sure the change didn't break others.

### Convergence Criteria

A scenario is "verified" when:

- It passes against the real server **3 times in a row** without changes between runs.
- The assertions actually test the intended behavior (not just "didn't crash").
- The test report documents exactly what the scenario validates.

If a scenario doesn't converge after 5 iterations, document the remaining issue in `ISSUES.md` and move on. It may require changes to the Remora plugin or LSP server, not just the test infrastructure.

---

## 12. Cast File Reference

### Format: Asciicast v2 (JSONL)

```
Line 1: {"version": 2, "width": 120, "height": 35, "timestamp": 1772556814, "env": {...}}
Line 2: [0.0382, "o", "\x1b[H\x1b[2J...frame content..."]
Line 3: [0.3025, "o", "\x1b[H\x1b[2J...frame content..."]
...
```

- **Line 1** is the header (JSON object, not array).
- **Subsequent lines** are frames: `[elapsed_seconds, event_type, data]`.
- `event_type` is always `"o"` (output) in our recorder.
- `data` starts with `\x1b[H\x1b[2J` (cursor home + erase screen) -- this is the full-screen redraw prefix injected by AsciinemaRecorder.
- Content after the prefix is the raw tmux `capture-pane -e` output with ANSI colors.
- Lines in the content are separated by `\r\n`.

### Parsing Tips

```python
import json

# Read all frames
with open("e2e/output/startup_20260303_143012.cast") as f:
    header = json.loads(next(f))
    frames = [json.loads(line) for line in f]

# Get the last frame (final screen state)
last_ts, _, last_data = frames[-1]
print(f"Final frame at {last_ts:.1f}s")

# Strip ANSI + screen reset to get plain text
import re
plain = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', last_data)
plain = plain.replace('\x1b[H\x1b[2J', '')
lines = plain.split('\r\n')
for i, line in enumerate(lines):
    print(f"{i+1:3d}| {line}")
```

### Timing Analysis

```python
# Find when "[Remora]" first appeared
for ts, _, data in frames:
    if "[Remora]" in data:
        print(f"[Remora] appeared at {ts:.1f}s")
        break

# Find frame rate
if len(frames) > 1:
    intervals = [frames[i][0] - frames[i-1][0] for i in range(1, len(frames))]
    print(f"Avg frame interval: {sum(intervals)/len(intervals):.3f}s")
```

---

## 13. Checklist

Quick-reference for each verification pass. Copy this into your project notes and check off as you go.

### Pre-Run

- [ ] vLLM server reachable (`curl http://remora-server:8000/v1/models`)
- [ ] No stale tmux sessions (`tmux ls`)
- [ ] Harness tests pass (`devenv shell -- python -m pytest tests/test_e2e_harness.py -q`)
- [ ] Smoke scenario passes (`devenv shell -- python -m e2e.run -s smoke`)

### Per Scenario

- [ ] Write pre-test expectations (what you expect to see)
- [ ] Run the scenario (`devenv shell -- python -m e2e.run -s <name>`)
- [ ] Note PASS/FAIL and duration
- [ ] Read the .cast file -- extract key frames and timestamps
- [ ] Write post-test observations (what actually happened)
- [ ] Identify changes needed
- [ ] Apply fixes to scenario / keys.py
- [ ] Re-run and verify fix
- [ ] Check for regressions on other scenarios

### Post-Cycle

- [ ] All three scenarios pass against real server
- [ ] Test reports complete for all scenarios
- [ ] keys.py has new helpers (if any were identified)
- [ ] Scenarios use the new helpers
- [ ] PROGRESS.md updated
- [ ] CONTEXT.md updated with final state
