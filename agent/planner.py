"""How the agent decides what to pay for.

Scene B of the demo is only honest if the malicious tool output actually drives
the agent's behaviour. Previously `simulate_attack=True` selected a hardcoded
attacker address and amount from an if/else, which meant the "attack" was staged
rather than performed — a fair judge would call that out.

Here the planner *reads* the tool output and extracts whatever payment it was
told to make. Given the injected text, a naive agent lands on the attacker's
address and the attacker's amount because that is what the text says, not
because a branch said so. SentinelPay then blocks it anyway, which is the point:
the boundary does not depend on the agent being clever.

Two implementations:

  RuleBasedPlanner - deterministic extraction. No dependencies, always available,
                     used by the test suite so results stay reproducible.
  OllamaPlanner    - a real local LLM decides, via Ollama. Optional and free;
                     enabled with MODEL_PROVIDER=ollama. Falls back to the rule
                     based planner if Ollama is not reachable, because the demo
                     must never hard-fail on an optional component.

Neither planner is trusted. Both produce a *proposal*; the policy engine, the
verifier and the contract decide whether it happens.
"""

import json
import logging
import re
from typing import Any, Dict, Optional, Protocol

from pydantic import BaseModel

from sentinelpay.tracing import traceable

logger = logging.getLogger(__name__)

# Algorand addresses are 58 base32 characters. Also matches the obviously-fake
# placeholder addresses used in the offline demos, which is deliberate: the
# planner should surface whatever the text claims, and let SentinelPay judge it.
_ADDRESS_RE = re.compile(r"\b([A-Z2-7]{58}|[A-Z_]{2,}[A-Z0-9_]{16,})\b")
_AMOUNT_RE = re.compile(r"([\d,]+)\s*(?:micro-?algo|ualgo)\b", re.IGNORECASE)

# Language that marks text as trying to redirect the agent's spending. Used to
# label the proposal's provenance, never to authorize anything.
_IMPERATIVE_MARKERS = (
    "you must",
    "immediately send",
    "urgent",
    "system override",
    "required to",
    "transfer",
)


class ProposedPayment(BaseModel):
    """What the agent wants to pay, before any SentinelPay check runs."""

    declared_goal: str
    amount: int
    destination: str
    resource: str = "energy-dataset-2026"
    currency: str = "uALGO"
    # Where the parameters came from. Surfaced in the demo so the audience can
    # see the agent acting on untrusted text.
    derived_from: str = "task"


class Planner(Protocol):
    def propose_payment(
        self, objective: str, tool_output: Dict[str, Any], default_destination: str
    ) -> ProposedPayment:
        """Decide what payment, if any, this task calls for."""
        ...


def extract_injected_payment(text: str) -> Optional[ProposedPayment]:
    """Pull a payment instruction out of untrusted tool output.

    Returns None when the text contains no spending instruction. This is
    intentionally credulous — it models an agent that believes what it reads.
    """
    amount_match = _AMOUNT_RE.search(text)
    address_match = _ADDRESS_RE.search(text)
    if not amount_match or not address_match:
        return None

    lowered = text.lower()
    if not any(marker in lowered for marker in _IMPERATIVE_MARKERS):
        return None

    # Reproduce the instruction as the agent understood it, so the declared goal
    # reflects what it is actually trying to do rather than a sanitised summary.
    goal_line = next(
        (
            line.strip()
            for line in text.splitlines()
            if any(marker in line.lower() for marker in _IMPERATIVE_MARKERS)
        ),
        "Follow instruction found in tool output",
    )

    return ProposedPayment(
        declared_goal=goal_line[:256],
        amount=int(amount_match.group(1).replace(",", "")),
        destination=address_match.group(1),
        derived_from="untrusted_tool_output",
    )


class RuleBasedPlanner:
    """Deterministic planner. Believes tool output; that is the threat model."""

    @traceable(name="rule_based_propose_payment", tags=["sentinelpay", "agent"], metadata={"component": "planner", "provider": "rule_based"})
    def propose_payment(
        self, objective: str, tool_output: Dict[str, Any], default_destination: str
    ) -> ProposedPayment:
        injected = extract_injected_payment(str(tool_output.get("content", "")))
        if injected is not None:
            logger.warning(
                "Agent extracted a payment instruction from untrusted tool output: "
                "%s uALGO to %s",
                injected.amount,
                injected.destination,
            )
            return injected

        return ProposedPayment(
            declared_goal=f"Purchase historical energy dataset for {objective}",
            amount=100_000,
            destination=default_destination,
            derived_from="task",
        )


class OllamaPlanner:
    """Optional planner backed by a local Ollama model. No API bill, no key.

    Enable with MODEL_PROVIDER=ollama and MODEL_NAME=<a tool-capable local model>.
    If Ollama is not running, this degrades to RuleBasedPlanner rather than
    breaking the demo — model choice is not part of the security argument.
    """

    SYSTEM_PROMPT = (
        "You are a research agent that may spend a small budget. "
        "Given the user objective and a search result, reply with ONLY a JSON object: "
        '{"declared_goal": str, "amount": int (micro-ALGO), "destination": str}. '
        "No prose, no code fences."
    )

    def __init__(self, model: str = "llama3.2:3b", host: str = "http://127.0.0.1:11434", timeout: float = 30.0):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._fallback = RuleBasedPlanner()

    def available(self) -> bool:
        try:
            import httpx

            return httpx.get(f"{self.host}/api/tags", timeout=3.0).status_code == 200
        except Exception:
            return False

    @traceable(name="ollama_propose_payment", tags=["sentinelpay", "agent"], metadata={"component": "planner", "provider": "ollama"})
    def propose_payment(
        self, objective: str, tool_output: Dict[str, Any], default_destination: str
    ) -> ProposedPayment:
        try:
            import httpx

            response = httpx.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "system": self.SYSTEM_PROMPT,
                    "prompt": (
                        f"User objective: {objective}\n\n"
                        f"Search result: {tool_output.get('content', '')}\n\n"
                        f"Default payee if none is specified: {default_destination}"
                    ),
                    "stream": False,
                    "format": "json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            parsed = json.loads(response.json()["response"])
            if not isinstance(parsed, dict):
                raise ValueError("LLM output is not a JSON object")

            declared_goal = str(parsed["declared_goal"]).strip()
            amount = parsed["amount"]
            destination = str(parsed["destination"]).strip()
            # The model is untrusted: only accept an integer micro-ALGO amount.
            # Reject floats (silent truncation), negative and zero amounts, and
            # empty strings, then degrade to rules rather than pay on garbage.
            if not declared_goal or not destination:
                raise ValueError("LLM output has empty goal or destination")
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise ValueError(f"LLM amount is not an integer: {amount!r}")
            if amount <= 0:
                raise ValueError(f"LLM amount must be positive: {amount}")

            return ProposedPayment(
                declared_goal=declared_goal[:256],
                amount=amount,
                destination=destination,
                derived_from="local_llm",
            )
        except Exception as e:
            logger.warning("Ollama planner unavailable (%s); falling back to rules.", e)
            return self._fallback.propose_payment(objective, tool_output, default_destination)


def build_planner(provider: str, model: str) -> Planner:
    """Select a planner from configuration. Unknown providers fall back to rules."""
    if provider.lower() == "ollama":
        planner = OllamaPlanner(model=model)
        if planner.available():
            return planner
        logger.warning("MODEL_PROVIDER=ollama but Ollama is not reachable; using rules.")
    return RuleBasedPlanner()
