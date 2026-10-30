from backend.app.agent.facts import Facts
from backend.app.agent.transparency import (
    ARTICLE_50,
    RULES,
    TransparencyCheck,
    check_transparency,
    decide,
    roles,
)
from backend.app.retrieval.contexts import Context

NO = {"applies": "no", "reason": "No."}


def yes(reason="Yes."):
    return {"applies": "yes", "reason": reason, "quote": "q"}


def check(**findings) -> TransparencyCheck:
    return TransparencyCheck(**dict.fromkeys(RULES, NO) | findings)


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def ask(self, system, user, schema):
        self.calls.append((system, user, schema))
        return self.reply


def test_roles_unknown_or_both_means_every_duty():
    assert roles("provider") == {"provider"} and roles("deployer") == {"deployer"}
    assert roles(None) == roles("provider_and_deployer") == {"provider", "deployer"}


def test_nothing_applies_means_no_duties():
    result = decide(check(), Facts(role="provider"), "en")
    assert result.duties == result.others == result.citations == result.questions == []


def test_duties_are_split_by_the_users_role():
    findings = check(interacts=yes(), deepfake=yes())  # 50(1) provider, 50(4) deployer
    provider = decide(findings, Facts(role="provider"), "en")
    assert [(d.situation, d.who) for d in provider.duties] == [("interacts", "provider")]
    assert [d.situation for d in provider.others] == ["deepfake"]

    deployer = decide(findings, Facts(role="deployer"), "en")
    assert [d.situation for d in deployer.duties] == ["deepfake"]

    unknown = decide(findings, Facts(), "en")
    assert [d.situation for d in unknown.duties] == ["interacts", "deepfake"] and not unknown.others


def test_both_paragraph_4_situations_cite_paragraph_4():
    result = decide(check(deepfake=yes(), public_interest_text=yes()), Facts(), "it")
    assert [c.chunk_id for c in result.citations] == ["it_art50_p4", "it_art50_p4"]
    assert result.duties[0].text.startswith("Rendere noto")


def test_uncertain_findings_become_questions():
    unsure = {"applies": "uncertain", "reason": "?", "question": "Is the text published?"}
    result = decide(check(public_interest_text=unsure), Facts(), "en")
    assert result.uncertain == ["public_interest_text"]
    assert result.questions == ["Is the text published?"] and result.duties == []


def test_check_transparency_reads_article_50():
    asked = []

    def fetch(ids):
        asked.append(ids)
        return [Context(i, i, "text") for i in ids]

    llm = FakeLLM(check())
    check_transparency(llm, fetch, "Un chatbot.", Facts(), "it")
    assert asked == [[f"it_{unit}" for unit in ARTICLE_50]]
    assert llm.calls[0][2] is TransparencyCheck
    assert "Write reasons and questions in Italian." in llm.calls[0][0]
