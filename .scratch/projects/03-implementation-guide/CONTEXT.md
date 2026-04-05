# Implementation Guide — Context

## Project

Obsidian Ops — local-first, agent-driven operations overlay for an Obsidian vault.

## Purpose

Create a detailed implementation guide for building the obsidian-ops library from the refined concept, spec, and architecture documents.

## Source Documents

- `02-documentation-rewrite/CONCEPT.md` — product vision, mental model, known limitations
- `02-documentation-rewrite/SPEC.md` — requirements, API spec, performance targets, functional requirements
- `02-documentation-rewrite/ARCHITECTURE.md` — system structure, component boundaries, ADRs, data flows
- `01-obsidian-ops-concept/CONCEPT_REVIEW.md` — review findings, risks, recommendations

## Current State

- Project scaffold exists in `src/obsidian_ops/` (all 12 modules created from earlier concept docs)
- Tests not yet written
- Implementation may need revision to align with refined docs (e.g., async subprocess calls, localhost binding, content size guards)

## What's Next

- Create the implementation guide (GUIDE.md)
