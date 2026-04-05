# Next Step Plan Template

## Goal
- One-sentence experiment goal:

## Reproduction Command
- `devenv shell -- python -m e2e.run --scenario <scenario> --no-record`
- `devenv shell -- python -m e2e.run --scenario <scenario>` (recording on)

## Target Files and Functions
- `<absolute path>`
  - function(s):
  - expected change:

## Expected Error/Signal Changes
- Existing signature expected to decrease/disappear:
- New instrumentation markers expected:
- What should appear if hypothesis is wrong:
- Cast/UI change expected (exact prompt/history behavior):

## Minimal Change Set
1. Change:
   - file/function:
   - why this is minimal:
2. Change:
   - file/function:
   - why this is minimal:

## Validation
1. Tests:
2. E2E run:
3. Log checks (`rg` patterns):
4. Cast checks (timestamps/snippets):

## Exit Criteria
- What exact evidence is required to call this step complete.
