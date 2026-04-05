from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import openai

from obsidian_ops.config import Settings
from obsidian_ops.models import SSEEvent
from obsidian_ops.tools import ToolRuntime, get_tool_definitions

BASE_SYSTEM_PROMPT = """You are an assistant that helps manage and improve notes in an Obsidian vault.
You have tools to read, write, list, search, fetch URLs, inspect history, and undo changes.

Rules:
- Preserve YAML frontmatter unless the user asks to change it.
- Preserve wikilinks unless the user asks to change them.
- Do not delete content unless the user clearly intends that outcome.
- Prefer minimal, local edits when possible.
- When creating new files, use sensible markdown structure.
- After making changes, summarize what you did briefly.
"""

NO_FILE_PROMPT = "No specific file is currently selected. The user may be asking about the vault generally."


def build_system_prompt(current_file_path: str | None) -> str:
    if current_file_path:
        return f"{BASE_SYSTEM_PROMPT}\nThe user is currently viewing: {current_file_path}"
    return f"{BASE_SYSTEM_PROMPT}\n{NO_FILE_PROMPT}"


def _summarize_args(arguments: dict) -> str:
    if not arguments:
        return ""
    parts = []
    for key, value in arguments.items():
        rendered = str(value)
        if len(rendered) > 80:
            rendered = rendered[:77] + "..."
        parts.append(f"{key}={rendered!r}")
    return ", ".join(parts)


class Agent:
    def __init__(self, settings: Settings, tool_runtime: ToolRuntime) -> None:
        self._settings = settings
        self._tools = tool_runtime
        self._client = openai.AsyncOpenAI(
            base_url=settings.vllm_base_url,
            api_key=settings.vllm_api_key or "no-key",
        )

    async def run(
        self,
        instruction: str,
        file_path: str | None,
        on_progress: Callable[[SSEEvent], Awaitable[None]],
    ) -> dict:
        self._tools.reset()
        system_prompt = build_system_prompt(file_path)
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instruction},
        ]
        await on_progress(SSEEvent(type="status", message="Agent started"))

        final_text = ""
        hit_iteration_cap = True
        for _ in range(self._settings.max_tool_iterations):
            try:
                response = await self._client.chat.completions.create(
                    model=self._settings.vllm_model,
                    messages=messages,
                    tools=get_tool_definitions(),
                    tool_choice="auto",
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"LLM call failed: {exc}") from exc

            if not response.choices:
                raise RuntimeError("LLM call failed: empty response choices")

            assistant_message = response.choices[0].message
            assistant_payload: dict = {
                "role": "assistant",
                "content": assistant_message.content or "",
            }
            if assistant_message.tool_calls:
                assistant_payload["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                    for tool_call in assistant_message.tool_calls
                ]
            messages.append(assistant_payload)

            if not assistant_message.tool_calls:
                final_text = assistant_message.content or ""
                hit_iteration_cap = False
                break

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                await on_progress(
                    SSEEvent(
                        type="tool",
                        message=f"Calling {tool_name}({_summarize_args(arguments)})",
                    )
                )
                result = await self._tools.call_tool(tool_name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        if hit_iteration_cap:
            limit_note = "Agent hit its iteration limit before completing."
            final_text = f"{final_text}\n{limit_note}".strip() if final_text else limit_note

        result = {
            "summary": final_text,
            "changed_files": self._tools.changed_files,
        }
        await on_progress(SSEEvent(type="result", message=final_text, payload=result))
        return result
