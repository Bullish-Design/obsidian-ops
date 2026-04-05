# Kiln Overview - Assumptions

## Context
This project documents the research and analysis of the Kiln static site generator for developers working on the bullish-ssg library.

## Assumptions

### About Kiln
- Kiln is a Go-based static site generator specifically designed for Obsidian vaults
- It provides 1:1 feature parity with Obsidian
- It's distributed as a single binary with no dependencies
- It supports two modes: Default (vault mirror) and Custom (headless CMS)

### About the Audience
- Developers working on bullish-ssg
- Need to understand how Kiln works to integrate with it
- May not be familiar with Go or static site generators
- Need practical integration guidance

### Scope
- Document Kiln's core functionality
- Explain how bullish-ssg integrates with Kiln
- Provide command references
- Explain configuration options

## Out of Scope
- Contributing to Kiln
- Modifying Kiln source code
- Advanced custom mode templating
- Performance tuning Kiln itself
