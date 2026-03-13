# Agent Documentation

## Overview

This agent is a CLI tool that connects to an LLM (Large Language Model) and returns structured JSON answers. It serves as the foundation for the intelligent agent that will be extended with tools and agentic loop in subsequent tasks.

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

### Data Flow

```
User question (CLI argument)
    ↓
Load .env.agent.secret
    ↓
Create HTTP request to LLM API
    ↓
Parse LLM response
    ↓
Output JSON to stdout
```

### Components

1. **`load_config()`** — loads environment variables from `.env.agent.secret`
2. **`call_llm()`** — sends HTTP POST request to the LLM API endpoint
3. **`main()`** — CLI entry point, parses arguments, orchestrates the flow

### Input/Output

**Input:**
```bash
uv run agent.py "What does REST stand for?"
```

**Output (stdout):**
```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

**Debug output (stderr):**
```
Calling LLM with model: qwen3-coder-plus
LLM response received
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

## Extension Points

This is Task 1 implementation. In subsequent tasks:

- **Task 2:** Add tools (functions the agent can call)
- **Task 3:** Add agentic loop (iterative tool usage)
