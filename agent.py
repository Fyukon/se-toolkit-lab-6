#!/usr/bin/env python3
"""
Agent CLI - calls an LLM and returns a structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
    All debug output goes to stderr.
"""

import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


def load_config() -> dict[str, str]:
    """Load configuration from .env.agent.secret."""
    env_path = Path(__file__).parent / ".env.agent.secret"
    load_dotenv(env_path)

    import os

    config = {
        "api_base": os.getenv("LLM_API_BASE"),
        "api_key": os.getenv("LLM_API_KEY"),
        "model": os.getenv("LLM_MODEL"),
    }

    # Validate config
    missing = [k for k, v in config.items() if not v]
    if missing:
        print(f"Error: Missing config: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    return config


def call_lllm(question: str, config: dict[str, str]) -> str:
    """Call the LLM API and return the answer."""
    print(f"Calling LLM with model: {config['model']}", file=sys.stderr)

    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    }
    payload = {
        "model": config["model"],
        "messages": [{"role": "user", "content": question}],
        "temperature": 0,
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    answer = data["choices"][0]["message"]["content"]
    print(f"LLM response received", file=sys.stderr)
    return answer


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    config = load_config()

    answer = call_lllm(question, config)

    # Output JSON to stdout
    result = {"answer": answer, "tool_calls": []}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
