"""Which chunks a search may return: the current version, one language, and optionally
a part of the Act (e.g. only Article 5, or Article 6 and Annex III) or only binding text.

The agent will scope each step: check_prohibited searches Article 5 only, which keeps
explanatory recitals and unrelated articles out of its results.
"""

from dataclasses import dataclass, field

CURRENT_VERSION = "(SELECT version FROM versions WHERE is_current)"


@dataclass
class Scope:
    lang: str
    articles: list[str] = field(default_factory=list)  # ["5"], ["6", "113"]
    annexes: list[str] = field(default_factory=list)  # ["III"]
    binding_only: bool = False  # leave out recitals

    def where(self) -> tuple[str, dict]:
        """SQL conditions on the chunks table, and their parameters."""
        sql = [f"version = {CURRENT_VERSION}", "lang = %(scope_lang)s"]
        params: dict = {"scope_lang": self.lang}
        if self.articles or self.annexes:
            sql.append("(article = ANY(%(scope_articles)s) OR annex = ANY(%(scope_annexes)s))")
            params |= {"scope_articles": self.articles, "scope_annexes": self.annexes}
        if self.binding_only:
            sql.append("binding")
        return " AND ".join(sql), params
