# SentinelPay Agent Specification

## 1. Primary Agent: Deep Research Agent

- **Identifier**: `deep-agent-researcher-01`
- **Role**: Autonomous researcher for deep analysis, public querying, and x402 resource retrieval.
- **Capabilities**:
  - Task decomposition and structured planning
  - Subagent delegation to specialized sub-researchers
  - Free tool consumption (`free_research`)
  - Protected economic execution via `paid_research` (SentinelPay gated)

## 2. Hard Security Boundaries

1. **NO DIRECT SIGNING**: The agent runtime possesses no private keys to sign arbitrary blockchain transactions.
2. **INTENT ONLY**: Any payment requirement encountered must be converted into a structured `PaymentIntent`.
3. **FAIL-CLOSED**: If SentinelPay returns `status: "denied"`, the agent terminates the payment attempt immediately and reports policy constraints to the user.
