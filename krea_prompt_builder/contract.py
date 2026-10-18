"""Deterministic text-only guardrails; this is NOT an independent visual evaluator.

The source project's evaluation idea is adapted to a single-image workflow:
user requirements stay separate from VLM suggestions. Only user-entered exact
textual anchors are checked; vision-dependent scene truth remains unverified.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


def parse_phrases(text: str) -> tuple[str, ...]:
    """Each nonempty line is a literal case-insensitive phrase to check in prompt text."""
    phrases = []
    for line in (text or "").splitlines():
        normalized = " ".join(line.strip().split())
        if normalized and normalized.casefold() not in {p.casefold() for p in phrases}:
            phrases.append(normalized[:200])
    if len(phrases) > 40:
        raise ValueError("Too many scene-contract phrases (maximum 40 per field)")
    return tuple(phrases)


def normalized_for_matching(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


@dataclass(frozen=True)
class ContractStatus:
    ok: bool
    report_pl: str


def evaluate_text_contract(prompt_en_us: str, required: str = "", forbidden: str = "") -> ContractStatus:
    """Validate only explicit substrings, not scene semantics or image fidelity."""
    normalized = normalized_for_matching(prompt_en_us)
    needed = parse_phrases(required)
    banned = parse_phrases(forbidden)
    missing = [x for x in needed if normalized_for_matching(x) not in normalized]
    present = [x for x in banned if normalized_for_matching(x) in normalized]
    if missing or present:
        messages = ["BLOKADA: prompt narusza jawne ograniczenia tekstowe."]
        if missing:
            messages.append("Brak wymaganych dosłownych fraz: " + "; ".join(missing))
        if present:
            messages.append("Znaleziono zabronione dosłowne frazy: " + "; ".join(present))
        messages.append("To kontrola literalnych słów, nie niezależna ocena obrazu. Prompt został zablokowany.")
        return ContractStatus(False, "\n".join(messages))
    if needed or banned:
        return ContractStatus(True, "OK: jawne warunki tekstowe spełnione. Wierność wizualna i nieoczekiwane synonimy NIE zostały zweryfikowane.")
    return ContractStatus(True, "BRAK REGUŁ LITERALNYCH: wynik nie ma niezależnego potwierdzenia zgodności ze sceną.")
