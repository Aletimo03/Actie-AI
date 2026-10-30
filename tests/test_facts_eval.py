import typing

from backend.app.agent.facts import Facts
from evals.facts import Case, load_cases, score


def test_checks_combine_expected_and_unknown_fields():
    case = Case("d", "en", expect={"domain": ["a", "b"], "role": "provider"}, unknown=["purpose"])
    assert case.checks() == {"domain": ["a", "b"], "role": ["provider"], "purpose": [None]}


def test_score_counts_checks_cases_and_errors():
    cases = [
        Case("right", "en", expect={"domain": "education"}, unknown=["role"]),
        Case("wrong", "en", expect={"domain": ["employment", "other"]}),
        Case("broken", "en", expect={"domain": "other"}),
    ]
    replies = {
        "right": Facts(domain="education"),
        "wrong": Facts(domain="education"),
        "broken": None,
    }
    result = score(replies.get, cases, runs=2)
    assert (result.checks, result.passed) == (8, 4)
    assert (result.cases, result.cases_passed, result.errors) == (6, 2, 2)
    assert result.by_field == {"domain": 4}


def test_cases_file_matches_the_schema():
    cases = load_cases()
    assert len(cases) >= 15
    fields = Facts.model_fields
    for case in cases:
        assert case.lang in ("en", "it") and case.checks()
        for name, accepted in case.checks().items():
            assert name in fields, name
            for value in accepted:  # every expected value must be one the schema allows
                Facts.model_validate({name: value})
    domains = {v for c in cases for v in c.checks().get("domain", []) if v}
    assert domains <= set(typing.get_args(fields["domain"].annotation.__args__[0]))
