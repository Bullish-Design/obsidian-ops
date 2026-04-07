# CONCEPT + SPEC Review

## 1. Scope and Method

This review re-evaluates:
- `CONCEPT.md`
- `SPEC.md`

Focus areas:
- Internal consistency (concept vs spec)
- Implementability without hidden design decisions
- Safety and correctness risks
- Testability and acceptance clarity

---

## 2. Executive Summary

The architecture direction is solid: a library-first vault operations core with strict sandboxing, explicit non-goals, and optional HTTP transport is the right separation.

Main risk is not the architecture itself, but unresolved contract details that will cause rework if coding starts before alignment. The most important issues are:

1. Frontmatter update semantics are contradictory between sections.
2. Frontmatter preservation expectations are stronger in concept than in spec and likely not achievable with `pyyaml` alone.
3. Several boundary behaviors are under-specified (heading/block edge cases, append/newline behavior, list/search glob semantics).
4. Path sandboxing is directionally correct but has TOCTOU and platform edge cases not explicitly addressed.

Recommended status: **Do not implement yet** until the critical contract mismatches below are resolved in the docs.

---

## 3. What Is Strong

1. Clear product boundary and one-way dependency from agent layer to ops layer (`CONCEPT.md:L39-L50`).
2. Correctly scoped non-goals to prevent scope creep (`CONCEPT.md:L67-L75`, `CONCEPT.md:L284-L294`).
3. Good phased implementation order in spec (`SPEC.md:L923-L949`).
4. Explicit exception hierarchy and lock behavior are concrete and testable (`SPEC.md:L414-L437`, `SPEC.md:L625-L659`).
5. VCS behavior is sufficiently explicit for v1 (`SPEC.md:L602-L622`).

---

## 4. Critical Issues (Resolve Before Implementation)

## 4.1 Frontmatter update contract is internally inconsistent

Evidence:
- Concept says targeted updates include nested paths (`CONCEPT.md:L59`).
- Spec API text says `update_frontmatter` supports dot notation / nested dicts (`SPEC.md:L196-L197`).
- Spec merge semantics later says shallow top-level merge only, nested structures replaced (`SPEC.md:L526-L537`).

Why this matters:
- This changes method behavior materially and drives test expectations.
- Implementers may ship incompatible behavior depending on which section they follow.

Recommendation:
- Choose one explicit v1 rule and apply it consistently across concept/spec/tests.
- If shallow merge is intended, remove all nested-path wording and examples that imply deep path patching.
- If nested patching is intended, define exact algorithm (dot paths, dict merge precedence, list handling, deletion semantics).

---

## 4.2 Frontmatter preservation promise is over-committed vs implementation choices

Evidence:
- Concept says preserve ordering/comments/formatting preferences (`CONCEPT.md:L250-L256`).
- Spec marks preservation as best-effort and reconstructs YAML from parsed dict (`SPEC.md:L513-L522`).
- Dependencies include only `pyyaml` for core (`CONCEPT.md:L227-L235`, `SPEC.md:L705-L707`).

Why this matters:
- `pyyaml` round-tripping generally cannot preserve comments and often changes style.
- If comments/format preservation are treated as acceptance criteria, the implementation will fail by design.

Recommendation:
- For v1, explicitly downgrade preservation to:
  - preserve body byte-for-byte,
  - preserve data semantics,
  - allow YAML style/comments to change.
- Or change parser strategy to a round-trip-capable YAML library and update dependencies accordingly.

---

## 4.3 “Wikilinks as first-class” is not reflected in API/scope

Evidence:
- Design principles claim wikilinks are first-class (`CONCEPT.md:L37`).
- No wikilink API exists in spec public surface (`SPEC.md:L13-L399`).
- Wikilink graph support is deferred as optional extra (`CONCEPT.md:L80`).

Why this matters:
- This reads as a v1 capability claim but has no implementable surface.

Recommendation:
- Rephrase concept principle to avoid claiming first-class wikilink operations in v1.
- Example: “Obsidian-aware for frontmatter, headings, and block refs; wikilink analysis deferred.”

---

## 4.4 Heading boundary wording is logically inconsistent in one place

Evidence:
- Spec says boundary is next heading of equal or higher level, then parenthetical says “fewer #” (`SPEC.md:L547`).
- “Equal level” is same number of `#`, not fewer.

Why this matters:
- Small wording bug, but it will create parser disagreements and failing tests.

Recommendation:
- Replace with: “next heading with level <= current level.”

---

## 4.5 Lock semantics + internal method composition can self-deadlock (BusyError)

Evidence:
- Non-reentrant try-lock required (`SPEC.md:L629-L632`).
- Multiple high-level methods are lock-owning (`SPEC.md:L636-L653`).

Why this matters:
- If lock-owning methods call other lock-owning methods internally, same-thread `BusyError` occurs.

Recommendation:
- Specify implementation pattern explicitly:
  - public methods acquire lock,
  - internal `_unsafe_*` helpers never acquire lock,
  - no public-to-public calls for mutating methods.

