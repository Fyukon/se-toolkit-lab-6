#!/usr/bin/env python3
"""
Agent CLI - calls an LLM with tools and returns a structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    All debug output goes to stderr.
"""

import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Maximum tool calls per question
MAX_TOOL_CALLS = 10

# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation assistant with access to the project wiki files.

You have two tools available. To use them, respond with JSON in this exact format:

To list files:
{"tool": "list_files", "args": {"path": "wiki"}}

To read a file:
{"tool": "read_file", "args": {"path": "wiki/filename.md"}}

When you have found the answer, respond with:
{"answer": "your answer here", "source": "wiki/filename.md#section"}

Rules:
1. Use list_files to explore directories
2. Use read_file to read specific files
3. Always cite your source (file path with optional #section)
4. Only answer questions about the project documentation
5. If you don't know, say so

Think step by step. Start by exploring the wiki structure if needed.
"""


def load_config() -> dict[str, str]:
    """Load configuration from .env.agent.secret."""
    env_path = Path(__file__).parent / ".env.agent.secret"
    load_dotenv(env_path)

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


def is_safe_path(requested_path: str) -> tuple[bool, Path]:
    """
    Check if the requested path is safe (within project root).
    Returns (is_safe, resolved_path).
    """
    project_root = Path(__file__).parent.resolve()
    
    # Reject absolute paths
    if Path(requested_path).is_absolute():
        return False, Path("")
    
    # Reject paths with ..
    if ".." in requested_path:
        return False, Path("")
    
    # Resolve the full path
    full_path = (project_root / requested_path).resolve()
    
    # Check if resolved path is within project root
    if not str(full_path).startswith(str(project_root)):
        return False, Path("")
    
    return True, full_path


def read_file(path: str) -> str:
    """Read a file from the project repository."""
    print(f"Tool: read_file('{path}')", file=sys.stderr)
    
    is_safe, full_path = is_safe_path(path)
    if not is_safe:
        return f"Error: Access denied - path '{path}' is outside project directory"
    
    if not full_path.exists():
        return f"Error: File not found - '{path}'"
    
    if not full_path.is_file():
        return f"Error: Not a file - '{path}'"
    
    try:
        content = full_path.read_text(encoding="utf-8")
        print(f"  Read {len(content)} characters", file=sys.stderr)
        return content
    except Exception as e:
        return f"Error: Could not read file - {e}"


def list_files(path: str) -> str:
    """List files and directories at a given path."""
    print(f"Tool: list_files('{path}')", file=sys.stderr)
    
    is_safe, full_path = is_safe_path(path)
    if not is_safe:
        return f"Error: Access denied - path '{path}' is outside project directory"
    
    if not full_path.exists():
        return f"Error: Directory not found - '{path}'"
    
    if not full_path.is_dir():
        return f"Error: Not a directory - '{path}'"
    
    try:
        entries = sorted([e.name for e in full_path.iterdir()])
        result = "\n".join(entries)
        print(f"  Listed {len(entries)} entries", file=sys.stderr)
        return result
    except Exception as e:
        return f"Error: Could not list directory - {e}"


# Map tool names to functions
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
}


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool and return the result."""
    if name not in TOOL_FUNCTIONS:
        return f"Error: Unknown tool '{name}'"
    
    func = TOOL_FUNCTIONS[name]
    
    # Extract arguments
    if "path" in arguments:
        return func(arguments["path"])
    
    return f"Error: Missing required arguments for tool '{name}'"


def parse_llm_response(content: str) -> dict | None:
    """
    Parse the LLM response to extract tool calls or final answer.
    Looks for JSON objects in the response.
    """
    content = content.strip()
    
    # Try to parse the entire content as JSON first
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON object with balanced braces
    # Start from the first { and find matching }
    start = content.find('{')
    if start == -1:
        return None
    
    depth = 0
    end = start
    for i, char in enumerate(content[start:], start):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    
    if depth != 0:
        return None
    
    try:
        data = json.loads(content[start:end])
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return None
    
    return None


def call_llm(messages: list[dict], config: dict[str, str]) -> str:
    """Call the LLM API and return the content."""
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    }
    
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0,
    }
    
    print(f"Calling LLM API with {len(messages)} messages...", file=sys.stderr)
    
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    
    content = data["choices"][0]["message"]["content"]
    return content


def run_agentic_loop(question: str, config: dict[str, str]) -> dict:
    """
    Run the agentic loop:
    1. Send question to LLM
    2. Parse response for tool calls or final answer
    3. If tool call, execute and append result, continue
    4. If final answer, return it
    """
    # Initialize conversation history
    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    
    # Track all tool calls for output
    all_tool_calls = []
    last_answer = None
    
    for iteration in range(MAX_TOOL_CALLS):
        print(f"\n=== Iteration {iteration + 1} ===", file=sys.stderr)
        
        # Call LLM
        content = call_llm(conversation, config)
        print(f"LLM response: {content[:200]}...", file=sys.stderr)
        
        # Parse response
        parsed = parse_llm_response(content)
        
        if not parsed:
            # No JSON found - treat as final answer
            print(f"Final answer received", file=sys.stderr)
            last_answer = content
            break
        
        # Check if it's a tool call
        has_tool = "tool" in parsed
        has_args = "args" in parsed
        has_result = "result" in parsed
        
        if has_tool and has_args and not has_result:
            tool_name = parsed["tool"]
            tool_args = parsed["args"]
            
            print(f"Tool call: {tool_name}({tool_args})", file=sys.stderr)
            
            # Execute tool
            result = execute_tool(tool_name, tool_args)
            
            # Record tool call
            all_tool_calls.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result[:500] if len(result) > 500 else result,
            })
            
            # Add assistant's tool call to conversation
            conversation.append({
                "role": "assistant",
                "content": json.dumps({"tool": tool_name, "args": tool_args}),
            })
            
            # Add tool result as user message
            result_preview = result[:300] + "..." if len(result) > 300 else result
            conversation.append({
                "role": "user",
                "content": f"Tool output from {tool_name}:\n{result_preview}",
            })
            
            # Continue loop
            continue
        
        # Check if it's a final answer
        if "answer" in parsed:
            print(f"Final answer received", file=sys.stderr)
            last_answer = parsed.get("answer", content)
            source = parsed.get("source", "")
            
            # Add to conversation
            conversation.append({
                "role": "assistant",
                "content": content,
            })
            
            return {
                "answer": last_answer,
                "source": source,
                "tool_calls": all_tool_calls,
            }
    
    # Max iterations or no tool call - return what we have
    print(f"\nLoop ended", file=sys.stderr)
    
    # Extract source if possible
    source = ""
    if last_answer:
        match = re.search(r'wiki/[\w\-/]+\.md(?:#[\w\-]+)?', last_answer)
        if match:
            source = match.group()
    
    # If no source found, use last read_file
    if not source:
        for call in reversed(all_tool_calls):
            if call["tool"] == "read_file":
                source = call["args"].get("path", "")
                break
    
    return {
        "answer": last_answer or "I couldn't find enough information to answer your question.",
        "source": source,
        "tool_calls": all_tool_calls,
    }


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)
    
    question = sys.argv[1]
    config = load_config()
    
    result = run_agentic_loop(question, config)
    
    # Output JSON to stdout
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
