"""Sixth agent step: the user's obligations, each with the date it applies from.

Once the risk level, the role and the Annex point are known, the duties are
fixed by the law, so this step is a table read by code, with no LLM call:
the same system always gets the same list. Each duty points to its article;
verify_citations checks that every one exists in the current text.

Dates (Art. 113, as amended by the Digital Omnibus):
- Art. 4 (AI literacy, Chapter I): from 2 February 2025;
- Art. 50 (transparency): from 2 August 2026; 50(2) for systems already on
  the market by then: 2 December 2026 (Art. 111(4));
- high-risk duties (Chapter III, Sections 1-3): 2 December 2027 for Annex III
  systems, 2 August 2028 for Annex I products (Art. 113(c)).
Read literally, Art. 113 dates Arts. 43, 47-49 and 72-73 (outside Sections
1-3) from 2 August 2026, but they assume a system that is high-risk under
Chapter III. They get the same date as the other high-risk duties, and the
report says so in a note.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from backend.app.agent.prohibited import Citation
from backend.app.agent.transparency import Duty, roles

Who = Literal["provider", "deployer"]
# When a duty applies beyond the risk level and the role: decided by code from the
# Annex III point, or left to the user as a condition shown next to the duty.
When = Literal["always", "annex_iii", "fria", "public_body", "employer"]


@dataclass(frozen=True)
class Rule:
    unit: str
    who: Who
    text: dict[str, str]
    when: When = "always"


AI_LITERACY = Rule(
    "art4_p1",
    "provider",  # and deployer: see decide_obligations
    {
        "en": "Make sure your staff who operate or use AI systems have sufficient AI literacy.",
        "it": "Garantire che il personale che gestisce o usa sistemi di IA abbia un livello "
        "sufficiente di alfabetizzazione in materia di IA.",
    },
)

HIGH_RISK = [
    Rule("art9_p1", "provider", {
        "en": "Set up and maintain a risk management system for the whole lifecycle.",
        "it": "Istituire e mantenere un sistema di gestione dei rischi per l'intero ciclo di vita.",
    }),
    Rule("art10_p1", "provider", {
        "en": "Train, validate and test on data sets that meet the quality criteria.",
        "it": "Addestrare, convalidare e testare su dati che rispettano i criteri di qualità.",
    }),
    Rule("art11_p1", "provider", {
        "en": "Draw up the technical documentation before placing it on the market.",
        "it": "Redigere la documentazione tecnica prima dell'immissione sul mercato.",
    }),
    Rule("art12_p1", "provider", {
        "en": "Make the system record events (logs) automatically over its lifetime.",
        "it": "Fare in modo che il sistema registri automaticamente gli eventi (log).",
    }),
    Rule("art13_p1", "provider", {
        "en": "Make it transparent enough for deployers, with instructions for use.",
        "it": "Renderlo sufficientemente trasparente per i deployer, con istruzioni per l'uso.",
    }),
    Rule("art14_p1", "provider", {
        "en": "Design it so that people can oversee it effectively while it is in use.",
        "it": "Progettarlo in modo che possa essere sorvegliato efficacemente da persone fisiche.",
    }),
    Rule("art15_p1", "provider", {
        "en": "Achieve appropriate accuracy, robustness and cybersecurity.",
        "it": "Garantire un livello adeguato di accuratezza, robustezza e cibersicurezza.",
    }),
    Rule("art17_p1", "provider", {
        "en": "Put a documented quality management system in place.",
        "it": "Istituire un sistema documentato di gestione della qualità.",
    }),
    Rule("art43_p1", "provider", {
        "en": "Complete the conformity assessment before placing it on the market.",
        "it": "Completare la valutazione della conformità prima dell'immissione sul mercato.",
    }),
    Rule("art47_p1", "provider", {
        "en": "Draw up the EU declaration of conformity and keep it for 10 years.",
        "it": "Redigere la dichiarazione di conformità UE e conservarla per 10 anni.",
    }),
    Rule("art48_p1", "provider", {
        "en": "Affix the CE marking.",
        "it": "Apporre la marcatura CE.",
    }),
    Rule("art49_p1", "provider", {
        "en": "Register the system in the EU database before placing it on the market.",
        "it": "Registrare il sistema nella banca dati dell'UE prima dell'immissione sul mercato.",
    }, "annex_iii"),
    Rule("art72_p1", "provider", {
        "en": "Set up and document post-market monitoring.",
        "it": "Istituire e documentare un sistema di monitoraggio successivo all'immissione "
        "sul mercato.",
    }),
    Rule("art73_p1", "provider", {
        "en": "Report serious incidents to the market surveillance authorities.",
        "it": "Segnalare gli incidenti gravi alle autorità di vigilanza del mercato.",
    }),
    Rule("art26_p1", "deployer", {
        "en": "Use the system according to the provider's instructions for use.",
        "it": "Usare il sistema conformemente alle istruzioni per l'uso del fornitore.",
    }),
    Rule("art26_p2", "deployer", {
        "en": "Assign human oversight to competent, trained people with authority.",
        "it": "Affidare la sorveglianza umana a persone competenti, formate e con autorità.",
    }),
    Rule("art26_p4", "deployer", {
        "en": "Make sure the input data you control is relevant and representative.",
        "it": "Garantire che i dati di input sotto il vostro controllo siano pertinenti e "
        "rappresentativi.",
    }),
    Rule("art26_p5", "deployer", {
        "en": "Monitor its operation and inform the provider of risks and serious incidents.",
        "it": "Monitorarne il funzionamento e informare il fornitore di rischi e incidenti gravi.",
    }),
    Rule("art26_p6", "deployer", {
        "en": "Keep the logs under your control for at least six months.",
        "it": "Conservare i log sotto il vostro controllo per almeno sei mesi.",
    }),
    Rule("art26_p11", "deployer", {
        "en": "Tell the people it makes or assists decisions about that it is used on them.",
        "it": "Informare le persone interessate dalle decisioni che il sistema è usato nei "
        "loro confronti.",
    }, "annex_iii"),
    Rule("art26_p7", "deployer", {
        "en": "Inform workers' representatives and the affected workers before using it.",
        "it": "Informare i rappresentanti dei lavoratori e i lavoratori interessati prima "
        "dell'uso.",
    }, "employer"),
    Rule("art27_p1", "deployer", {
        "en": "Carry out a fundamental rights impact assessment before first use.",
        "it": "Effettuare una valutazione d'impatto sui diritti fondamentali prima del primo uso.",
    }, "fria"),
    Rule("art49_p3", "deployer", {
        "en": "Register your use of the system in the EU database before using it.",
        "it": "Registrare l'uso del sistema nella banca dati dell'UE prima di usarlo.",
    }, "public_body"),
]  # fmt: skip

CONDITIONS = {
    "employer": {
        "en": "if you use it at the workplace as an employer",
        "it": "se lo usate sul luogo di lavoro come datore di lavoro",
    },
    "public_body": {
        "en": "if you are a public authority or act on its behalf",
        "it": "se siete un'autorità pubblica o agite per suo conto",
    },
    "fria": {
        "en": "if you are a public body or a private entity providing public services",
        "it": "se siete un ente pubblico o un ente privato che fornisce servizi pubblici",
    },
}

# Where each date comes from: (chunk, the words that set it, per language).
SOURCES = {
    "ai_literacy": (
        "art113_a",
        date(2025, 2, 2),
        {
            "en": "Chapters I and II shall apply from 2 February 2025",
            "it": "I capi I e II si applicano a decorrere dal 2 febbraio 2025",
        },
    ),
    "transparency": (
        "art113",
        date(2026, 8, 2),
        {
            "en": "It shall apply from 2 August 2026",
            "it": "Si applica a decorrere dal 2 agosto 2026",
        },
    ),
    "annex_iii": (
        "art113_c_i",
        date(2027, 12, 2),
        {
            "en": "2 December 2027 as regards AI systems classified as high-risk pursuant to "
            "Article 6(2) and Annex III",
            "it": "2 dicembre 2027 per quanto riguarda i sistemi di IA classificati come ad "
            "alto rischio ai sensi dell'articolo 6, paragrafo 2, e dell'allegato III",
        },
    ),
    "annex_i": (
        "art113_c_ii",
        date(2028, 8, 2),
        {
            "en": "2 August 2028 as regards AI systems classified as high-risk pursuant to "
            "Article 6(1) and Annex I",
            "it": "2 agosto 2028 per quanto riguarda i sistemi di IA classificati come ad alto "
            "rischio ai sensi dell'articolo 6, paragrafo 1, e dell'allegato I",
        },
    ),
}
CLAIMS = {
    "ai_literacy": {
        "en": "AI literacy (Art. 4) applies from 2 February 2025.",
        "it": "L'alfabetizzazione in materia di IA (art. 4) si applica dal 2 febbraio 2025.",
    },
    "transparency": {
        "en": "The transparency duties (Art. 50) apply from 2 August 2026.",
        "it": "Gli obblighi di trasparenza (art. 50) si applicano dal 2 agosto 2026.",
    },
    "annex_iii": {
        "en": "The high-risk duties apply from 2 December 2027 for Annex III systems.",
        "it": "Gli obblighi per l'alto rischio si applicano dal 2 dicembre 2027 per i sistemi "
        "dell'allegato III.",
    },
    "annex_i": {
        "en": "The high-risk duties apply from 2 August 2028 for Annex I products.",
        "it": "Gli obblighi per l'alto rischio si applicano dal 2 agosto 2028 per i prodotti "
        "dell'allegato I.",
    },
}
NOTES = {
    "aligned": {
        "en": "Art. 113 dates Arts. 43, 47-49 and 72-73 from 2 August 2026, but they apply "
        "to systems that are high-risk under Chapter III, so they are shown with its date.",
        "it": "L'art. 113 fa decorrere gli artt. 43, 47-49 e 72-73 dal 2 agosto 2026, ma "
        "riguardano sistemi ad alto rischio ai sensi del capo III, quindi sono indicati con "
        "la sua data.",
    },
    "legacy": {
        "en": "A high-risk system already on the market before that date is covered only "
        "if its design changes significantly afterwards; systems used by public "
        "authorities must comply by 2 August 2030 in any case (Art. 111(2)).",
        "it": "Un sistema ad alto rischio già sul mercato prima di tale data è soggetto solo "
        "se in seguito il suo progetto cambia in modo significativo; i sistemi usati da "
        "autorità pubbliche devono conformarsi in ogni caso entro il 2 agosto 2030 "
        "(art. 111, paragrafo 2).",
    },
    "existing_generator": {
        "en": "If your generator was on the market before 2 August 2026, the marking duty "
        "of Art. 50(2) applies from 2 December 2026 (Art. 111(4)).",
        "it": "Se il vostro generatore era sul mercato prima del 2 agosto 2026, l'obbligo di "
        "marcatura dell'art. 50, paragrafo 2, si applica dal 2 dicembre 2026 "
        "(art. 111, paragrafo 4).",
    },
}


@dataclass
class Obligation:
    chunk_id: str
    who: Who
    text: str
    applies_from: date
    in_force: bool  # already applies on the day of the assessment
    condition: str | None = None  # a fact the user must check, when code can't decide it
    verified: bool = False  # the article exists in the current text (set by verify_citations)


@dataclass
class ObligationsResult:
    obligations: list[Obligation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)  # the provisions setting the dates
    uncertain: list[str] = field(default_factory=list)  # never: every rule is decided by code


def high_risk_source(basis: list[str]) -> str:
    """Annex III's earlier date wins when a system is both."""
    return "annex_iii" if any("_annex3" in point for point in basis) else "annex_i"


