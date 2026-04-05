# Implementation Guide — Assumptions

## Audience

- A developer (or AI agent) implementing obsidian-ops from scratch or revising the existing scaffold

## Guide Scope

- Step-by-step implementation order for all modules
- Reference code for each module aligned with the refined spec and architecture
- Incorporates all critical fixes from the concept review (async subprocess, localhost bind, content size guards)
- Testing strategy and test code
- Manual acceptance checklist

## Technical Assumptions

- Python 3.13+
- FastAPI, Pydantic, httpx, openai SDK, uvicorn
- Jujutsu (`jj`) and Kiln (`kiln`) installed on the system
- vLLM running an OpenAI-compatible endpoint
- Single local user, trusted environment
- Vault already initialized as a Jujutsu workspace
