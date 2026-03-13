# Plan for Task 1: Call an LLM from Code

## LLM Provider and Model

**Provider:** Qwen Code API (self-hosted on VM via qwen-code-oai-proxy)

**Model:** `qwen3-coder-plus`

**Why this choice:**
- Already set up on the VM
- Provides 1000 free requests per day
- Works from Russia
- OpenAI-compatible API endpoint
- No credit card required

**API Configuration:**
- `LLM_API_BASE`: `http://<vm-ip>:<port>/v1` (OpenAI-compatible endpoint)
- `LLM_MODEL`: `qwen3-coder-plus`
- `LLM_API_KEY`: stored in `.env.agent.secret`

## Agent Structure

The agent will be a Python CLI program (`agent.py`) with the following structure:

### 1. Environment Loading
- Read configuration from `.env.agent.secret` using `python-dotenv`
- Extract `LLM_API_BASE`, `LLM_API_KEY`, and `LLM_MODEL`

### 2. Command-Line Interface
- Accept a single positional argument: the user's question
- Use `argparse` or `sys.argv` for parsing

### 3. LLM Client
- Use the `openai` Python package (compatible with Qwen Code API)
- Create a `OpenAI` client with:
  - `base_url` from `LLM_API_BASE`
  - `api_key` from `LLM_API_KEY`
- Call `chat.completions.create()` with:
  - `model`: from `LLM_API_BASE`
  - `messages`: `[{"role": "user", "content": question}]`
  - `temperature`: 0 (for deterministic answers)

### 4. Response Processing
- Extract the answer from `response.choices[0].message.content`
- Build the output JSON: `{"answer": "...", "tool_calls": []}`
- `tool_calls` is empty for this task (will be populated in Task 2)

### 5. Output
- Print JSON to stdout (single line, compact format)
- All debug/logging output goes to stderr
- Exit code 0 on success

### Data Flow

```
User question (CLI arg)
    ↓
Load .env.agent.secret
    ↓
Create OpenAI client
    ↓
Call LLM API
    ↓
Parse response
    ↓
Output JSON to stdout
```

## Implementation Steps

1. Create `.env.agent.secret` from `.env.agent.example` with actual VM credentials
2. Install dependencies: `openai`, `python-dotenv` (check `pyproject.toml`)
3. Create `agent.py` with:
   - Environment loading
   - CLI argument parsing
   - LLM client setup
   - Response formatting
4. Test with a simple question
5. Create `AGENT.md` documentation
6. Write 1 regression test

## Testing

The test will:
- Run `agent.py "test question"` as a subprocess
- Parse stdout as JSON
- Verify `answer` field exists and is non-empty
- Verify `tool_calls` field exists and is an empty array
