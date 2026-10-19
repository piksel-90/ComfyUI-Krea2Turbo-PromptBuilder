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


# A self-assessment by the VLM is useful for debugging, not an independent
# computer-vision validation. Only an explicit negative verdict may add a
# conservative block; absence of a verdict never means verified compliance.
_SELF_VERDICT = re.compile(
    r"(?im)^[ \t]*WYNIK_PROMPTU\s*:\s*"
    r"(ZGODNY|NIEZGODNY|NIEPEWNY|BRAK_ZAŁOŻEŃ|BRAK_ZALOZEN)"
    r"[ \t]*[.。]?[ \t]*$"
)


def evaluate_scene_contract(
    prompt_en_us: str,
    *,
    source_prompt: str = "",
    user_goal: str = "",
    scene_contract: str = "",
    analysis_pl: str = "",
    analysis_en: str = "",
    model_report_pl: str = "",
    required_exact_phrases: str = "",
    forbidden_exact_phrases: str = "",
) -> ContractStatus:
    """Combine transparent requirement tracking with literal gates + VLM report.

    The report always identifies the supplied requirements; only an explicit
    negative VLM *prompt* self-verdict or a literal violation blocks output.
    Image/source mismatch alone does not block a corrected generation prompt.
    """
    literal = evaluate_text_contract(prompt_en_us, required_exact_phrases, forbidden_exact_phrases)
    source_prompt = (source_prompt or "").strip()
    user_goal = (user_goal or "").strip()
    scene_contract = (scene_contract or "").strip()
    report = (model_report_pl or "").strip()
    has_requirements = bool(source_prompt or user_goal or scene_contract)
    verdicts = _SELF_VERDICT.findall(report)
    verdict = verdicts[-1].upper() if verdicts else None
    self_report_blocks = bool(has_requirements and verdict == "NIEZGODNY")
    ok = literal.ok and not self_report_blocks

    def brief(text: str, limit: int = 650) -> str:
        return (text[:limit].rstrip() + " … [skrócono]") if len(text) > limit else text

    parts = ["RAPORT ZGODNOŚCI SCENY — V0.1.7"]
    parts.extend((
        "ZAŁOŻENIA ŹRÓDŁOWE: " + (brief(source_prompt) if source_prompt else "Nie podano."),
        "CEL UŻYTKOWNIKA: " + (brief(user_goal) if user_goal else "Nie podano."),
        "NADRZĘDNY KONTRAKT SCENY: " + (brief(scene_contract) if scene_contract else "Nie podano."),
    ))
    if report:
        parts.extend(("OCENA MODELU (PL; nie jest niezależną walidacją obrazu):", report))
    else:
        parts.append("OCENA MODELU: Brak osobnej sekcji zgodności w odpowiedzi VLM. "
                     "Wierność oryginalnym założeniom nie została semantycznie zweryfikowana.")
        observed = (analysis_pl or analysis_en or "").strip()
        if observed:
            parts.append("ZAOBSERWOWANE W OPISIE MODELU: " + brief(observed, 450))
    if self_report_blocks:
        parts.append("BLOKADA WEDŁUG VLM: Model jawnie ocenił NOWY PROMPT jako NIEZGODNY "
                     "z podanymi wymaganiami. Jest to samoocena VLM, nie niezależny test wizji.")
    elif has_requirements and verdict == "NIEPEWNY":
        parts.append("NIEPEWNOŚĆ: Model nie potwierdził zgodności. "
                     "contract_ok dotyczy wyłącznie wykrytych naruszeń, a nie gwarantuje zgodności wizualnej.")
    elif has_requirements and not verdict:
        parts.append("BRAK WERDYKTU: Model nie podał rozpoznawalnej linii WYNIK_PROMPTU. "
                     "Nie można automatycznie potwierdzić zgodności semantycznej.")
    parts.append("KONTROLA LITERALNA: " + literal.report_pl)
    parts.append("OGRANICZENIE: raport modelu nie ma niezależnego potwierdzenia zgodności ze sceną; "
                 "sprawdzanie dosłownych fraz nie wykrywa zmian znaczenia ani synonimów.")
    return ContractStatus(ok, "\n\n".join(parts))
