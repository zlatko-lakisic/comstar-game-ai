"""Doctrine document triage stub."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DoctrineDestination(str, Enum):
    RULES = "rules"  # deterministic layer, zero prompt cost
    SKILL = "skill"  # always-on injected doctrine
    RAG = "rag"  # situational retrieval corpus


@dataclass
class DoctrineSection:
    title: str
    body: str
    destination: DoctrineDestination
    tags: list[str] = field(default_factory=list)
    game_version: str | None = None
    mod: str = "vanilla"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "destination": self.destination.value,
            "tags": self.tags,
            "game_version": self.game_version,
            "mod": self.mod,
        }


_RULE_PATTERNS = (
    re.compile(r"\b\d+\s*%|\btable\b|\bmodifier\b|\bformula\b", re.I),
    re.compile(r"\bcounter[s]?\b|\bterrain\b.*\b(bonus|penalty)\b", re.I),
)
_SKILL_PATTERNS = (
    re.compile(r"\balways\b|\bdefault\b|\bcore doctrine\b", re.I),
    re.compile(r"\bhold\b|\bpreserve\b|\bnever\b", re.I),
)


def _classify_section(title: str, body: str) -> DoctrineDestination:
    text = f"{title}\n{body}"
    if any(p.search(text) for p in _RULE_PATTERNS):
        return DoctrineDestination.RULES
    if any(p.search(text) for p in _SKILL_PATTERNS) and len(body) < 800:
        return DoctrineDestination.SKILL
    return DoctrineDestination.RAG


def triage_document(
    text: str,
    *,
    title: str = "document",
    game_version: str | None = None,
    mod: str = "vanilla",
) -> list[DoctrineSection]:
    """Split markdown-ish text into sections and assign destinations."""
    chunks = re.split(r"\n(?=#{1,3}\s)", text.strip())
    if len(chunks) <= 1 and not text.strip().startswith("#"):
        chunks = [text]

    sections: list[DoctrineSection] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        sec_title = title
        body = chunk
        if lines and lines[0].startswith("#"):
            sec_title = lines[0].lstrip("#").strip() or title
            body = "\n".join(lines[1:]).strip() or chunk
        dest = _classify_section(sec_title, body)
        sections.append(
            DoctrineSection(
                title=sec_title,
                body=body,
                destination=dest,
                tags=[dest.value],
                game_version=game_version,
                mod=mod,
            )
        )
    return sections


def triage_summary(sections: list[DoctrineSection]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sec in sections:
        key = sec.destination.value
        counts[key] = counts.get(key, 0) + 1
    return counts
