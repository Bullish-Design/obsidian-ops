---
name: lsp-chat-recovery-loop
description: "Run a repeatable Remora LSP chat-delivery recovery loop: simplify the latest server/client logs, investigate pipeline failures, write a hypothesis report with recommended fix and rationale, implement a minimal fix, commit it, and hand off verification steps. Use when debugging chat-delivery regressions, lock-contention storms, missing HumanChatEvent/execute_turn stages, or similar LSP runtime reliability issues."
---

# Lsp Chat Recovery Loop

## Workflow

1. Select and run the best existing e2e scenario for the target behavior.
2. Create a new run directory in `.scratch/projects/lsp-chat-delivery-recovery/runs/`.
3. Simplify latest logs into that run directory.
4. Quantify pipeline stages and failure signatures.
5. If markers are missing, run with recording and analyze the `.cast`.
6. Write a detailed hypothesis report and next-step plan.
7. Implement one minimal, falsifiable fix.
8. Validate with focused checks and rerun relevant e2e.
9. Commit with a precise message.
10. Provide exact user verification steps.

## Step 0: Choose and Run E2E Scenario

Before log analysis, run an e2e scenario that exercises the desired behavior.

### Scenario selection rules
- Prefer existing scenarios in `e2e/scenarios/`.
- For chat-delivery issues, default to `chat`.
- For panel-only issues, default to `panel_nav`.
- For startup/attach issues, default to `startup`.
- `startup` can false-pass on UI/init notifications without proving an attached remora client; always pair startup investigations with the `nv2 --headless` attach probe below.
- If no existing scenario exercises the failure path, create one new scenario and register it in `e2e/scenarios/__init__.py`.

### Required artifact
Create `E2E_SELECTION.md` in the run directory with:
- selected scenario
- why it matches the bug
- command run
- whether a new scenario was needed (and why)

Run command (example):

```bash
devenv shell -- python -m e2e.run --scenario chat --no-record
```

### Mandatory post-e2e validation
After the run, verify the scenario actually exercised the target path using logs (not just PASS/FAIL).

For chat-delivery investigations, require:
- client log contains `CMD RemoraChat`
- server log contains `cmd_chat: requestInput sent`
- server log contains `on_input_submitted: params=`
- server log contains `execute_turn: START`

If these markers are missing, treat the scenario as non-validating and either:
1. adjust scenario usage (timing/focus), or
2. create a new scenario that deterministically exercises submit path.

For startup/attach investigations, do not rely on `startup` scenario PASS alone.
Require a direct headless client-attach probe:

```bash
devenv shell -- nv2 --headless remora_demo/companion/demo/harness.py \
  "+lua vim.defer_fn(function() local clients=vim.lsp.get_clients({name='remora'}); print('REMORA_CLIENTS=' .. tostring(#clients)); vim.cmd('qa!') end, 10000)"
```

Treat `REMORA_CLIENTS=0` as a startup failure even if `e2e.run --scenario startup` reports PASS.

Then run the same scenario with recording enabled and inspect the newest `.cast`:

```bash
devenv shell -- python -m e2e.run --scenario chat
```

Capture in `CAST_ANALYSIS.md`:
- cast file path
- whether `Message to agent:` appears
- whether typed message text appears in prompt/history
- whether key-sequence artifacts (e.g., stray `ra`) appear
- timestamped snippets that align with missing server markers

## Step 1: Create Run Directory

Create a timestamped run folder:

```bash
mkdir -p .scratch/projects/lsp-chat-delivery-recovery/runs/<YYYY-MM-DD-step-XX-short-name>/simplified-logs
```

Keep all outputs for this loop in that folder:
- `E2E_SELECTION.md`
- `CAST_ANALYSIS.md` (required when marker validation fails)
- `NEXT_STEP_PLAN.md` (optional if already maintained elsewhere)
- `HYPOTHESIS_REPORT.md`
- simplified logs
- summary/counter artifacts

## Step 2: Simplify Latest Logs

Use the bundled helper script:

```bash
devenv shell -- python .scratch/skills/lsp-chat-recovery-loop/scripts/simplify_last_run_logs.py \
  --output-dir .scratch/projects/lsp-chat-delivery-recovery/runs/<run>/simplified-logs
```

Defaults:
- Read from `/home/andrew/Documents/Projects/remora/.remora/logs`
- Select latest `server-*.log` and latest `client-*.log`
- Drop repetitive `NodeDiscoveredEvent` noise triplets
- Write `simplify_summary.json`

If needed, include more recent logs:

```bash
devenv shell -- python .scratch/skills/lsp-chat-recovery-loop/scripts/simplify_last_run_logs.py \
  --count 3 \
  --output-dir .scratch/projects/lsp-chat-delivery-recovery/runs/<run>/simplified-logs
```

## Step 3: Investigate and Quantify

In simplified server logs, collect at least:
- `on_input_submitted`
- `HumanChatEvent emitted`
- `execute_turn: START`
- `execute_turn: ... calling LLM`
- `append: database locked`
- `batch_append: database locked`

Use `rg -n` and record counts in the hypothesis report. Prefer stage-by-stage chain analysis over single-error analysis.

Also record the exact source of each signature:
- log file path + timestamp
- code origin (`file + function`, include line when available)

## Step 4: Write Hypothesis Report + Next Step Plan

Create `HYPOTHESIS_REPORT.md` and `NEXT_STEP_PLAN.md` in the run directory. Use:
- `references/hypothesis-report-template.md`
- `references/next-step-plan-template.md`

Rules:
- State one primary hypothesis.
- Recommend one minimal fix for that hypothesis.
- Include falsification criteria.
- Explicitly state what outcome would disprove the fix.
- Include exact code areas to inspect (absolute paths + function names).
- Include concrete error signatures with origin (`file.py:line` from logs/code when available).
- Include reproduction command(s) and expected markers so a brand-new session can continue immediately.

## Step 5: Implement Minimal Fix

Guardrails:
- Change one causal lever at a time.
- Do not combine startup/race tweaks with contention fixes in one experiment.
- Prefer structural contention ownership fixes over retry-value retuning.

Make the code change directly, then run focused checks relevant to touched code.

## Step 6: Validate and Commit

Run targeted verification commands. Keep output concise and tied to the hypothesis.

Commit non-interactively:

```bash
git add <changed-files>
git commit -m "<scope>: <what changed> for <hypothesis>"
```

## Step 7: Handoff to User

Provide:
1. What was changed and why.
2. Commit hash.
3. Exact commands for the user to run to verify behavior.
4. Expected log evidence after verification (specific markers and counts).

Do not end with vague guidance; provide concrete, copy-pasteable commands.

## Resources

- `scripts/simplify_last_run_logs.py`: simplify newest logs with default noise filters.
- `references/hypothesis-report-template.md`: required report structure.
- `references/next-step-plan-template.md`: required next-step plan structure.
