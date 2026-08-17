"""Deep Agent harness implementation."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agent.planner import Planner, ProposedPayment, RuleBasedPlanner
from agent.tools.paid_tool import PaidResearchTool
from agent.tools.research_tool import FreeResearchTool
from sentinelpay.gateway.middleware import SentinelPayGateway
from sentinelpay.policy.models import AgentPolicy
from sentinelpay.tracing import traceable

# Where a legitimate purchase is expected to go. Overridable per instance so the
# demos and the live TestNet run can point at a real payee.
DEFAULT_RESOURCE_OWNER = "RESOURCE_OWNER_ALGORAND_ADDRESS_AAAAAAAAAAAAAAAAAAAAAAAAAAAA"


class TaskPlan(BaseModel):
    """Structured plan produced by the Deep Agent."""

    objective: str
    steps: List[str]
    estimated_cost_micro_units: int
    required_tools: List[str]


class AgentExecutionLog(BaseModel):
    """Log of agent actions during execution."""

    agent_id: str
    objective: str
    plan: TaskPlan
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    proposed_payment: Optional[ProposedPayment] = None
    payment_attempts: List[Dict[str, Any]] = Field(default_factory=list)
    final_output: Optional[str] = None
    status: str = "initialized"


class DeepAgent:
    """
    Deep Agents compatible harness.

    - Plans a task and calls tools
    - Has no wallet-signing privileges of any kind
    - Every payment goes through SentinelPay, which may refuse

    The agent is explicitly *untrusted*. It is allowed to be wrong, gullible, or
    fully compromised; nothing here is load-bearing for security.
    """

    def __init__(
        self,
        agent_id: str = "deep-agent-researcher-01",
        policy: Optional[AgentPolicy] = None,
        gateway: Optional[SentinelPayGateway] = None,
        planner: Optional[Planner] = None,
        resource_owner: str = DEFAULT_RESOURCE_OWNER,
    ):
        self.agent_id = agent_id
        self.policy = policy
        self.gateway = gateway
        self.planner = planner or RuleBasedPlanner()
        self.resource_owner = resource_owner
        self.free_tool = FreeResearchTool()
        self.paid_tool = PaidResearchTool(gateway=gateway, policy=policy)

    @traceable(name="deep_agent_plan_task", tags=["sentinelpay", "agent"], metadata={"component": "agent"})
    def plan_task(self, user_objective: str, max_budget_micro_units: int = 100_000) -> TaskPlan:
        """Generate a structured task breakdown from the user objective."""
        return TaskPlan(
            objective=user_objective,
            steps=[
                "1. Perform initial discovery using the free research tool.",
                "2. Check whether deeper data requires a paid x402 resource.",
                "3. Request SentinelPay authorization for the required payment.",
                "4. If authorized, settle the payment and complete the report.",
            ],
            estimated_cost_micro_units=min(max_budget_micro_units, 100_000),
            required_tools=["free_research", "paid_research"],
        )

    @traceable(name="deep_agent_run", tags=["sentinelpay", "agent"], metadata={"component": "agent"})
    def run(self, user_objective: str, simulate_attack: bool = False) -> AgentExecutionLog:
        """Execute the objective through planning and tool use.

        `simulate_attack` controls only what the *tool returns* — it seeds a
        malicious search result. The payment parameters are then whatever the
        planner derives from that text, so the attack is performed rather than
        staged.
        """
        plan = self.plan_task(user_objective)
        log = AgentExecutionLog(agent_id=self.agent_id, objective=user_objective, plan=plan)

        query = "Solar Energy Injection Test" if simulate_attack else "Solar Energy Trends 2026"
        tool_output = self.free_tool.execute(query)
        log.tool_calls.append({"tool": "free_research", "query": query, "result": tool_output})

        proposal = self.planner.propose_payment(
            objective=user_objective,
            tool_output=tool_output,
            default_destination=self.resource_owner,
        )
        log.proposed_payment = proposal

        payment_result = self.paid_tool.request_payment_intent(
            agent_id=self.agent_id,
            declared_goal=proposal.declared_goal,
            # The user's objective, passed through by the harness rather than
            # restated by the agent. A hijacked agent can change its declared
            # goal but not the scope that goal is checked against.
            task_scope=user_objective,
            amount=proposal.amount,
            destination=proposal.destination,
            resource=proposal.resource,
            currency=proposal.currency,
        )
        log.payment_attempts.append(payment_result)

        status = payment_result.get("status")
        if status == "authorized":
            log.status = "completed_successfully"
            log.final_output = (
                f"Task succeeded. SentinelPay authorized {proposal.amount} uALGO. "
                f"Attestation ID: {payment_result['attestation']['attestation_id']}. "
                "Paid research data aggregated into the final report."
            )
        elif status == "denied":
            log.status = "blocked_by_policy"
            log.final_output = (
                "Task stopped: SentinelPay blocked the payment request. "
                f"Reason: {payment_result.get('reason')}. Funds remained protected."
            )
        else:
            log.status = "awaiting_authorization"
            log.final_output = (
                f"Payment intent created: {payment_result.get('payment_intent_id')}. "
                "Awaiting SentinelPay evaluation."
            )

        return log
