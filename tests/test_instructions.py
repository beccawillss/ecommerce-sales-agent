"""Tests for the stable Phase 6 developer instruction boundary."""

from salesagent.agent.instructions import DEVELOPER_INSTRUCTIONS, PROMPT_VERSION


def test_instructions_are_versioned_lean_and_fixture_independent() -> None:
    assert PROMPT_VERSION == "phase6-v2"
    assert "search_products" in DEVELOPER_INSTRUCTIONS
    assert "check_inventory" in DEVELOPER_INSTRUCTIONS
    assert "authoritative" in DEVELOPER_INSTRUCTIONS
    assert "read-only" in DEVELOPER_INSTRUCTIONS
    assert "nominated_product_ids" in DEVELOPER_INSTRUCTIONS
    assert "current turn" in DEVELOPER_INSTRUCTIONS
    assert "salesagent_context" in DEVELOPER_INSTRUCTIONS
    assert "retain" in DEVELOPER_INSTRUCTIONS
    assert "complete list" in DEVELOPER_INSTRUCTIONS
    assert "tool results" in DEVELOPER_INSTRUCTIONS
    assert "exact catalogue filters" in DEVELOPER_INSTRUCTIONS
    assert 'broader shopper wording such as "blue"' in DEVELOPER_INSTRUCTIONS
    assert "known safe constraints" in DEVELOPER_INSTRUCTIONS
    assert "Historical accepted product IDs are reference context only" in (
        DEVELOPER_INSTRUCTIONS
    )
    assert "refresh a historical ID using get_product" in DEVELOPER_INSTRUCTIONS
    assert "authoritative grounding from the current turn" in DEVELOPER_INSTRUCTIONS
    assert "JKT-" not in DEVELOPER_INSTRUCTIONS
    assert "WELCOME10" not in DEVELOPER_INSTRUCTIONS
    assert len(DEVELOPER_INSTRUCTIONS) < 3500
