# Hypothesis Report Template

## Run Metadata
- Date:
- Run directory:
- E2E scenario + command:
- Recording command + cast file:
- Input logs (absolute paths):
- Commit baseline:

## Observed Symptoms
- Symptom 1:
- Symptom 2:
- Symptom 3:

## Error Signatures (Exact)
- Signature:
  - Source log:
  - Timestamp(s):
  - Origin in code (file + function, and line if known):
  - Why this matters:

## Cast Evidence
- Snippet timestamp:
  - Cast file:
  - What was visible in UI:
  - Why this supports (or rejects) the hypothesis:

## Stage Counters
- `on_input_submitted`:
- `HumanChatEvent emitted`:
- `execute_turn: START`:
- `execute_turn: ... calling LLM`:
- `append: database locked`:
- `batch_append: database locked`:

## Code Areas to Inspect Next
- File:
  - Function(s):
  - Reason:

## Primary Hypothesis
State one causal hypothesis only.

## Recommended Fix
Describe one minimal code change to test the hypothesis.

## Why This Fix
Explain why this fix should affect the observed failure path.

## Falsification Criteria
List exact outcomes that reject this hypothesis.

## Verification Plan
1. Command(s) to run:
2. Expected markers in logs:
3. Pass/fail conditions:
4. If failed, first files/lines to inspect:

## Notes
Include follow-up ideas only if the primary hypothesis is falsified.
