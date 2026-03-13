# Agent Documentation

## Overview

This agent is a CLI tool that connects to an LLM (Large Language Model) with access to tools for reading project documentation, searching files, and querying the backend API. It implements an agentic loop that allows the LLM to iteratively explore the wiki, search source code, and query the API to answer questions.

## Architecture

### LLM Provider

**Provider:** Qwen Code API (self-hosted on VM via qwen-code-oai-proxy)

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**
- 1000 free requests per day
- Works from Russia
- No credit card required
- OpenAI-compatible API

### Configuration

The agent reads configuration from two environment files:

#### `.env.agent.secret` (LLM Configuration)

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_BASE` | API endpoint URL | `http://10.93.24.180:42005/v1` |
| `LLM_API_KEY` | Authentication key | `alex_qwen` |
| `LLM_MODEL` | Model name | `qwen3-coder-plus` |

#### `.env.docker.secret` (Backend Configuration)

| Variable | Description | Example |
|----------|-------------|---------|
| `LMS_API_KEY` | Backend API key for `query_api` auth | `alex` |
| `AGENT_API_BASE_URL` | Base URL for backend API | `http://localhost:42001` |

> **Important:** The autochecker injects its own values. Never hardcode API keys or URLs.

### Tools

The agent has four tools available:

#### `read_file`

Read the contents of a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns:** File contents as a string (truncated to 15000 chars), or an error message.

**Security:** The tool validates paths to prevent directory traversal attacks (`../`).

#### `list_files`

List files and directories in a given directory.

**Parameters:**
- `path` (string, required): Relative directory path from project root (e.g., `wiki`)

**Returns:** Newline-separated list of file/directory names.

**Security:** The tool validates paths to prevent accessing directories outside the project root.

#### `search_file`

Search for a keyword pattern in a file and return matching lines with context.

**Parameters:**
- `path` (string, required): Relative file path from project root
- `query` (string, required): Search pattern (case-insensitive)

**Returns:** Matching lines with line numbers and context (2 lines before/after).

**Security:** Same path validation as `read_file`.

#### `query_api`

Call the deployed backend API to get system information or data.

**Parameters:**
- `method` (string, required): HTTP method (GET, POST, PUT, DELETE, PATCH)
- `path` (string, required): API endpoint path (e.g., `/items/`, `/analytics/scores`)
- `body` (string, optional): JSON request body for POST/PUT/PATCH requests

**Returns:** JSON string with `status_code` and `body`.

**Authentication:** Uses `LMS_API_KEY` from `.env.docker.secret` via `Authorization: Bearer <key>` header.

### Agentic Loop

The agent implements an iterative loop:

```
User Question
    ↓
[Loop: max 12 iterations]
    ↓
Send conversation to LLM
    ↓
Parse response
    │
    ├── Tool call? ──yes──▶ Execute tool ──▶ Append result ──▶ Continue
    │                        │
    │                        └── Detect loops (same tool+args)
    │
    no (final answer)
    │
    ▼
Extract answer + source
    ↓
Output JSON
```

1. **Initialize** conversation with system prompt + user question
2. **Call LLM** with conversation history
3. **Parse response:**
   - If JSON with `tool` and `args` → execute tool, append result, continue
   - If JSON with `answer` → return final answer
   - If no JSON → treat as final answer
4. **Loop detection:** If same tool called with same arguments, generate answer from results
5. **Output** JSON with `answer`, `source`, and `tool_calls`

### System Prompt Strategy

The system prompt instructs the LLM to:
- Use JSON format for tool calls: `{"tool": "list_files", "args": {"path": "wiki"}}`
- Use JSON format for final answers: `{"answer": "...", "source": "wiki/file.md#section"}`
- Use `search_file` to find keywords in large files
- Use `query_api` for system facts and data queries
- Always cite sources (file path with optional section anchor or API endpoint)
- Never repeat the same tool call

### Tool Selection Guide

The LLM is instructed to choose tools based on question type:

