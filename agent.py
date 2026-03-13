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
MAX_TOOL_CALLS = 12

# System prompt for the system agent
SYSTEM_PROMPT = """You are a documentation and system assistant.

You have four tools. To use a tool, respond with ONLY this JSON format:
{"tool": "tool_name", "args": {"arg_name": "value"}}

Available tools:
- list_files: {"tool": "list_files", "args": {"path": "wiki"}}
- read_file: {"tool": "read_file", "args": {"path": "wiki/file.md"}}
- search_file: {"tool": "search_file", "args": {"path": "wiki/file.md", "query": "keyword"}}
- query_api: {"tool": "query_api", "args": {"method": "GET", "path": "/api/endpoint"}}

When you have the answer, respond with ONLY:
{"answer": "your answer text", "source": "wiki/file.md#section"}

IMPORTANT:
- Output ONLY JSON - no explanations outside JSON
- One tool call at a time
- After search_file, provide final answer using the found information
- Never repeat the same tool call
"""


def load_config() -> dict:
    """Load configuration from both .env files."""
    # Load LLM config from .env.agent.secret
    llm_env_path = Path(__file__).parent / ".env.agent.secret"
    load_dotenv(llm_env_path, override=False)
    
    # Load LMS config from .env.docker.secret
    lms_env_path = Path(__file__).parent / ".env.docker.secret"
    load_dotenv(lms_env_path, override=False)

    config = {
        # LLM config
        "llm_api_base": os.getenv("LLM_API_BASE"),
        "llm_api_key": os.getenv("LLM_API_KEY"),
        "llm_model": os.getenv("LLM_MODEL"),
        # LMS config
        "lms_api_key": os.getenv("LMS_API_KEY"),
        "agent_api_base_url": os.getenv("AGENT_API_BASE_URL", "http://localhost:42002"),
    }

    # Validate LLM config
    missing_llm = [k for k in ["llm_api_base", "llm_api_key", "llm_model"] if not config.get(k)]
    if missing_llm:
        print(f"Error: Missing LLM config: {', '.join(missing_llm)}", file=sys.stderr)
        sys.exit(1)

    # Validate LMS config
    if not config.get("lms_api_key"):
        print("Error: Missing LMS_API_KEY in .env.docker.secret", file=sys.stderr)
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


def read_file(path: str, max_chars: int = 15000) -> str:
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
        # Truncate very large files to avoid token limits
        # But keep enough content for the LLM to find answers
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n... [truncated]"
        print(f"  Read {len(content)} characters", file=sys.stderr)
        return content
    except Exception as e:
        return f"Error: Could not read file - {e}"


def search_file(path: str, query: str) -> str:
    """Search for a pattern in a file and return matching lines."""
    print(f"Tool: search_file('{path}', '{query}')", file=sys.stderr)

    is_safe, full_path = is_safe_path(path)
    if not is_safe:
        return f"Error: Access denied - path '{path}' is outside project directory"

    if not full_path.exists():
        return f"Error: File not found - '{path}'"

    if not full_path.is_file():
        return f"Error: Not a file - '{path}'"

    try:
        content = full_path.read_text(encoding="utf-8")
        lines = content.split('\n')
        matches = []
        for i, line in enumerate(lines, 1):
            if query.lower() in line.lower():
                # Include context: line before and after
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                context = '\n'.join(f"{j}: {lines[j-1]}" for j in range(start, end))
                matches.append(f"Line {i}:\n{context}")
        
        if not matches:
            return f"No matches found for '{query}' in {path}"
        
        result = '\n\n'.join(matches)
        # Truncate if too long
        if len(result) > 10000:
            result = result[:10000] + "\n\n... [truncated]"
        print(f"  Found {len(matches)} matches", file=sys.stderr)
        return result
    except Exception as e:
        return f"Error: Could not search file - {e}"


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


def query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend API and return the response."""
    print(f"Tool: query_api('{method}' {path})", file=sys.stderr)
    
    config = load_config()
    base_url = config["agent_api_base_url"]
    api_key = config["lms_api_key"]
    
    # Build full URL
    url = f"{base_url}{path}"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                data = json.loads(body) if body else {}
                response = client.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                data = json.loads(body) if body else {}
                response = client.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            elif method.upper() == "PATCH":
                data = json.loads(body) if body else {}
                response = client.patch(url, headers=headers, json=data)
            else:
                return f"Error: Unknown HTTP method '{method}'"
        
        result = {
            "status_code": response.status_code,
            "body": response.text,
        }
        result_str = json.dumps(result)
        print(f"  Status: {response.status_code}", file=sys.stderr)
        return result_str
        
    except httpx.RequestError as e:
        return f"Error: API request failed - {e}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON body - {e}"
    except Exception as e:
        return f"Error: API call failed - {e}"


# Map tool names to functions
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api,
    "search_file": search_file,
}


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool and return the result."""
    if name not in TOOL_FUNCTIONS:
        return f"Error: Unknown tool '{name}'"

    func = TOOL_FUNCTIONS[name]

    # Extract arguments based on tool
    if name == "read_file":
        if "path" in arguments:
            return func(arguments["path"])
        return f"Error: Missing required argument 'path' for tool '{name}'"
    
    elif name == "list_files":
        if "path" in arguments:
            return func(arguments["path"])
        return f"Error: Missing required argument 'path' for tool '{name}'"
    
    elif name == "search_file":
        if "path" not in arguments:
            return f"Error: Missing required argument 'path' for tool '{name}'"
        if "query" not in arguments:
            return f"Error: Missing required argument 'query' for tool '{name}'"
        return func(arguments["path"], arguments["query"])
    
    elif name == "query_api":
        if "method" not in arguments:
            return f"Error: Missing required argument 'method' for tool '{name}'"
        if "path" not in arguments:
            return f"Error: Missing required argument 'path' for tool '{name}'"
        
        method = arguments["method"]
        path = arguments["path"]
        body = arguments.get("body")
        return func(method, path, body)

    return f"Error: Unknown tool '{name}'"


