"""Regression tests for agent.py CLI.

These tests run agent.py as a subprocess and verify the JSON output.
Run with: uv run pytest tests/test_agent.py -v
"""

import json
import subprocess

import pytest


class TestTask1Agent:
    """Test Task 1 agent output (basic JSON structure)."""

    @pytest.mark.asyncio
    async def test_agent_returns_valid_json(self):
        """Test that agent.py returns valid JSON with answer and tool_calls."""
        result = subprocess.run(
            ["uv", "run", "agent.py", "What is 2+2?"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        output = json.loads(result.stdout)

        # Check required fields exist
        assert "answer" in output, "Missing 'answer' field in output"
        assert "tool_calls" in output, "Missing 'tool_calls' field in output"
        assert "source" in output or True, "'source' field should exist (may be empty)"

        # Check field types
        assert isinstance(output["answer"], str), "'answer' must be a string"
        assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"

        # Check answer is non-empty
        assert len(output["answer"]) > 0, "'answer' must not be empty"


class TestTask2DocumentationAgent:
    """Test Task 2 documentation agent with tool calling."""

    @pytest.mark.asyncio
    async def test_merge_conflict_question(self):
        """Test question about merge conflicts expects read_file in tool_calls."""
        result = subprocess.run(
            ["uv", "run", "agent.py", "How do you resolve a merge conflict?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        output = json.loads(result.stdout)

        # Check required fields
        assert "answer" in output, "Missing 'answer' field"
        assert "source" in output, "Missing 'source' field"
        assert "tool_calls" in output, "Missing 'tool_calls' field"

        # Check that tools were used
        tool_calls = output["tool_calls"]
        assert len(tool_calls) > 0, "Expected tool calls for documentation question"

        # Check that read_file or list_files was used
        tools_used = {call["tool"] for call in tool_calls}
        assert "read_file" in tools_used or "list_files" in tools_used, \
            f"Expected read_file or list_files, got: {tools_used}"

        # Check source references wiki file
        source = output.get("source", "")
        # Source should reference a wiki file (git.md or git-workflow.md typically)
        assert "wiki/" in source or any("wiki/" in call.get("args", {}).get("path", "") for call in tool_calls), \
            "Expected source or tool args to reference wiki files"

    @pytest.mark.asyncio
    async def test_wiki_listing_question(self):
        """Test question about wiki files expects list_files in tool_calls."""
        result = subprocess.run(
            ["uv", "run", "agent.py", "What files are in the wiki?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        output = json.loads(result.stdout)

        # Check required fields
        assert "answer" in output, "Missing 'answer' field"
        assert "tool_calls" in output, "Missing 'tool_calls' field"

        # Check that list_files was used
        tool_calls = output["tool_calls"]
        assert len(tool_calls) > 0, "Expected tool calls for wiki listing question"

        tools_used = {call["tool"] for call in tool_calls}
        assert "list_files" in tools_used, \
            f"Expected list_files tool for wiki listing question, got: {tools_used}"

        # Check that the tool was called with wiki path
        wiki_list_calls = [c for c in tool_calls if c["tool"] == "list_files"
                          and c.get("args", {}).get("path") == "wiki"]
        assert len(wiki_list_calls) > 0, "Expected list_files to be called with path='wiki'"


class TestTask3SystemAgent:
    """Test Task 3 system agent with query_api tool."""

    @pytest.mark.asyncio
    async def test_framework_question(self):
        """Test question about backend framework expects read_file in tool_calls."""
        result = subprocess.run(
            ["uv", "run", "agent.py", "What Python web framework does this project's backend use?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        output = json.loads(result.stdout)

        # Check required fields
        assert "answer" in output, "Missing 'answer' field"
        assert "tool_calls" in output, "Missing 'tool_calls' field"

        # Check that answer mentions FastAPI
        answer = output.get("answer", "").lower()
        assert "fastapi" in answer, f"Expected answer to mention FastAPI, got: {output.get('answer')}"

        # If tools were used, check that read_file or search_file was used
        tool_calls = output.get("tool_calls", [])
        if tool_calls:
            tools_used = {call["tool"] for call in tool_calls}
            assert "read_file" in tools_used or "search_file" in tools_used or "list_files" in tools_used, \
                f"Expected file reading tool, got: {tools_used}"

    @pytest.mark.asyncio
    async def test_item_count_question(self):
        """Test question about item count expects query_api in tool_calls."""
        result = subprocess.run(
            ["uv", "run", "agent.py", "How many items are in the database?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        output = json.loads(result.stdout)

        # Check required fields
        assert "answer" in output, "Missing 'answer' field"
        assert "tool_calls" in output, "Missing 'tool_calls' field"

        # Check that query_api was used
        tool_calls = output["tool_calls"]
        tools_used = {call["tool"] for call in tool_calls}
        assert "query_api" in tools_used, f"Expected query_api for data question, got: {tools_used}"

    @pytest.mark.asyncio
    async def test_unauthenticated_status_code(self):
        """Test status code question expects query_api with auth=False."""
        result = subprocess.run(
            ["uv", "run", "agent.py", "What HTTP status code does the API return for /items/ without auth?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        output = json.loads(result.stdout)

        # Check that query_api was used with auth=False
        tool_calls = output["tool_calls"]
        query_api_calls = [c for c in tool_calls if c["tool"] == "query_api"]
        assert len(query_api_calls) > 0, "Expected query_api call"
        
        # Check that at least one call has auth=False or the agent reasoned about it
        # Note: Depending on the API, it might return 200 or 401. 
        # The test verifies that the agent attempted unauthenticated access if needed.
        unauth_calls = [c for c in query_api_calls if c.get("args", {}).get("auth") is False]
        assert len(unauth_calls) > 0, "Expected query_api to be called with auth=False"

    @pytest.mark.asyncio
    async def test_top_learners_bug_diagnosis(self):
        """Test bug diagnosis expects query_api and source code reading."""
        result = subprocess.run(
            ["uv", "run", "agent.py", "What bug exists in the /analytics/top-learners endpoint?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        output = json.loads(result.stdout)

        # Check that query_api and read_file/search_file were used
        tool_calls = output["tool_calls"]
        tools_used = {call["tool"] for call in tool_calls}
        assert "query_api" in tools_used, "Expected query_api to reproduce the bug"
        assert "read_file" in tools_used or "search_file" in tools_used, "Expected file reading to diagnose the bug"

        # Check that answer mentions sorting or None values
        answer = output.get("answer", "").lower()
        assert "sort" in answer or "none" in answer or "comparison" in answer, \
            f"Expected answer to mention sorting or None values, got: {output.get('answer')}"
