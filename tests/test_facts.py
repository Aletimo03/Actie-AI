from backend.app.agent.facts import SYSTEM, Facts, build_prompt, extract_facts, missing_facts

COMPLETE = dict(
    summary="Ranks job applicants",
    purpose="Shortlist candidates",
    domain="employment",
    affected_people="job applicants",
    role="deployer",
)


class FakeLLM:
    """Records the prompts and returns a fixed reply."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def ask(self, system, user, schema):
        self.calls.append((system, user, schema))
        return self.reply


def test_extract_facts_sends_the_description_as_data():
    facts = Facts(**COMPLETE)
    llm = FakeLLM(facts)
    assert extract_facts(llm, "  A tool that ranks CVs.  ") is facts
    system, user, schema = llm.calls[0]
    assert system == SYSTEM and schema is Facts
    assert user == "<description>\nA tool that ranks CVs.\n</description>"


def test_answers_are_added_to_the_prompt():
    prompt = build_prompt("A tool that ranks CVs.", {"Who uses it?": "Our HR team"})
    assert prompt.endswith("follow-up questions:\n- Who uses it?: Our HR team")


def test_unknown_facts_default_to_none():
    facts = Facts()
    assert facts.domain is None and facts.uses_biometrics is None


def test_null_strings_become_none():
    facts = Facts.model_validate_json('{"summary": "null", "purpose": " ", "role": "unknown"}')
    assert facts.summary is None and facts.purpose is None and facts.role is None


def test_missing_facts_lists_required_gaps_in_order():
    assert missing_facts(Facts(summary="Something")) == [
        "purpose",
        "domain",
        "affected_people",
        "role",
    ]
    assert missing_facts(Facts(**COMPLETE)) == []


def test_real_time_is_asked_only_for_biometric_systems():
    assert missing_facts(Facts(**COMPLETE, uses_biometrics=True)) == ["real_time"]
    assert missing_facts(Facts(**COMPLETE, uses_biometrics=True, real_time=False)) == []
    assert missing_facts(Facts(**COMPLETE, uses_biometrics=False)) == []
