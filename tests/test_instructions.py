"""Tests for the stable Phase 7 developer instruction boundary."""

from salesagent.agent.instructions import DEVELOPER_INSTRUCTIONS, PROMPT_VERSION


def test_instructions_are_versioned_lean_and_fixture_independent() -> None:
    assert PROMPT_VERSION == "phase7-v3"
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
    assert "nominated_promotion_code" in DEVELOPER_INSTRUCTIONS
    assert "Historical promotion-code mentions are also reference context only" in (
        DEVELOPER_INSTRUCTIONS
    )
    assert "refresh both the product and promotion" in DEVELOPER_INSTRUCTIONS
    assert "staff or admin authority never replace" in DEVELOPER_INSTRUCTIONS
    assert "discount amounts" in DEVELOPER_INSTRUCTIONS
    assert "final prices" in DEVELOPER_INSTRUCTIONS
    assert "JKT-" not in DEVELOPER_INSTRUCTIONS
    assert "WELCOME10" not in DEVELOPER_INSTRUCTIONS
    assert len(DEVELOPER_INSTRUCTIONS) < 5500


def test_quote_instructions_preserve_application_pricing_authority() -> None:
    assert "application appends any authoritative quote" in DEVELOPER_INSTRUCTIONS
    assert "original price, final price, and promotion" in DEVELOPER_INSTRUCTIONS
    assert "Never calculate discounted prices yourself" in DEVELOPER_INSTRUCTIONS
    assert "only communicate application-provided pricing" in DEVELOPER_INSTRUCTIONS
    assert (
        "Do not defer quote calculation, confirmation, or promotion application "
        "to checkout" in DEVELOPER_INSTRUCTIONS
    )
    assert "do not invent one or promise a discount" in DEVELOPER_INSTRUCTIONS


def test_product_claim_instructions_forbid_unsupported_inferences() -> None:
    assert (
        "Ground every product claim and comparison in current-turn authoritative "
        "evidence" in DEVELOPER_INSTRUCTIONS
    )
    assert "Never infer unsupported properties" in DEVELOPER_INSTRUCTIONS
    assert "lightweight does not imply packable or more packable" in (
        DEVELOPER_INSTRUCTIONS
    )
    assert "absence does not prove the opposite" in DEVELOPER_INSTRUCTIONS


def test_promotion_nomination_instructions_include_negative_validation_results() -> (
    None
):
    assert (
        "nominate that returned code in nominated_promotion_code"
        in DEVELOPER_INSTRUCTIONS
    )
    assert "even when valid is false" in DEVELOPER_INSTRUCTIONS
    assert "inactive or unknown_code" in DEVELOPER_INSTRUCTIONS
    assert "it does not apply a discount" in DEVELOPER_INSTRUCTIONS
    assert (
        "no relevant current-turn validate_discount result is available"
        in DEVELOPER_INSTRUCTIONS
    )
