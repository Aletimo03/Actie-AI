"""Fifth agent step: the user's role, after Article 25.

The facts step reads the stated role (built it -> provider, uses it ->
deployer). Article 25(1) can change it: a deployer of a high-risk system who
puts their own name on it (a), substantially modifies it (b) or changes its
intended purpose so that it becomes high-risk (c) is its provider, with the
provider's duties. The facts step reads the three circumstances; code applies
the article, with no LLM call. It only matters for a deployer of a high-risk
system, so only that user is asked, in one question for all three.

The citations quote the points themselves, written here; verify_citations
checks them against the current text on every run.
"""

from dataclasses import dataclass, field

from backend.app.agent.facts import Facts
from backend.app.agent.prohibited import Citation

# Article 25(1) point -> (the fact that triggers it, the words of the point per language)
ARTICLE_25 = {
    "a": (
        "rebranded",
        {
            "en": "they put their name or trademark on a high-risk AI system",
            "it": "se appone il proprio nome o marchio su un sistema di IA ad alto rischio",
        },
    ),
    "b": (
        "substantially_modified",
        {
            "en": "they make a substantial modification to a high-risk AI system",
            "it": "se apporta una modifica sostanziale a un sistema di IA ad alto rischio",
        },
    ),
    "c": (
        "changed_purpose",
        {
            "en": "they modify the intended purpose of an AI system",
            "it": "se modifica la finalità prevista di un sistema di IA",
        },
    ),
}
CLAIMS = {
    "en": "Under Article 25(1)({label}) you are the provider of this high-risk system.",
    "it": "Ai sensi dell'articolo 25, paragrafo 1, lettera {label}), siete il fornitore di "
    "questo sistema ad alto rischio.",
}
QUESTION = {
    "en": "Did you put your own name or trademark on the system, make substantial changes "
    "to it, or change what it is used for?",
    "it": "Avete apposto il vostro nome o marchio sul sistema, l'avete modificato in modo "
    "sostanziale, o ne avete cambiato la finalità?",
}


@dataclass
class RoleResult:
    role: str | None  # provider | deployer | provider_and_deployer | None (unknown)
    became_provider: list[str] = field(default_factory=list)  # Art. 25(1) points that apply
    uncertain: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)


def decide_role(facts: Facts, is_high_risk: bool, lang: str) -> RoleResult:
    result = RoleResult(facts.role)
    if facts.role != "deployer" or not is_high_risk:
        return result
    for label, (fact, quote) in ARTICLE_25.items():
        if getattr(facts, fact):
            result.became_provider.append(label)
            result.citations.append(
                Citation(
                    chunk_id=f"{lang}_art25_p1_{label}",
                    quote=quote[lang],
                    claim=CLAIMS[lang].format(label=label),
                )
            )
    if result.became_provider:
        result.role = "provider_and_deployer"  # they still use it, now also as its provider
    elif any(getattr(facts, fact) is None for fact, _ in ARTICLE_25.values()):
        result.uncertain.append("art25")
        result.questions.append(QUESTION[lang])
    return result
