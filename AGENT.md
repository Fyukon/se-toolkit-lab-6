# The System Agent Architecture

## Overview

The System Agent is an advanced version of the Documentation Agent from Task 2. While the previous iteration focused on static wiki files, the System Agent bridges the gap between documentation and the live system. It is equipped with a `query_api` tool that allows it to interact directly with the deployed backend API, enabling it to answer questions about the current state of the database, verify system facts, and diagnose bugs by combining live error reports with source code analysis.

## Tools and Integration

The agent's capabilities are built around four core tools:
- **`list_files`** and **`read_file`**: These remain essential for navigating the codebase and reading wiki documentation. The agent uses them to find architectural details in `docker-compose.yml`, `Dockerfile`, and `main.py`.
- **`search_file`**: This tool is used to quickly locate specific code patterns or documentation sections, which is particularly useful for identifying buggy lines in the source code.
- **`query_api`**: This is the key addition for Task 3. It supports standard HTTP methods (`GET`, `POST`, etc.) and includes optional authentication via `LMS_API_KEY`. It also supports an `auth=false` mode to test the system's behavior for unauthenticated requests.

## Intelligence and Strategy

The core of the agent is its updated system prompt, which defines clear strategies for complex scenarios:
- **Data-Dependent Queries**: Instead of relying on hardcoded knowledge, the agent fetches data from endpoints like `/items/` or `/learners/` and performs its own analysis (e.g., counting the results).
- **Bug Diagnosis**: When asked about a bug, the agent follows a multi-step process. First, it uses `query_api` to reproduce the error. If it receives a 422 validation error, it is instructed to retry with appropriate parameters (like a lab ID). Once it observes a 500 error, it reads the relevant router code to identify the root cause, such as a `ZeroDivisionError` or a `TypeError` in a `sorted()` call involving `None` values.
- **Request Lifecycle**: The agent can trace a request from the browser through the Caddy reverse proxy to the FastAPI application and finally to the PostgreSQL database by synthesizing information from multiple configuration and source files.

## Lessons Learned from Benchmarking

The development process was highly iterative, guided by the `run_eval.py` benchmark. Several key improvements were made based on failures:
- **JSON Robustness**: LLMs can be inconsistent in their output formatting. The agent's parsing logic was improved to handle markdown code blocks and common malformed JSON (like missing commas between fields).
- **Validation vs. Crash**: Initial versions of the agent would stop at a 422 error, thinking it had found the bug. The strategy was refined to distinguish between validation errors and actual system crashes (500), encouraging the agent to provide missing parameters to reach the deeper logic.
- **Tool Normalization**: To accommodate different LLM models, the agent now normalizes various tool call formats into a standard structure, ensuring consistent execution across different platforms.

The final result is a genuinely autonomous agent that can navigate the repository, query the API, and reason about the system's behavior without relying on hardcoded answers.
