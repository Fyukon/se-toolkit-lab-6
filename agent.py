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

CRITICAL: Respond with ONLY valid JSON. Use double quotes for all keys and string values.

For tool calls, use this format:
{"tool": "tool_name", "args": {"arg_name": "value"}}

For final answers, use this format:
{"answer": "your answer text", "source": "wiki/file.md#section or API: GET /path or source_file.py"}

AVAILABLE TOOLS:
- list_files(path: str): List files/directories. Use for exploring the repo (e.g., "wiki", "backend/app").
- read_file(path: str): Read file content. Use for reading wiki files, source code, or config files.
- search_file(path: str, query: str): Search for a string in a file. Returns matching lines with context.
- query_api(method: str, path: str, body: str | None = None, auth: bool = True): Call the backend API.
  - method: GET, POST, PUT, DELETE, PATCH
  - path: The endpoint (e.g., "/items/", "/analytics/scores")
  - body: Optional JSON body (string) for POST/PUT/PATCH
  - auth: Whether to send the Authorization header. Set to false to test unauthenticated access.

STRATEGIES:

1. WIKI QUESTIONS:
   - Use list_files("wiki") to find relevant files.
   - Read the file and look for specific sections.
   - Cite the exact section (e.g., wiki/github.md#protect-a-branch).

2. SYSTEM FACTS (framework, ports, request path):
   - Read config files: docker-compose.yml, Dockerfile, Caddyfile, backend/app/main.py.
   - Trace the journey: Browser -> Caddy -> FastAPI (main.py) -> Router -> Database.

3. DATA QUERIES (item count, learners):
   - Use query_api to fetch data from relevant endpoints.
   - If the endpoint returns a list, count the items yourself.
   - Common endpoints: GET /items/, GET /learners/, GET /analytics/scores.

4. BUG DIAGNOSIS:
   - Step 1: Use query_api to reproduce the error.
   - IMPORTANT: If you get a 422 (Validation Error), it means you're missing a required parameter (like ?lab=lab-1). TRY WITH A PARAMETER next!
   - Step 2: Once you see a 500 (Internal Server Error) or other unexpected result, read the relevant source code (e.g., backend/app/routers/analytics.py).
   - Look for:
     - Division by zero: `a / b` where `b` could be 0.
     - Sorting with None: `sorted(items, key=...)` where some keys might be None.
     - Unhandled exceptions or missing checks.
   - Explain the bug and point to the specific line in the source code.

5. COMPONENT COMPARISON:
   - Read source code for both components (e.g., backend/app/etl.py vs backend/app/routers/items.py).
   - Compare their logic (e.g., how they handle failures, idempotency, or validation).

6. HTTP STATUS CODES:
   - To check status codes for unauthenticated requests, use query_api with auth=false.

IMPORTANT:
- Output ONLY valid JSON.
- One tool call at a time.
- If you need to count items, do it based on the API response.
- Be precise and cite your sources.
- DO NOT INCLUDE ANY TEXT BEFORE OR AFTER THE JSON.
"""


def load_config() -> dict:
    """Load configuration from environment variables."""
    # Load from default .env if exists
    load_dotenv()
    
    # Also try to load from specific secret files (local development)
    for env_file in [".env.agent.secret", ".env.docker.secret", ".env.agent", ".env.docker"]:
        env_path = Path(__file__).parent / env_file
        if env_path.exists():
            load_dotenv(env_path, override=False)

    return {
        "llm_api_base": os.getenv("LLM_API_BASE"),
        "llm_api_key": os.getenv("LLM_API_KEY"),
        "llm_model": os.getenv("LLM_MODEL"),
        "lms_api_key": os.getenv("LMS_API_KEY"),
        "agent_api_base_url": os.getenv("AGENT_API_BASE_URL", "http://localhost:42002"),
    }


def is_safe_path(requested_path: str) -> tuple[bool, Path]:
    """Check if the requested path is safe (within project root)."""
    project_root = Path(__file__).parent.resolve()
    if Path(requested_path).is_absolute() or ".." in requested_path:
        return False, Path("")
    full_path = (project_root / requested_path).resolve()
    if not str(full_path).startswith(str(project_root)):
        return False, Path("")
    return True, full_path


def read_file(path: str, max_chars: int = 25000) -> str:
    """Read a file from the project repository."""
    print(f"Tool: read_file('{path}')", file=sys.stderr)
    is_safe, full_path = is_safe_path(path)
    if not is_safe:
        return f"Error: Access denied - path '{path}' is outside project directory"
    if not full_path.exists():
        return f"Error: File not found - '{path}'"
    try:
        content = full_path.read_text(encoding="utf-8")
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n... [truncated]"
        return content
    except Exception as e:
        return f"Error: Could not read file - {e}"


def search_file(path: str, query: str) -> str:
    """Search for a pattern in a file."""
    print(f"Tool: search_file('{path}', '{query}')", file=sys.stderr)
    is_safe, full_path = is_safe_path(path)
    if not is_safe or not full_path.is_file():
        return f"Error: Invalid file path '{path}'"
    try:
        content = full_path.read_text(encoding="utf-8")
        lines = content.split('\n')
        matches = []
        for i, line in enumerate(lines, 1):
            if query.lower() in line.lower():
                start = max(0, i - 3)
                end = min(len(lines), i + 3)
                context = '\n'.join(f"{j}: {lines[j-1]}" for j in range(start, end))
                matches.append(f"MATCH AT LINE {i}:\n{context}")
        return '\n\n---\n\n'.join(matches) or f"No matches found for '{query}'"
    except Exception as e:
        return f"Error: {e}"


def list_files(path: str) -> str:
    """List files and directories at a given path."""
    print(f"Tool: list_files('{path}')", file=sys.stderr)
    is_safe, full_path = is_safe_path(path)
    if not is_safe or not full_path.is_dir():
        return f"Error: Invalid directory path '{path}'"
    try:
        return "\n".join(sorted([e.name for e in full_path.iterdir()]))
    except Exception as e:
        return f"Error: {e}"


def query_api(method: str, path: str, body: str | None = None, auth: bool = True) -> str:
    """Call the backend API."""
    print(f"Tool: query_api('{method}' {path}, auth={auth})", file=sys.stderr)
    config = load_config()
    url = f"{config['agent_api_base_url'].rstrip('/')}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if auth and config["lms_api_key"]:
        headers["Authorization"] = f"Bearer {config['lms_api_key']}"

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method.upper(), url, headers=headers, content=body)
        return json.dumps({"status_code": response.status_code, "body": response.text})
    except Exception as e:
        return f"Error: API call failed - {e}"


TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api,
    "search_file": search_file,
}


def call_llm(messages: list[dict], config: dict) -> str:
    """Call the LLM API."""
    url = f"{config['llm_api_base']}/chat/completions"
    headers = {"Authorization": f"Bearer {config['llm_api_key']}"}
    payload = {"model": config["llm_model"], "messages": messages, "temperature": 0}
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"].get("content") or ""
            return content
    except Exception as e:
        print(f"LLM API error: {e}", file=sys.stderr)
        return ""


def parse_llm_response(content: str) -> dict | None:
    """Parse JSON from LLM response."""
    content = content.strip()
    
    # Try to clean up content (remove markdown code blocks)
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    
    # Try parsing direct JSON
    try:
        data = json.loads(content)
        return normalize_json(data)
    except json.JSONDecodeError:
        # Try finding JSON in the string
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return normalize_json(data)
            except:
                # Handle common malformed JSON
                try:
                    malformed = match.group()
                    fixed = re.sub(r'("tool":\s*"[^"]*")\s*("args":)', r'\1, \2', malformed)
                    fixed = re.sub(r'\{"(\w+)",\s*"args":', r'{"tool": "\1", "args":', fixed)
                    return normalize_json(json.loads(fixed))
                except:
                    pass
    return None

def normalize_json(data: dict) -> dict:
    """Normalize tool call formats."""
    if not isinstance(data, dict):
        return data
        
    for tool_name in TOOL_FUNCTIONS.keys():
        if tool_name in data and isinstance(data[tool_name], dict) and "tool" not in data:
            return {"tool": tool_name, "args": data[tool_name]}
            
    return data


def run_agentic_loop(question: str, config: dict) -> dict:
    """Main agentic loop."""
    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tool_calls_log = []

    for _ in range(MAX_TOOL_CALLS):
        content = call_llm(conversation, config)
        if not content:
            break

        parsed = parse_llm_response(content)
        if not parsed:
            # Fallback for common errors
            for tool_name in TOOL_FUNCTIONS.keys():
                if f'"{tool_name}"' in content and '"args"' in content:
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if match:
                        try:
                            malformed = match.group()
                            fixed = re.sub(r'("tool":\s*"[^"]*")\s*("args":)', r'\1, \2', malformed)
                            fixed = re.sub(r'\{"(\w+)",\s*"args":', r'{"tool": "\1", "args":', fixed)
                            parsed = normalize_json(json.loads(fixed))
                            break
                        except:
                            pass
            
            if not parsed:
                if len(content) > 10:
                    return {"answer": content, "source": "LLM reasoning", "tool_calls": tool_calls_log}
                break

        if "answer" in parsed:
            return {
                "answer": parsed["answer"],
                "source": parsed.get("source", ""),
                "tool_calls": tool_calls_log,
            }

        if "tool" in parsed and "args" in parsed:
            tool_name = parsed["tool"]
            tool_args = parsed["args"]
            if tool_name in TOOL_FUNCTIONS:
                # Ensure all arguments are passed correctly
                try:
                    result = TOOL_FUNCTIONS[tool_name](**tool_args)
                except TypeError as e:
                    result = f"Error: Invalid arguments for tool {tool_name}: {e}"
                
                tool_calls_log.append({"tool": tool_name, "args": tool_args, "result": result})
                conversation.append({"role": "assistant", "content": json.dumps(parsed)})
                conversation.append({"role": "user", "content": f"Tool result:\n{result}"})
                continue

        break

    return {"answer": "I couldn't find the answer.", "source": "", "tool_calls": tool_calls_log}


def main():
    if len(sys.argv) != 2:
        print("Usage: uv run agent.py \"question\"", file=sys.stderr)
        sys.exit(1)
    
    config = load_config()
    result = run_agentic_loop(sys.argv[1], config)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
