# Task 3: The System Agent - Implementation Plan

## 1. Goal
The goal is to enhance the agent from Task 2 with a `query_api` tool, allowing it to interact with the deployed backend. The agent should be able to answer static system questions, data-dependent queries, and diagnose bugs by combining API results with source code analysis.

## 2. Implementation Strategy

### 2.1 Clean up `agent.py`
The current `agent.py` was cleaned of hardcoded overrides and "last resort" answer generation logic. The agent now relies entirely on the LLM's reasoning, improved system prompt, and tools.

### 2.2 Define `query_api` tool
- **Parameters**: `method`, `path`, `body` (optional), `auth` (optional boolean, default true).
- **Authentication**: Uses `LMS_API_KEY` from environment variables.
- **Base URL**: Uses `AGENT_API_BASE_URL` (default: `http://localhost:42002`).
- **Response**: Returns a JSON string with `status_code` and `body`.

### 2.3 Update System Prompt
The system prompt was updated with specific strategies:
- **Data Queries**: Use `query_api` and count items in the returned array.
- **System Facts**: Use `read_file` on configuration files.
- **Bug Diagnosis**: 
    - Reproduce the error with `query_api`.
    - Handle 422 errors by providing missing parameters.
    - Analyze source code for 500 errors (division by zero, None-unsafe sorting).
- **Request Lifecycle**: Trace the path through multiple files.
- **Component Comparison**: Read source files for both components and compare.

### 2.4 Environment Variables
Configuration is read from environment variables:
- `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`
- `LMS_API_KEY`
- `AGENT_API_BASE_URL`

## 3. Iteration Strategy
1. Cleaned `agent.py`.
2. Improved JSON parsing and normalization to handle inconsistent LLM outputs.
3. Added `auth` parameter to `query_api` for unauthenticated testing.
4. Refined bug diagnosis prompt to handle 422 validation errors.

## 4. Benchmark Results
- **Initial Score**: 0/10 (failed on first question due to logic error in loop)
- **Second Score**: 3/10 (failed on JSON formatting for tool calls)
- **Third Score**: 5/10 (failed on unauthenticated status code check)
- **Fourth Score**: 7/10 (failed on bug diagnosis because it didn't try with parameters)
- **Final Score**: 10/10 (passed all local questions)

### Fixes:
- Improved `parse_llm_response` to handle markdown code blocks and malformed JSON (missing commas, incorrect tool call formats).
- Added `auth: bool` to `query_api` to allow testing unauthenticated endpoints.
- Updated `SYSTEM_PROMPT` to instruct the LLM to provide parameters (like `?lab=lab-1`) when it receives a 422 error during bug diagnosis.
