#!/usr/bin/env python3
"""
TriageIQ Claude Agent
----------------------
A terminal chat interface powered by Claude Fable 5.1 (or any Anthropic model)
with read/write access to the TriageIQ workspace.

Usage:
    poetry run python claude_agent/chat.py

Commands during chat:
    /exit  or  /quit  — end the session
    /clear             — clear conversation history
    /model             — show current model
    /help              — show this list
"""

import json
import os
import sys
from pathlib import Path

# ── Load .env from workspace root ─────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import anthropic

# ── Import agent modules ───────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from config import MODEL_ID, MAX_TOKENS, THINKING_BUDGET, SYSTEM_PROMPT, WORKSPACE_ROOT
from tools import TOOL_DEFINITIONS, dispatch_tool


# ── ANSI colour helpers ────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
CYAN    = "\033[36m"
YELLOW  = "\033[33m"
GREEN   = "\033[32m"
MAGENTA = "\033[35m"
DIM     = "\033[2m"
RED     = "\033[31m"


def c(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}"


# ── Tool-call handler ─────────────────────────────────────────────────────────

def handle_tool_calls(response_content: list) -> tuple[list, list]:
    """
    Process tool_use blocks from a Claude response.
    Returns (tool_result_message, text_blocks_to_print).
    """
    tool_results = []
    texts = []

    for block in response_content:
        if block.type == "text":
            texts.append(block.text)
        elif block.type == "thinking":
            # Print thinking in dim style so user can see reasoning
            print(c("\n[thinking]\n", DIM) + c(block.thinking, DIM) + "\n")
        elif block.type == "tool_use":
            tool_name = block.name
            tool_input = block.input
            tool_id = block.id

            print(
                c(f"\n  ⚙  Tool: ", YELLOW) +
                c(tool_name, BOLD) +
                c(f"({json.dumps(tool_input, ensure_ascii=False)})", DIM)
            )

            result = dispatch_tool(tool_name, tool_input)
            # Truncate very long results for display, but send full result to API
            display = result if len(result) < 2000 else result[:2000] + f"\n… ({len(result)-2000} more chars)"
            print(c("  →  ", GREEN) + display.replace("\n", "\n     "))

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result,
            })

    return tool_results, texts


# ── Main REPL ─────────────────────────────────────────────────────────────────

def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(c("ERROR: ANTHROPIC_API_KEY not set.", RED))
        print(f"Add it to: {WORKSPACE_ROOT / '.env'}")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    conversation: list[dict] = []

    print(c("━" * 60, CYAN))
    print(c("  TriageIQ Claude Agent", BOLD))
    print(c(f"  Model  : {MODEL_ID}", CYAN))
    print(c(f"  Root   : {WORKSPACE_ROOT}", DIM))
    print(c("  Type /help for commands. Ctrl-C or /exit to quit.", DIM))
    print(c("━" * 60, CYAN))
    print()

    # Fable 5.1+ uses adaptive thinking + output_config.effort
    # (older models used thinking.type="enabled" + budget_tokens — no longer valid)
    use_thinking = THINKING_BUDGET > 0

    while True:
        try:
            user_input = input(c("You › ", BOLD + CYAN)).strip()
        except (KeyboardInterrupt, EOFError):
            print(c("\n\nGoodbye!", CYAN))
            break

        if not user_input:
            continue

        # ── Slash commands ────────────────────────────────────────────────────
        if user_input.lower() in ("/exit", "/quit"):
            print(c("Goodbye!", CYAN))
            break
        if user_input.lower() == "/clear":
            conversation.clear()
            print(c("  Conversation cleared.", DIM))
            continue
        if user_input.lower() == "/model":
            print(c(f"  Current model: {MODEL_ID}", DIM))
            continue
        if user_input.lower() == "/help":
            print(c(
                "  /exit  /quit — end session\n"
                "  /clear        — wipe history\n"
                "  /model        — show model name\n"
                "  /help         — this message",
                DIM
            ))
            continue

        # ── Add user message ──────────────────────────────────────────────────
        conversation.append({"role": "user", "content": user_input})

        # ── Agentic loop — keep going while Claude calls tools ────────────────
        print()
        while True:
            kwargs = dict(
                model=MODEL_ID,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=conversation,
            )
            if use_thinking:
                # Fable 5.1 adaptive thinking API
                kwargs["thinking"] = {"type": "adaptive"}
                kwargs["output_config"] = {"effort": "high"}

            try:
                response = client.messages.create(**kwargs)
            except anthropic.APIError as e:
                print(c(f"\nAPI Error: {e}", RED))
                break

            tool_results, text_blocks = handle_tool_calls(response.content)

            # Print Claude's text reply
            if text_blocks:
                print(c("Claude › ", BOLD + MAGENTA))
                for txt in text_blocks:
                    print(txt)
                print()

            # If Claude wants to use tools, feed results back and continue
            if response.stop_reason == "tool_use":
                conversation.append({"role": "assistant", "content": response.content})
                conversation.append({"role": "user", "content": tool_results})
                continue

            # Stop reason is "end_turn" — done
            if text_blocks:
                conversation.append({"role": "assistant", "content": response.content})
            break


if __name__ == "__main__":
    main()
