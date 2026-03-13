"""Regression tests for agent.py CLI.

These tests run agent.py as a subprocess and verify the JSON output.
Run with: uv run pytest tests/test_agent.py -v
"""

import json
import subprocess

import pytest


class TestAgentOutput:
    """Test that agent.py produces valid JSON with required fields."""

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

        # Check field types
        assert isinstance(output["answer"], str), "'answer' must be a string"
        assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"

        # Check answer is non-empty
        assert len(output["answer"]) > 0, "'answer' must not be empty"

        # Check tool_calls is empty (Task 1 doesn't use tools)
        assert len(output["tool_calls"]) == 0, "'tool_calls' must be empty for Task 1"
