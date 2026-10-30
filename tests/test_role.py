from backend.app.agent.facts import Facts
from backend.app.agent.role import ARTICLE_25, decide_role

DEPLOYER = Facts(
    role="deployer", rebranded=False, substantially_modified=False, changed_purpose=False
)


def test_a_deployer_who_changed_nothing_stays_a_deployer():
    result = decide_role(DEPLOYER, is_high_risk=True, lang="en")
    assert (result.role, result.became_provider, result.uncertain) == ("deployer", [], [])


def test_each_article_25_circumstance_makes_the_deployer_a_provider():
    for label, (fact, _) in ARTICLE_25.items():
        facts = DEPLOYER.model_copy(update={fact: True})
        result = decide_role(facts, is_high_risk=True, lang="it")
        assert (result.role, result.became_provider) == ("provider_and_deployer", [label])
        [citation] = result.citations
        assert citation.chunk_id == f"it_art25_p1_{label}"
        assert citation.claim.startswith("Ai sensi dell'articolo 25")


def test_an_unknown_circumstance_is_asked_once_in_the_users_language():
    facts = DEPLOYER.model_copy(update={"rebranded": None, "changed_purpose": None})
    result = decide_role(facts, is_high_risk=True, lang="it")
    assert result.uncertain == ["art25"] and result.questions[0].startswith("Avete apposto")


def test_article_25_matters_only_for_deployers_of_high_risk_systems():
    unknown = Facts(role="deployer")
    assert decide_role(unknown, is_high_risk=False, lang="en").uncertain == []
    for role in ("provider", "provider_and_deployer", None):
        result = decide_role(Facts(role=role), is_high_risk=True, lang="en")
        assert (result.role, result.uncertain) == (role, [])
