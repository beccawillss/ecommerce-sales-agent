"""Tests for the stable Phase 5 developer instruction boundary."""

from salesagent.agent.instructions import DEVELOPER_INSTRUCTIONS, PROMPT_VERSION


def test_instructions_are_versioned_lean_and_fixture_independent() -> None:
    assert PROMPT_VERSION == "phase5-v1"
    assert "search_products" in DEVELOPER_INSTRUCTIONS
    assert "check_inventory" in DEVELOPER_INSTRUCTIONS
    assert "authoritative" in DEVELOPER_INSTRUCTIONS
    assert "read-only" in DEVELOPER_INSTRUCTIONS
    assert "nominated_product_ids" in DEVELOPER_INSTRUCTIONS
    assert "current turn" in DEVELOPER_INSTRUCTIONS
    assert "empty list" in DEVELOPER_INSTRUCTIONS
    assert "JKT-" not in DEVELOPER_INSTRUCTIONS
    assert "WELCOME10" not in DEVELOPER_INSTRUCTIONS
    assert len(DEVELOPER_INSTRUCTIONS) < 2200
