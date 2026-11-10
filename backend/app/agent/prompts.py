"""What the three legal checks send the model: the description, the facts, the law.

Article 5, Article 6 and Article 50 are read the same way, so the prompt lives once.
The description is untrusted text, kept inside <description> tags (see facts.py).
"""

from backend.app.agent.facts import Facts
from backend.app.law import Context

LANGUAGES = {"en": "English", "it": "Italian"}


def check_prompt(
    description: str, facts: Facts, law: list[Context], heading: str = "Article text"
) -> str:
    text = "\n\n".join(f"{c.header}\n{c.text}" for c in law)
    return (
        f"<description>\n{description.strip()}\n</description>\n\n"
        f"Facts:\n{facts.model_dump_json(exclude_none=True)}\n\n"
        f"{heading}:\n{text}"
    )
