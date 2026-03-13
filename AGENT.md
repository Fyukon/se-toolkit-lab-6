# Agent Documentation

## Overview

This agent is a CLI tool that connects to an LLM (Large Language Model) with access to tools for reading project documentation. It implements an agentic loop that allows the LLM to iteratively explore the wiki and answer questions based on the project documentation.

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

The agent reads configuration from `.env.agent.secret`:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_BASE` | API endpoint URL | `http://10.93.24.180:42005/v1` |
| `LLM_API_KEY` | Authentication key | `alex_qwen` |
| `LLM_MODEL` | Model name | `qwen3-coder-plus` |

### Tools

The agent has two tools available:

#### `read_file`

Read the contents of a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns:** File contents as a string, or an error message if the file doesn't exist.

**Security:** The tool validates paths to prevent directory traversal attacks (`../`).

#### `list_files`

List files and directories in a given directory.

**Parameters:**
- `path` (string, required): Relative directory path from project root (e.g., `wiki`)

**Returns:** Newline-separated list of file/directory names.

**Security:** The tool validates paths to prevent accessing directories outside the project root.

### Agentic Loop

The agent implements an iterative loop:

```
User Question
    ↓
[Loop: max 10 iterations]
    ↓
Send conversation to LLM
    ↓
Parse response
    │
    ├── Tool call? ──yes──▶ Execute tool ──▶ Append result ──▶ Continue
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
4. **Output** JSON with `answer`, `source`, and `tool_calls`

### System Prompt Strategy

The system prompt instructs the LLM to:
- Use JSON format for tool calls: `{"tool": "list_files", "args": {"path": "wiki"}}`
- Use JSON format for final answers: `{"answer": "...", "source": "wiki/file.md#section"}`
- Explore the wiki structure with `list_files` when needed
- Read specific files with `read_file` to find answers
- Always cite sources (file path with optional section anchor)

### Data Flow

```
User question (CLI argument)
    ↓
Load .env.agent.secret
    ↓
Initialize conversation [system, user]
    ↓
[Agentic Loop]
    ├─▶ Call LLM API
    ├─▶ Parse response
    ├─▶ Execute tool (if needed)
    └─▶ Append result to conversation
    ↓
Extract answer + source
    ↓
Output JSON to stdout
```

### Input/Output

**Input:**
```bash
uv run agent.py "How do you resolve a merge conflict?"
```

**Output (stdout):**
```json
{
  "answer": "A merge conflict occurs when two branches modify the same lines...",
  "source": "wiki/git.md#merge-conflict",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "api.md\ngit.md\ngit-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git.md"},
      "result": "# Git\n\n## Merge conflict\n..."
    }
  ]
}
```

**Debug output (stderr):**
```
=== Iteration 1 ===
Calling LLM API with 2 messages...
LLM response: {"tool": "list_files", "args": {"path": "wiki"}}...
Tool call: list_files({'path': 'wiki'})
Tool: list_files('wiki')
  Listed 72 entries

=== Iteration 2 ===
Calling LLM API with 4 messages...
...
```

## How to Run

1. Ensure `.env.agent.secret` is configured with valid credentials
2. Run the agent:
   ```bash
   uv run agent.py "<your question>"
   ```

## Dependencies

- `httpx` — HTTP client for API calls
- `python-dotenv` — environment variable loading

## Security

Both tools implement path validation:
- Reject absolute paths
- Reject paths containing `..`
- Verify resolved path is within project root

This prevents directory traversal attacks.

## Extension Points

This is Task 2 implementation. In Task 3, additional tools will be added:
- Tools for querying the backend API
- Tools for running tests
- Tools for analyzing code
