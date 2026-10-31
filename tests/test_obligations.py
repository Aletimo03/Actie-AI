from datetime import date

from backend.app.agent.obligations import HIGH_RISK, decide_obligations
from backend.app.agent.transparency import Duty

TODAY = date(2026, 10, 30)
CV = ["en_annex3_4_a"]
CREDIT = ["it_annex3_5_b"]
GRID = ["en_annex3_2"]
TOY = ["en_art6_p1"]


def ids(result):
    return [o.chunk_id for o in result.obligations]


def test_a_minimal_risk_system_only_owes_ai_literacy_already_in_force():
    result = decide_obligations("deployer", [], [], "en", TODAY)
    [literacy] = result.obligations
    assert (literacy.chunk_id, literacy.who, literacy.in_force) == ("en_art4_p1", "deployer", True)
    assert [c.chunk_id for c in result.citations] == ["en_art113_a"] and result.notes == []


def test_an_annex_iii_provider_gets_every_provider_duty_from_december_2027():
    result = decide_obligations("provider", CV, [], "en", TODAY)
    providers = [f"en_{r.unit}" for r in HIGH_RISK if r.who == "provider"]
    assert ids(result) == ["en_art4_p1", *providers]
    high_risk = result.obligations[1:]
    assert {(o.applies_from, o.in_force) for o in high_risk} == {(date(2027, 12, 2), False)}
    assert "en_art113_c_i" in [c.chunk_id for c in result.citations]
    assert len(result.notes) == 2  # the aligned dates and the legacy rule


def test_an_annex_i_product_waits_until_august_2028():
    result = decide_obligations("provider", TOY, [], "en", TODAY)
    assert result.obligations[1].applies_from == date(2028, 8, 2)
    assert "en_art49_p1" not in ids(result)  # registration is for Annex III systems


def test_a_deployer_sees_conditions_it_must_check_itself():
    result = decide_obligations("deployer", CV, [], "en", TODAY)
    conditions = {o.chunk_id: o.condition for o in result.obligations if o.condition}
    assert set(conditions) == {"en_art26_p7", "en_art27_p1", "en_art49_p3"}
    assert conditions["en_art26_p7"].startswith("where the system is used at the workplace")
    assert "en_art9_p1" not in ids(result)


def test_credit_scoring_always_needs_a_fundamental_rights_assessment():
    result = decide_obligations("deployer", CREDIT, [], "it", TODAY)
    [fria] = [o for o in result.obligations if o.chunk_id == "it_art27_p1"]
    assert fria.condition is None and fria.text.startswith("Effettuare una valutazione")


def test_critical_infrastructure_is_left_out_of_registration_and_the_assessment():
    assert not {"en_art49_p1", "en_art49_p3", "en_art27_p1", "en_art26_p11"} & set(
        ids(decide_obligations(None, GRID, [], "en", TODAY))
    )


def test_an_unknown_role_lists_both_roles_duties():
    result = decide_obligations(None, CV, [], "en", TODAY)
    assert {o.who for o in result.obligations} == {"provider", "deployer"}
    assert ids(result)[:2] == ["en_art4_p1", "en_art4_p1"]


def test_transparency_duties_are_dated_and_existing_generators_get_the_grace_period():
    marking = Duty("synthetic_content", "en_art50_p2", "provider", "Mark the outputs.")
    result = decide_obligations("provider", [], [marking], "en", TODAY)
    duty = result.obligations[-1]
    assert (duty.chunk_id, duty.applies_from, duty.in_force) == (
        "en_art50_p2",
        date(2026, 8, 2),
        True,
    )
    assert "en_art113" in [c.chunk_id for c in result.citations]
    assert any("2 December 2026" in note for note in result.notes)