def needs_fria(basis: list[str], lang: str) -> bool:
    """Art. 27(1): always for credit scoring and life/health insurance (Annex III 5(b), (c))."""
    return any(point in (f"{lang}_annex3_5_b", f"{lang}_annex3_5_c") for point in basis)


def applies(rule: Rule, basis: list[str], lang: str) -> tuple[bool, str | None]:
    """(whether the rule applies, the condition to show if code can't decide)."""
    annex_iii = [p for p in basis if "_annex3" in p]
    critical_infrastructure = all(p.startswith(f"{lang}_annex3_2") for p in annex_iii)
    if rule.when == "annex_iii":
        return bool(annex_iii) and not critical_infrastructure, None
    if rule.when in ("fria", "public_body"):
        if not annex_iii or critical_infrastructure:  # 27(1) and 49(3) leave out Annex III point 2
            return False, None
        if rule.when == "fria" and needs_fria(basis, lang):
            return True, None
        return True, CONDITIONS[rule.when][lang]
    if rule.when == "employer":
        return True, CONDITIONS["employer"][lang]
    return True, None


def decide_obligations(
    role: str | None,
    high_risk_basis: list[str],
    duties: list[Duty],
    lang: str,
    today: date,
) -> ObligationsResult:
    result = ObligationsResult()
    mine = roles(role)
    used: list[str] = []

    def add(rule_unit: str, who: Who, text: str, source: str, condition=None) -> None:
        start = SOURCES[source][1]
        result.obligations.append(
            Obligation(f"{lang}_{rule_unit}", who, text, start, start <= today, condition)
        )
        if source not in used:
            used.append(source)

    for who in sorted(mine):
        add(AI_LITERACY.unit, who, AI_LITERACY.text[lang], "ai_literacy")
    if high_risk_basis:
        source = high_risk_source(high_risk_basis)
        for rule in HIGH_RISK:
            ok, condition = applies(rule, high_risk_basis, lang)
            if rule.who in mine and ok:
                add(rule.unit, rule.who, rule.text[lang], source, condition)
        result.notes += [NOTES["aligned"][lang], NOTES["legacy"][lang]]
    for duty in duties:
        add(duty.chunk_id.removeprefix(f"{lang}_"), duty.who, duty.text, "transparency")
        if duty.situation == "synthetic_content":
            result.notes.append(NOTES["existing_generator"][lang])

    for source in used:
        unit, _, quote = SOURCES[source]
        claim = CLAIMS[source][lang]
        result.citations.append(Citation(chunk_id=f"{lang}_{unit}", quote=quote[lang], claim=claim))
    return result
