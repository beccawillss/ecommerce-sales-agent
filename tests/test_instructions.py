"""Tests for the stable Phase 4 developer instruction boundary."""

from salesagent.agent.instructions import DEVELOPER_INSTRUCTIONS, PROMPT_VERSION


def test_instructions_are_versioned_lean_and_fixture_independent() -> None:
    assert PROMPT_VERSION == "phase4-v1"
    assert "search_products" in DEVELOPER_INSTRUCTIONS
    assert "check_inventory" in DEVELOPER_INSTRUCTIONS
    assert "authoritative" in DEVELOPER_INSTRUCTIONS
    assert "read-only" in DEVELOPER_INSTRUCTIONS
    assert "JKT-" not in DEVELOPER_INSTRUCTIONS
    assert "WELCOME10" not in DEVELOPER_INSTRUCTIONS
    assert len(DEVELOPER_INSTRUCTIONS) < 1600