| Question Type | Tool to Use |
|--------------|-------------|
| Wiki documentation | `list_files`, `read_file`, `search_file` |
| System facts (framework, ports) | `read_file` (source code), `query_api` |
| Data queries (item count, scores) | `query_api` |
| Bug diagnosis | `query_api` + `read_file` |

### Data Flow

```
User question (CLI argument)
    ↓
Load .env.agent.secret + .env.docker.secret
    ↓
Initialize conversation [system, user]
    ↓
[Agentic Loop]
    ├─▶ Call LLM API
    ├─▶ Parse response (handle multiple JSON formats)
    ├─▶ Execute tool (if needed)
    ├─▶ Detect loops
    └─▶ Append result to conversation
    ↓
Extract answer + source
    ↓
Output JSON to stdout
```

### Input/Output

**Input:**
```bash
uv run agent.py "How many items are in the database?"
```

**Output (stdout):**
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

**Debug output (stderr):**
```
=== Iteration 1 ===
Calling LLM API with 2 messages...
LLM response: {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}}...
Tool call: query_api({'method': 'GET', 'path': '/items/'})
Tool: query_api('GET' /items/)
  Status: 200

=== Iteration 2 ===
Calling LLM API with 4 messages...
LLM response: {"answer": "There are 44 items...", "source": "API: GET /items/"}...
Final answer received
```

## How to Run

1. Ensure `.env.agent.secret` is configured with LLM credentials
2. Ensure `.env.docker.secret` is configured with `LMS_API_KEY` and `AGENT_API_BASE_URL`
3. Run the agent:
   ```bash
   uv run agent.py "<your question>"
   ```

## Dependencies

- `httpx` — HTTP client for API calls
- `python-dotenv` — environment variable loading

## Security

Both file tools (`read_file`, `search_file`) implement path validation:
- Reject absolute paths
- Reject paths containing `..`
- Verify resolved path is within project root

This prevents directory traversal attacks.

The `query_api` tool uses bearer token authentication via `LMS_API_KEY`.

## Lessons Learned from Benchmark

### Challenges Encountered

1. **LLM doesn't follow JSON format strictly:** The Qwen Code API sometimes returns JSON in different formats (e.g., `{"list_files": {"path": "wiki"}}` instead of `{"tool": "list_files", "args": {"path": "wiki"}}`). The parser was updated to handle multiple formats.

2. **Infinite loops on repeated tool calls:** The LLM sometimes calls the same tool with the same arguments repeatedly. Loop detection was added to break these cycles and generate answers from available results.

3. **LLM doesn't know API endpoints:** The LLM has no built-in knowledge of the backend API schema. It may try incorrect endpoints like `/api/database/count` instead of `/items/`. Future improvements could include API schema documentation in the system prompt.

4. **Large files exceed token limits:** Files like `wiki/github.md` (19KB) are truncated to 15000 characters. The `search_file` tool was added to find specific sections without reading the entire file.

5. **LLM ignores search results:** Even when `search_file` finds relevant information, the LLM may continue searching instead of providing an answer. Loop detection helps, but better prompt engineering is needed.

### Iteration Strategy

1. Start with simple prompts and gradually add constraints
2. Add loop detection early to prevent wasted iterations
3. Handle multiple JSON formats in the parser
4. Generate answers from tool results when LLM fails
5. Consider adding API schema documentation for better endpoint discovery

## Final Evaluation Score

**Local run_eval.py status:** Partially passing

- Question 1 (wiki branch protection): Agent finds info but LLM struggles to format answer
- Question 2 (framework): Agent reads source code successfully
- Question 3 (item count): Agent uses query_api but may not find correct endpoint

**Known issues:**
- LLM sometimes doesn't follow JSON format strictly
- Loop detection triggers but generated answers may not be optimal
- API endpoint discovery needs improvement

## Extension Points

This is Task 3 implementation. Future improvements could include:

- **API schema documentation:** Provide the LLM with a list of valid API endpoints
- **Better answer generation:** Use LLM to summarize tool results when loops are detected
- **Multi-step reasoning:** Chain tool calls more effectively for complex questions
- **Caching:** Cache file reads and API calls to reduce redundant operations
