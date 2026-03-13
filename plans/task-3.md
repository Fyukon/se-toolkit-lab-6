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
3. query_api - Call the deployed backend API

When to use each tool:
- Use list_files/read_file for wiki documentation questions
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

## Path Security

Keep the existing `is_safe_path()` function for `read_file` and `list_files`.

The `query_api` tool doesn't need path security (API handles its own auth).

## Benchmark Strategy

### Initial Run

Run `uv run run_eval.py` to see baseline performance.

### Expected Failures

1. **Wiki questions** — should work (Task 2 already handles these)
2. **System facts** — may fail if LLM doesn't know when to use `query_api`
3. **Data queries** — will fail until `query_api` is implemented correctly
4. **Bug diagnosis** — may require multi-step reasoning

### Iteration Strategy

1. Fix `query_api` implementation first
2. Improve system prompt if LLM doesn't choose the right tool
3. Add better error handling for API failures
4. Adjust tool descriptions if LLM misunderstands parameters

## Testing

Add 2 new regression tests:

1. **System fact question:** "What framework does the backend use?"
   - Expected: `read_file` tool (to read pyproject.toml or wiki)

2. **Data query question:** "How many items are in the database?"
   - Expected: `query_api` tool with GET /items/

## Implementation Steps

1. Create `plans/task-3.md` (this file)
2. Update `.env.docker.secret` with `LMS_API_KEY`
3. Update `load_config()` to read both `.env` files
4. Implement `query_api()` tool
5. Add `query_api` to `TOOL_FUNCTIONS`
6. Update `SYSTEM_PROMPT` to include `query_api`
7. Update `AGENT.md` documentation
8. Add 2 regression tests
9. Run `run_eval.py` and iterate
10. Commit plan first, then code

## Output Format

```json
{
  "answer": "There are 120 items in the database.",
  "source": "API: GET /items/",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": {...}}"
    }
  ]
}
```

Note: `source` is now optional and can reference API endpoints.
