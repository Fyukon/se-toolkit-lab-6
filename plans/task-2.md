# Plan for Task 2: The Documentation Agent

## Overview

Extend the Task 1 agent with tools (`read_file`, `list_files`) and an agentic loop that allows the LLM to iteratively query the project wiki to answer questions.

## LLM Provider and Model

**Provider:** Qwen Code API (self-hosted on VM)
**Model:** `qwen3-coder-plus`

This model supports function calling (tool calls) natively.

## Tool Definitions

### `read_file`

**Purpose:** Read contents of a file from the project.

**Schema:**
```json
{
  "name": "read_file",
  "description": "Read a file from the project repository",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Relative path from project root"}
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Use `pathlib.Path` to resolve the file
- Security check: ensure resolved path is within project root (no `../` traversal)
- Return file contents as string, or error message if file doesn't exist

### `list_files`

**Purpose:** List files and directories at a given path.

**Schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories in a directory",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Relative directory path from project root"}
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Use `pathlib.Path.iterdir()` or `os.listdir()`
- Security check: ensure resolved path is within project root
- Return newline-separated list of entries

## Path Security

Both tools must prevent directory traversal attacks:

1. Resolve the requested path against project root
2. Check that the resolved path starts with the project root
3. Reject any path containing `..` or absolute paths
4. Return error message if security check fails

```python
def is_safe_path(requested_path: str) -> bool:
    project_root = Path(__file__).parent.resolve()
    full_path = (project_root / requested_path).resolve()
    return str(full_path).startswith(str(project_root))
```

## Agentic Loop

The loop will:

1. **Initialize** messages list with system prompt + user question
2. **Loop** (max 10 iterations):
   - Call LLM with messages + tool definitions
   - If response has `tool_calls`:
     - Execute each tool
     - Append tool results as `tool` role messages
     - Continue loop
   - If response has text content (no tool calls):
     - Extract answer and source
     - Break loop
3. **Output** JSON with `answer`, `source`, `tool_calls`

### Message Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # ... tool results appended during loop
]
```

### Tool Call Format (OpenAI-compatible)

```json
{
  "name": "read_file",
  "arguments": {"path": "wiki/git-workflow.md"}
}
```

### Tool Result Format

Append as `tool` role message:
```python
{
    "role": "tool",
    "name": "read_file",
    "content": "file contents here"
}
```

## System Prompt

The system prompt will instruct the LLM to:

1. Use `list_files` to discover wiki files when needed
2. Use `read_file` to read specific files
3. Always include a source reference (file path + optional section anchor)
4. Stop calling tools when enough information is gathered
5. Provide concise answers based on wiki content

Example:
```
You are a documentation assistant. You have access to two tools:
- list_files: List files in a directory
- read_file: Read contents of a file

To answer questions:
1. First explore the wiki structure with list_files if needed
2. Read relevant files with read_file
3. Find the answer and cite the source (file path + section if applicable)
4. When you have the answer, respond with the final message (no tool calls)

Always include the source field in your final answer.
```

## Output Format

```json
{
  "answer": "The answer text from LLM",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

## Implementation Steps

1. Create `plans/task-2.md` (this file)
2. Update `agent.py`:
   - Add tool definitions (schemas)
   - Implement `read_file()` and `list_files()` functions
   - Implement path security checks
   - Implement agentic loop with max 10 iterations
   - Update output JSON to include `source` field
3. Update `AGENT.md` with tool documentation
4. Add 2 regression tests:
   - Test merge conflict question (expects `read_file`, wiki source)
   - Test wiki listing question (expects `list_files`)
5. Test manually with example questions
6. Commit plan first, then code

## Data Flow Diagram

```
User Question
    ↓
[Loop Start]
    ↓
Build messages (system + user + tool results)
    ↓
Call LLM with tools parameter
    ↓
Has tool_calls? ──yes──▶ Execute tools ──▶ Store results ──▶ [Continue Loop]
    │
    no (has content)
    │
    ▼
Extract answer + source
    ↓
Build output JSON
    ↓
Print to stdout
```

## Testing Strategy

**Test 1: Merge Conflict Question**
- Question: "How do you resolve a merge conflict?"
- Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

**Test 2: Wiki Listing Question**
- Question: "What files are in the wiki?"
- Expected: `list_files` in tool_calls

Run with: `uv run pytest tests/test_agent.py -v`