---

## 4.6 Path sandboxing does not fully define race-resistance expectations

Evidence:
- Validation is path-clean + realpath checks (`SPEC.md:L460-L465`, `SPEC.md:L481-L482`).
- No explicit note on TOCTOU between validation and open/write/delete.

Why this matters:
- Symlink swaps after validation can still escape if open semantics are naive.

Recommendation:
- State threat model for v1 explicitly.
- If strong race resistance is required, define safer open strategy (dirfd/openat-style traversal with `O_NOFOLLOW` where available) or explicitly accept residual risk for local trusted use.

---

## 5. Important Ambiguities (Should Resolve Early)

## 5.1 `write_heading` append format is unspecified

Evidence:
- Missing heading appends to file (`SPEC.md:L271`).
- No exact newline policy (leading/trailing blank lines, EOF newline).

Risk:
- Non-deterministic output diffs; brittle tests.

Recommendation:
- Define canonical append formatting.

---

## 5.2 `read_block` / `write_block` boundaries are too narrow for real Obsidian markdown

Evidence:
- Block defined as paragraph/list item up to marker (`SPEC.md:L575-L590`).

Risk:
- Ambiguity for multi-line list items, block quotes, callouts, fenced code blocks, tables.

Recommendation:
- Either define parser constraints strictly for v1 (simple paragraph + single-line list item only), or expand grammar and tests.

---

## 5.3 File search/read size policy is inconsistent

Evidence:
- `read_file` has `MAX_READ_SIZE` (`SPEC.md:L55`, `SPEC.md:L444`).
- `search_files` behavior for large files is unspecified.

Risk:
- Large-file scanning can violate intended memory guardrails.

Recommendation:
- Define whether search skips files over size cap, truncates reads, or has separate `MAX_SEARCH_FILE_SIZE`.

---

## 5.4 `list_files` glob semantics may be too restrictive and partly unclear

Evidence:
- Pattern matches filename only, not relative path (`SPEC.md:L109`).
- API examples imply general glob usage (`CONCEPT.md:L97`, `SPEC.md:L112`).

Risk:
- Cannot target subdirectories (`Projects/*.md`) if filename-only matching is strict.

Recommendation:
- Choose one:
  - full relative-path glob matching, or
  - keep filename-only but rename parameter/docs to make this explicit (`filename_pattern`).

---

## 5.5 HTTP API parameter encoding is awkward for headings/block IDs

Evidence:
- Heading/block identifiers in query string examples (`SPEC.md:L754-L757`).

Risk:
- Requires URL-encoding `##` and complex headings; higher client friction.

Recommendation:
- Use JSON body for these parameters on write/read endpoints where practical.

---

## 5.6 HTTP error mapping for VCS may over-report as 500

Evidence:
- All `VCSError` mapped to HTTP 500 (`SPEC.md:L778`).

Risk:
- Missing binary / non-workspace is often configuration or precondition, not server fault.

Recommendation:
- Split VCSError subtypes or map precondition errors to 400/424 and execution failures to 500.

---

## 5.7 Test command examples conflict with repo execution rules

Evidence:
- Spec uses bare `pytest` (`SPEC.md:L914-L918`).
- Repo rules require running tooling via `devenv shell -- ...`.

Recommendation:
- Update examples to `devenv shell -- pytest ...` for local consistency.

---

## 6. Suggested Spec Edits (Concrete)

1. Frontmatter semantics:
- Remove either shallow-merge section or nested-path claims so only one behavior remains.

2. Preservation contract:
- Replace strong preservation statements with explicit v1 guarantees that are realistically enforceable with chosen dependencies.

3. Heading boundary sentence:
- Change to “next heading with level <= target heading level.”

4. Lock composition:
- Add a short internal implementation rule prohibiting nested lock acquisition.

5. Path safety:
- Add a “Security model” subsection clarifying TOCTOU handling and platform limitations.

6. Content patching constraints:
- Add explicit “supported markdown constructs in v1” and list unsupported forms.

7. HTTP design:
- Move `heading` and `block_id` to JSON bodies or explicitly specify URL encoding requirements.

8. Test execution snippets:
- Replace direct `pytest` examples with `devenv shell -- pytest ...`.

---

## 7. Recommended Pre-Implementation Decision Checklist

Before coding, lock these decisions in docs:

1. `update_frontmatter`: shallow vs deep/dot-path semantics.
2. YAML preservation: best-effort vs strict formatting/comment retention.
3. Markdown parser scope for heading/block operations.
4. Search behavior on large files.
5. Glob matching scope (filename-only vs full relative path).
6. HTTP input shape for heading/block parameters.
7. VCS error taxonomy for HTTP mappings.
8. Sandbox security posture (best-effort local safety vs hardening against adversarial races).

---

## 8. Bottom Line

The architecture is good and implementation-ready **after** contract cleanup. Without these doc fixes, the team will likely incur churn in frontmatter behavior, content patching edge cases, and API expectations.