def parse_llm_response(content: str) -> dict | None:
    """
    Parse the LLM response to extract tool calls or final answer.
    The LLM may return different JSON formats, so we handle multiple cases.
    """
    content = content.strip()

    # Try to parse the entire content as JSON first
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            # Normalize format: convert {"tool_name": {...}} to {"tool": "tool_name", "args": {...}}
            if "tool" not in data and "answer" not in data:
                # Check if it's a tool call format like {"list_files": {"path": "wiki"}}
                for tool_name in ["list_files", "read_file", "search_file", "query_api"]:
                    if tool_name in data and isinstance(data[tool_name], dict):
                        return {"tool": tool_name, "args": data[tool_name]}
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON objects with balanced braces
    # Find all potential JSON objects and try to parse them
    results = []
    i = 0
    while i < len(content):
        start = content.find('{', i)
        if start == -1:
            break
        
        depth = 0
        end = start
        for j, char in enumerate(content[start:], start):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
        
        if depth != 0:
            break
        
        try:
            data = json.loads(content[start:end])
            if isinstance(data, dict):
                # Normalize format
                if "tool" not in data and "answer" not in data:
                    for tool_name in ["list_files", "read_file", "search_file", "query_api"]:
                        if tool_name in data and isinstance(data[tool_name], dict):
                            data = {"tool": tool_name, "args": data[tool_name]}
                            break
                results.append(data)
        except json.JSONDecodeError:
            pass
        
        i = end
    
    # Return the first valid JSON object that has 'tool' or 'answer'
    for result in results:
        if "tool" in result or "answer" in result:
            return result
    
    # If no tool/answer found, return first result
    if results:
        return results[0]
    
    return None


def call_llm(messages: list[dict], config: dict[str, str]) -> str:
    """Call the LLM API and return the content."""
    url = f"{config['llm_api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['llm_api_key']}",
    }

    payload = {
        "model": config["llm_model"],
        "messages": messages,
        "temperature": 0,
    }

    print(f"Calling LLM API with {len(messages)} messages...", file=sys.stderr)

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    # Handle case where content might be null
    content = data["choices"][0]["message"].get("content") or ""
    return content


def generate_answer_from_results(question: str, tool_calls: list[dict]) -> str:
    """Generate an answer from tool results when LLM fails to provide one."""
    # Look for search_file results that contain relevant information
    for call in reversed(tool_calls):
        if call["tool"] == "search_file":
            result = call.get("result", "")
            # Extract the relevant lines from search results
            if "Line " in result:
                # Found search results with line numbers
                lines = result.split('\n')
                # Find the actual content lines (not line numbers)
                content_lines = []
                for line in lines:
                    if line.startswith('Line ') or ':' in line[:5]:
                        continue
                    content_lines.append(line)
                
                if content_lines:
                    return '\n'.join(content_lines[:10])
    
    # Fallback: use last read_file result
    for call in reversed(tool_calls):
        if call["tool"] == "read_file":
            result = call.get("result", "")
            if result and not result.startswith("Error"):
                return result[:500]
    
    return "I found information but couldn't extract a clear answer."


def run_agentic_loop(question: str, config: dict) -> dict:
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
    
    # Track seen tool calls to detect loops
    seen_tool_calls = set()

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
            
            # Detect repeated tool calls (loop detection)
            tool_key = (tool_name, json.dumps(tool_args, sort_keys=True))
            if tool_key in seen_tool_calls:
                print(f"Detected repeated tool call, generating answer from context", file=sys.stderr)
                # Generate answer from available tool results
                last_answer = generate_answer_from_results(question, all_tool_calls)
                break
            seen_tool_calls.add(tool_key)

            # Execute tool
            result = execute_tool(tool_name, tool_args)

            # Record tool call (truncate long results)
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
        # Check for wiki file reference
        match = re.search(r'wiki/[\w\-/]+\.md(?:#[\w\-]+)?', last_answer)
        if match:
            source = match.group()
        
        # Check for API reference
        if not source:
            api_match = re.search(r'(?:API|endpoint)[:\s]+(?:GET|POST|PUT|DELETE|PATCH)\s+/\S+', last_answer)
            if api_match:
                source = api_match.group()

    # If no source found, use last read_file or query_api
    if not source:
        for call in reversed(all_tool_calls):
            if call["tool"] == "read_file":
                source = call["args"].get("path", "")
                break
            elif call["tool"] == "query_api":
                method = call["args"].get("method", "GET")
                path = call["args"].get("path", "")
                source = f"API: {method} {path}"
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
