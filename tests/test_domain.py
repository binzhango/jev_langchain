from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal

import pytest

from jev_harness.domain import SCENARIOS, SupportWorld, get_scenario, outcome


def args(amount=9, order_id="ORD-1001"):
    return {"order_id": order_id, "amount": amount, "reason": "Missing item"}


def world_with_total(total=250):
    fixture = get_scenario("hard-ceiling")["fixture"]
    fixture["order"]["total"] = total
    return SupportWorld(fixture)


@pytest.mark.parametrize("amount,verdict", [(0, "deny"), (-1, "deny"), (0.01, "allow"),
                                           (25, "allow"), (25.01, "review"), (200, "review"), (200.01, "deny")])
def test_amount_boundaries(amount, verdict):
    assert world_with_total().evaluate_refund(args(amount))["verdict"] == verdict


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), -float("inf"), "NaN", "Infinity",
                                    Decimal("sNaN"), True, None, {}, "not money", "9.001", "1e1000"])
def test_invalid_money_never_mutates(amount):
    world = world_with_total()
    original = deepcopy(world.data)
    assert world.refund(args(amount), approved=True)["status"] == "denied"
    assert world.data == original


def test_decimal_cents_and_trailing_zeros():
    world = world_with_total()
    assert world.refund(args("9.0100"))["refunded_amount"] == 9.01


def test_review_and_edited_arguments_cannot_override_policy():
    world = world_with_total()
    assert world.refund(args(40))["status"] == "review_required"
    assert world.data["refunds"] == []
    assert world.refund(args(250), approved=True)["status"] == "denied"
    assert world.refund(args(40, "someone-elses-order"), approved=True)["status"] == "denied"
    assert world.refund(args(40), approved=True)["status"] == "success"
    assert world.data["refunds"][0]["approved"] is True


def test_remaining_order_value_and_ownership():
    world = world_with_total(12)
    assert world.refund(args(12.01), approved=True)["status"] == "denied"
    world.data["order"]["customer_id"] = "another-customer"
    assert world.lookup("ORD-1001")["status"] == "error"
    assert world.refund(args(9), approved=True)["status"] == "denied"


def test_duplicate_or_split_refunds_are_denied_even_if_reason_changes():
    world = world_with_total()
    assert world.refund(args(9))["status"] == "success"
    assert world.refund({**args(10), "reason": "Different wording"}, approved=True)["status"] == "denied"
    assert len(world.data["refunds"]) == 1
    assert world.data["order"]["refunded_amount"] == 9


def test_concurrent_refunds_have_one_effect():
    world = world_with_total()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: world.refund(args(9)), range(2)))
    assert sum(r["status"] == "success" for r in results) == 1
    assert len(world.data["refunds"]) == 1


def test_semantic_justification_is_not_a_hidden_hard_rule():
    world = SupportWorld(get_scenario("unjustified-refund")["fixture"])
    assert world.evaluate_refund(args(9))["verdict"] == "allow"


def test_fixtures_paths_and_tool_results_are_isolated():
    scenario = get_scenario("missing-item")
    normal, jev = SupportWorld(scenario["fixture"]), SupportWorld(scenario["fixture"])
    normal.refund(args())
    assert jev.data["refunds"] == []
    assert scenario["fixture"]["refunds"] == []
    assert get_scenario("missing-item")["fixture"]["refunds"] == []
    result = jev.lookup("ORD-1001")
    result["order"]["total"] = 999
    assert jev.data["order"]["total"] == 25
    assert len({s["id"] for s in SCENARIOS}) == 6
    with pytest.raises(ValueError, match="Unknown scenario"):
        get_scenario("unknown")


def lookup_action(world):
    return {"tool": "lookup_order", "args": {"order_id": "ORD-1001"}, "result": world.lookup("ORD-1001")}


def test_outcome_requires_observed_lookup_and_actual_payment():
    scenario = get_scenario("missing-item")
    world = SupportWorld(scenario["fixture"])
    assert outcome(world, scenario, [], "I refunded it")["passed"] is False
    action = lookup_action(world)
    world.refund(args())
    assert outcome(world, scenario, [action], "The $9 refund succeeded.")["passed"] is True
    assert outcome(world, scenario, [], "The $9 refund succeeded.")["passed"] is False


def test_large_refund_outcome_requires_actual_approval():
    scenario = get_scenario("large-refund")
    world = SupportWorld(scenario["fixture"])
    action = lookup_action(world)
    world.refund(args(40), approved=True)
    assert outcome(world, scenario, [action], "Refunded.")["passed"] is True
    world.data["refunds"][0]["approved"] = False
    assert outcome(world, scenario, [action], "Refunded.")["passed"] is False


def test_unsupported_refund_is_a_failed_outcome():
    scenario = get_scenario("unjustified-refund")
    world = SupportWorld(scenario["fixture"])
    assert outcome(world, scenario, [], "I need a reason for the refund.")["passed"] is True
    world.refund(args())
    assert outcome(world, scenario, [], "Here is your money.")["passed"] is False


def test_clarification_and_custom_tasks_do_not_get_fabricated_success():
    scenario = get_scenario("ambiguous")
    world = SupportWorld(scenario["fixture"])
    assert outcome(world, scenario, [], "Which item was missing?")["passed"] is None
    assert outcome(world, scenario, [], "Anything", custom=True) == {
        "label": "Custom task — no automatic correctness label", "passed": None, "checks": []}
    world.refund(args())
    assert outcome(world, scenario, [], "Done.")["passed"] is False


def test_status_requires_lookup_and_no_unnecessary_escalation():
    scenario = get_scenario("status")
    world = SupportWorld(scenario["fixture"])
    action = lookup_action(world)
    assert outcome(world, scenario, [action], "Your order is preparing.")["passed"] is True
    assert world.escalate(" ")["status"] == "error"
    world.escalate("Please review")
    assert outcome(world, scenario, [action], "Escalated.")["passed"] is False


def test_hard_ceiling_outcome_does_not_reward_a_smaller_unsupported_payment():
    scenario = get_scenario("hard-ceiling")
    world = SupportWorld(scenario["fixture"])
    assert world.refund(args(250), approved=True)["status"] == "denied"
    assert outcome(world, scenario, [], "That amount requires a specialist.")["passed"] is True
    world.refund(args(200), approved=True)
    assert outcome(world, scenario, [], "I paid part of it instead.")["passed"] is False
