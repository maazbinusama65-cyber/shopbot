"""Deterministic safety checks that run before the LLM sees anything."""
import re

INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts?|rules)",
    r"disregard (all |any |the )?(previous|prior|above|earlier|your) (instructions|prompts?|rules)",
    r"(reveal|show|print|repeat|leak|tell me) (me )?(your|the) (system|hidden|initial|original) (prompt|instructions|message)",
    r"what (is|are) your (system|hidden|initial) (prompt|instructions)",
    r"you are now\b", r"\bact as (an? )?(unrestricted|jailbroken|dan)\b",
    r"\bdeveloper mode\b", r"\bjailbreak\b", r"\bdan mode\b",
    r"pretend (that )?(you have|there are) no (rules|restrictions|limits)",
    r"override (your|the) (safety|rules|instructions|policy)",
    r"<\s*/?\s*system\s*>", r"\[\s*system\s*\]",
    r"(show|dump|list|give me) (me )?(all )?(other|another|every) (users?|customers?)['’]?s?\b",
    r"(api[ _-]?key|admin[ _-]?token|password|secret)s?\b.*\b(show|reveal|give|print|tell)",
    r"\b(show|reveal|give|print|tell)\b.*\b(api[ _-]?key|admin[ _-]?token|secret key)\b",
]
_INJ = [re.compile(p, re.I) for p in INJECTION_PATTERNS]

REFUSAL_INJECTION = ("I can't help with that. I'm the Loom & Leaf shopping assistant, so I can only "
                     "help with our products, prices, policies and your own orders. "
                     "What would you like to shop for?")

# Whole-message match: "yes but make it two" must NOT confirm the stored proposal.
_YES = re.compile(r"^\s*(yes|y|yeah|yep|yup|confirm(ed)?|ok(ay)?|sure|go ahead|place (it|the order)|do it|"
                  r"please do|proceed)(,? (please|thanks|thank you))?[\s.!]*$", re.I)
_NO = re.compile(r"^\s*(no|n|nope|cancel|stop|don'?t|do not|never ?mind|abort)\b", re.I)


def is_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJ)


def is_confirmation(text: str) -> bool:
    return bool(_YES.match(text)) and len(text) < 80


def is_rejection(text: str) -> bool:
    return bool(_NO.match(text)) and len(text) < 80


_PERSONAL_HINT = re.compile(
    r"\b(i am|i'm|im|my|i prefer|i like|i love|i hate|i don'?t like|i wear|budget|allerg|size|i live|"
    r"i moved|call me|name is)\b", re.I)


def may_contain_personal_fact(text: str) -> bool:
    """Cheap gate so we only pay for a memory-extraction LLM call when it could matter."""
    return bool(_PERSONAL_HINT.search(text))
