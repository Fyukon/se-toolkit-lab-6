# Plan for Task 3: The System Agent

## Overview

Extend the Task 2 agent with a new `query_api` tool that can call the deployed backend API. This allows the agent to answer questions about the actual system state (not just documentation).

## LLM Provider and Model

**Provider:** Qwen Code API (self-hosted on VM)
**Model:** `qwen3-coder-plus`

## New Tool: `query_api`

### Schema

```json
{
  "name": "query_api",
  "description": "Call the deployed backend API to get system information or data",
  "parameters": {
    "type": "object",
    "properties": {
      "method": {
        "type": "string",
        "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
      },
      "path": {
        "type": "string",
        "description": "API endpoint path (e.g., '/items/', '/analytics/scores')"
      },
      "body": {
        "type": "string",
        "description": "Optional JSON request body for POST/PUT/PATCH requests"
      }
    },
    "required": ["method", "path"]
  }
}
```

### Implementation

```python
def query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend API and return the response."""
    # Read LMS_API_KEY from .env.docker.secret
    # Read AGENT_API_BASE_URL from .env.docker.secret (default: http://localhost:42002)
    # Make HTTP request with Authorization header
    # Return JSON string with status_code and body
```

### Authentication

- Use `LMS_API_KEY` from `.env.docker.secret`
- Send as `Authorization: Bearer <LMS_API_KEY>` header
- This is different from `LLM_API_KEY` (which authenticates with the LLM provider)

## Environment Variables

The agent must read all configuration from environment variables:

| Variable | Purpose | Source | Required |
|----------|---------|--------|----------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | Yes |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` | Yes |
| `LLM_MODEL` | Model name | `.env.agent.secret` | Yes |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` | Yes |
| `AGENT_API_BASE_URL` | Base URL for backend API | `.env.docker.secret` | No (default: `http://localhost:42002`) |

### Updated `load_config()`

```python
def load_config() -> dict:
    """Load configuration from both .env files."""
    # Load LLM config from .env.agent.secret
    # Load LMS config from .env.docker.secret
    return {
        "llm_api_base": ...,
        "llm_api_key": ...,
        "llm_model": ...,
        "lms_api_key": ...,
        "agent_api_base_url": ...,
    }
```

> **Important:** The autochecker injects its own values. Never hardcode API keys or URLs.

## System Prompt Updates

The system prompt must guide the LLM to choose the right tool:

```
You are a documentation and system assistant with access to:
1. list_files - List files in a directory
2. read_file - Read contents of a file
3. search_file - Search for text in a file
4. query_api - Call the deployed backend API

When to use each tool:
- Use list_files/read_file/search_file for wiki documentation questions
- Use query_api for:
  - System facts (framework, ports, status codes)
  - Data queries (item count, scores, analytics)
  - Bug diagnosis (check API responses for errors)

For query_api:
- Use GET for reading data
- Include the full path (e.g., '/items/', '/analytics/scores')
- For POST/PUT, include a JSON body string

Always cite sources:
- wiki files: wiki/filename.md#section
- API responses: API endpoint (e.g., GET /items/)
- Code files: path/to/file.py
```

## Agentic Loop

The loop remains the same as Task 2, just with one more tool:

1. Send question + conversation to LLM
2. Parse response for tool call or answer
3. If tool call → execute, append result, continue
4. If answer → return with source

Additional features:
- Loop detection to prevent infinite cycles
- Answer generation from tool results when LLM fails

## Path Security

Keep the existing `is_safe_path()` function for `read_file` and `list_files`.

The `query_api` tool doesn't need path security (API handles its own auth).

## Benchmark Strategy

### Initial Run

Run `uv run run_eval.py` to see baseline performance.

### Current Status

- Question 1 (wiki branch protection): Agent finds info but LLM doesn't generate proper answer
- Question 2 (framework): Agent needs to read backend source code
- Question 3 (item count): Agent needs to use correct API endpoint `/items/`

### Known Issues

1. **LLM doesn't follow JSON format strictly** - Parser now handles multiple formats
2. **LLM zацикливается на repeated tool calls** - Added loop detection
3. **LLM doesn't know API endpoints** - Need to improve system prompt or add API discovery

### Iteration Strategy

1. Improve system prompt with API endpoint examples
2. Add better loop detection and recovery
3. Consider adding API schema documentation for the LLM

## Testing

Add 2 new regression tests:

1. **System fact question:** "What framework does the backend use?"
   - Expected: `read_file` tool (to read pyproject.toml or backend source)

2. **Data query question:** "How many items are in the database?"
   - Expected: `query_api` tool with GET /items/

## Implementation Steps

1. Create `plans/task-3.md` (this file) ✅
2. Update `.env.docker.secret` with `LMS_API_KEY` and `AGENT_API_BASE_URL` ✅
3. Update `load_config()` to read both `.env` files ✅
4. Implement `query_api()` tool ✅
5. Add `query_api` to `TOOL_FUNCTIONS` ✅
6. Add `search_file` tool for large file searching ✅
7. Update `SYSTEM_PROMPT` to include all tools ✅
8. Add loop detection ✅
9. Update `AGENT.md` documentation
10. Add 2 regression tests
11. Run `run_eval.py` and iterate
12. Commit plan first, then code

## Output Format

```json
{
  "answer": "There are 44 items in the database.",
  "source": "API: GET /items/",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": [...]}"
    }
  ]
}
```

Note: `source` is now optional and can reference API endpoints.
