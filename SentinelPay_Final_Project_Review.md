SENTINELPAY
Final Project Review & Build Specification
x402 Global Challenge — PreHack Bengaluru

Core thesis
Let the AI agent reason and act autonomously; do not let it spend autonomously outside an independently verified policy. SentinelPay turns an intent decision into an on-chain authorization that the payment settlement path must satisfy.

Build target: a real x402 payment flow protected by an agent-intent firewall, with Algorand enforcing the final authorization boundary.
Decision	Final choice
Agent runtime	Deep Agents (open-source) as the agent harness; Managed Deep Agents / LangSmith Deployment is an optional showcase path, not a paid dependency.
Payment rail	Algorand x402 using @x402-avm tooling and GoPlausible facilitator.
Security boundary	SentinelPay policy middleware + signed attestation + Algorand smart-contract validation in the settlement transaction group.
LLM verifier	Local/open model when possible; deterministic policy engine always remains authoritative for hard constraints.
Default environment	Local + Algorand TestNet; move to MainNet only for competition eligibility / final demonstration.

 
1. Project Definition
1.1 What SentinelPay is
SentinelPay is an authorization layer for autonomous payments. It sits between an agent’s requested economic action and the x402 settlement path. The agent may plan, browse, delegate, and call tools through Deep Agents, but any payment must be transformed into a structured intent, evaluated against policy, attested by the verifier, and accepted by the SentinelPay Algorand contract before the payment is allowed to settle.
The uploaded project review established the original core idea: move fraud / policy enforcement from advisory application code into an Algorand smart contract that participates in the same atomic transaction group as the payment. The final design keeps that thesis, while adding Deep Agents as the realistic autonomous-agent execution layer and strengthening the authorization model around exact payment intent. fileciteturn0file0L6-L13
The product is not “an AI fraud detector.”
The product is a deterministic economic authorization boundary for probabilistic agents. x402 provides payment transport and settlement; SentinelPay answers the missing question: “Was this exact payment authorized by the agent’s task and policy?”

1.2 One-sentence pitch
SentinelPay protects x402 payments made by autonomous agents by binding a structured, independently verified intent to the exact payment and enforcing that authorization on Algorand before settlement.
2. Deep Agents Integration
Deep Agents is used as the execution harness for the protected agent. Current LangChain documentation describes Deep Agents as an open-source agent harness with built-in planning, file-system context management, subagent delegation, and long-running execution capabilities. It can be deployed through LangSmith Deployments or run locally/self-hosted. citeturn303418search3turn303418search9
This is strategically useful because the project becomes more realistic as the agent becomes more autonomous: SentinelPay is not protecting a toy one-shot function; it is protecting a multi-step agent that may research, delegate, call tools, and eventually trigger an economic action.
Layer	Responsibility	Trust level
Deep Agent	Reasoning, planning, tool selection, subagent delegation, task execution.	Untrusted / potentially compromised
Intent Normalizer	Converts a proposed payment into a canonical structured action.	Untrusted input processor
Policy Engine	Deterministic allow/deny checks: limits, destinations, tools, expiry, policy version.	Trusted
Intent Verifier	Independent semantic check that proposed action matches the declared task/plan.	Trusted but fallible
Attestation signer	Signs the exact authorization object. Private key kept outside source control.	Highly trusted
SentinelPay contract	Validates attestation binding, policy limits, replay protection and settlement conditions.	Enforcement boundary
x402 facilitator	Verifies/settles the x402 payment according to protocol; never becomes the policy authority.	External infrastructure

Critical trust-boundary rule
The Deep Agent must never have unrestricted access to the wallet-signing primitive. It requests a payment through SentinelPay. SentinelPay constructs or authorizes the payment flow only after policy and intent checks. A compromised agent therefore cannot simply bypass the guard by calling wallet.sign() directly.

3. Final Architecture
3.1 Logical flow
USER
  |
  | task + budget / policy
  v
DEEP AGENT (Deep Agents)
  |  plan -> tools -> subagents -> proposed payment
  v
INTENT NORMALIZER
  |  canonical action: agent, task, tool, resource, amount, asset, destination, expiry
  v
SENTINELPAY POLICY GATE
  |---- deterministic checks (hard limits / allowlist / policy)
  |
  +---- semantic verifier (narrow input only)
  |
  v
SIGNED ATTESTATION
  |
  v
ATOMIC PAYMENT GROUP
  |  payment + SentinelPay app call (+ x402-specific transaction data)
  v
ALGOrand SentinelPay CONTRACT
  |---- attestation signature / binding
  |---- spend cap / per-call cap
  |---- nonce + lease / consumed flag
  |---- destination / amount / asset policy
  v
SETTLEMENT
  |
  v
x402 PAID ENDPOINT / RESOURCE
3.2 What must be true for settlement
•	The payment amount and recipient match the normalized authorized action.
•	The attestation is signed by the configured verifier identity and is bound to the exact payment/group context.
•	The attestation is within its expiry window and has not already been consumed.
•	The payment satisfies the agent / policy spending cap and any destination or tool allowlist.
•	The SentinelPay application call succeeds in the same atomic transaction group as the payment.
•	If any required condition fails, the group does not settle and the paid resource is not served.
Non-negotiable demo invariant
A malicious x402 payment must be constructible by the agent but impossible to settle unless the required SentinelPay authorization path is present. The demo must prove settlement failure, not merely show an application-layer “blocked” message.

4. x402 / Algorand Integration
Current Algorand developer documentation provides x402 tooling for Algorand TestNet and shows the resource server returning HTTP 402 with payment requirements while a facilitator verifies payment proof. The current JavaScript package @x402-avm/core includes AVM/Algorand support, and the Algorand ecosystem documents GoPlausible as the dedicated facilitator. citeturn106385search5turn106385search7turn106385search6
4.1 Build-time flow
GET /paid-tool
       |
       +--> 402 Payment Required
       |       requirements = { network, asset, price, payTo, ... }
       |
       v
Deep Agent decides to pay
       |
       v
SentinelPay protected payment tool
       |
       +--> normalize intent
       +--> policy check
       +--> verifier
       +--> signed attestation
       |
       v
construct protected atomic transaction group
       |
       v
GoPlausible facilitator / Algorand settlement path
       |
       +--> verify
       +--> contract enforces SentinelPay
       +--> settle
       |
       v
200 Paid Response
4.2 Facilitator strategy
•	Development: use the public GoPlausible facilitator endpoint on TestNet; this avoids building a facilitator during the critical path.
•	Do not treat the facilitator as the policy engine. The resource server must require a settlement proof that is consistent with the SentinelPay authorization group.
•	Fallback: keep a local/mock settlement path for unit and integration testing so facilitator outages do not block contract development.
•	Optional hardening: self-host an open-source facilitator only if the hosted path causes a reliability or protocol constraint. This is a contingency, not a baseline requirement.
Competition caveat
The current Global Challenge rules require a paid x402 endpoint deployed on Algorand MainNet, the GoPlausible facilitator, and at least one real MainNet payment for eligibility. Treat this as the final promotion step after the TestNet MVP is stable; it necessarily introduces small real blockchain / test-to-mainnet funding requirements even if no paid SaaS is used. citeturn106385search2turn106385search3turn106385search30

5. Authorization & Attestation Model
5.1 Canonical authorization object
Authorization = {
  version,
  policy_id,
  agent_id,
  intent_hash,
  task_scope_hash,
  tool_id,
  resource_id,
  destination,
  asset,
  amount,
  nonce,
  issued_at,
  expires_at
}

Attestation = Sign_Verifier(Authorization)
The important change from the original design is that the verifier does not merely sign “approved = true.” It signs an authorization that constrains the exact economic action. The contract then verifies the payment against those same fields.
5.2 Semantic verifier input
The verifier should receive only structured fields and a compact task/plan representation. It must not be fed raw untrusted web pages, arbitrary tool output, or the full conversational context unless absolutely necessary. This reduces prompt-injection exposure. A deterministic policy engine must run before and after the model-based check.
Check	Owner	Failure action
Allowed tool / resource	Policy engine	Reject immediately
Per-call amount cap	Policy engine + contract	Reject
Cumulative spend cap	Contract state	Reject
Task alignment	Verifier	No attestation
Destination match	Policy engine + contract	Reject
Expiry / nonce	Contract	Reject
Attestation already consumed	Contract	Reject
Atomic group membership	Contract / protected settlement path	Reject

6. Threat Model & Mitigations
Threat	Severity	Mitigation
Compromised Deep Agent bypasses verifier	Critical	Never expose raw wallet signer. Payment tool routes through SentinelPay; settlement requires SentinelPay contract authorization.
Bare x402 payment submitted without SentinelPay call	Critical	Protected settlement path verifies the payment is bound to a successful SentinelPay authorization call; bare payment is not accepted for the protected resource.
Attestation replay	High	Bind attestation to exact group/payment context; nonce + lease + consumed state + short expiry.
Verifier private key compromise	High	Environment secret only; separate TestNet/MainNet keys; document rotation; long-term path to multisig/threshold verifier.
Verifier LLM fooled by prompt injection	High	Structured-only verifier input; deterministic policy backstop; no raw fetched content; verifier output never overrides hard limits.
Spend-cap race / concurrent payments	Medium	Atomic contract state update; cumulative spend stored on-chain; conservative limits and tests for concurrent submission.
Destination substitution	High	Canonical destination included in authorization; contract checks exact destination.
Amount / asset substitution	High	Canonical amount + asset bound into signed authorization and checked on-chain.
Agent changes plan after authorization	High	Authorization bound to task scope hash / intent version and exact action fields; do not reuse attestations across actions.
Facilitator outage	Medium	Local/mock tests + manual fallback plan; hosted facilitator only external runtime dependency.
Verifier latency	Medium	Use a small local model / classifier; pre-approved low-risk actions can use deterministic policy-only path.
False positives	Medium	Small labeled scenario set; threshold tuning; clear deny reasons; keep demo scenarios deterministic.
Key / secret leakage	High	.env excluded from Git; least-privilege accounts; separate roles; never log secret material.
TestNet-only proof	Low for MVP	State as PoC scope; promotion to MainNet only after security checks and competition eligibility review.

7. Policy Model
agent: research-agent
policy_id: research-v1

limits:
  max_per_transaction: 0.10 USDC
  daily_limit: 1.00 USDC

allowed_tools:
  - web_search
  - academic_search
  - weather

allowed_resources:
  - research-api.example
  - weather-api.example

blocked_actions:
  - purchase
  - subscription
  - transfer

verifier_threshold:
  amount_gte: 0.02 USDC
This policy object is the product-level abstraction. The LLM verifier should never be the sole source of truth; deterministic fields are carried into the smart contract so a clever model cannot authorize an amount, destination, or tool outside the policy envelope.
8. Technology Stack — Zero-Paid Baseline
Component	Recommended choice	Cost posture
Agent harness	Deep Agents (Python)	Open source; local
Agent graph/runtime	LangGraph under Deep Agents	Open source; local
Model	Local tool-calling model via Ollama or LM Studio, if capable	No API bill
Fallback model	Any free/local model already available to the team	No paid dependency
Verifier	Small local classifier / cross-encoder or local LLM with structured JSON output	No API bill
Backend	Node.js + Express / FastAPI as needed	Open source
x402 SDK	@x402-avm/core + Algorand x402 packages	Open source
Blockchain	Algorand TestNet for development	Free TestNet assets
Smart contract	PyTeal / Beaker + AlgoKit	Open source
Facilitator	GoPlausible public facilitator for TestNet / competition path	No subscription; external service
Database	SQLite / local JSON for demo metadata; contract boxes for authoritative spend state	Free / local
Observability	Console logs + local structured traces; LangSmith tracing only if free access is available	No paid dependency
Hosting	Local for MVP; optional free-tier deployment if needed	No required paid hosting
Repo / CI	GitHub	Free tier

No-paid-tools rule
The core system must build, test, and demo without a paid LLM API, paid database, paid observability platform, paid hosting plan, or paid facilitator subscription. A managed cloud agent can be used only as an optional deployment showcase if the team has a genuinely free hackathon/grant quota; otherwise run Deep Agents locally or self-host the generated deployment artifact.

9. Repository / Code Organization
sentinelpay/
├── agent/
│   ├── deep_agent.py          # Deep Agent entrypoint
│   ├── tools.py               # protected x402 tool wrappers
│   ├── prompts.py
│   └── scenarios/             # legitimate + injection scenarios
├── sentinelpay/
│   ├── policy.py              # deterministic policy engine
│   ├── intent.py              # canonical intent schema + hashing
│   ├── verifier.py            # local semantic verifier
│   ├── attestation.py         # signing / verification
│   └── client.py              # protected payment orchestration
├── contracts/
│   ├── sentinelpay.py         # Beaker/PyTeal contract
│   └── tests/
├── x402-server/
│   ├── server.ts              # paid resource endpoint
│   └── middleware.ts          # x402 + SentinelPay integration
├── scripts/
│   ├── fund_testnet.py
│   ├── deploy_contract.py
│   ├── run_demo.py
│   └── verify_attack.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── adversarial/
├── docs/
└── .env.example
10. Smart Contract MVP
10.1 Minimum state
•	Verifier public key / authorized verifier identity.
•	Policy identifier and version.
•	Per-agent cumulative spend counter for the configured window.
•	Consumed nonce / authorization marker (box storage or equivalent).
•	Optional per-agent policy configuration for the demo.
10.2 Minimum application calls
•	authorize_and_pay / validate_authorization: validates the exact attestation and payment constraints.
•	record_spend: updates cumulative spend atomically.
•	consume_nonce: marks the authorization as used.
•	optional admin/config call for the demo policy, protected by creator/admin authorization.
Keep the contract small. Avoid adding a generalized marketplace, reputation graph, DAO governance, or arbitrary policy language during the hackathon.
11. Required Test Matrix
Test	Expected result
Valid task + valid tool + valid amount	Settlement succeeds
Valid task + amount above per-call cap	Contract rejects
Valid task + cumulative daily cap exceeded	Contract rejects
Wrong destination	Contract rejects
Wrong asset	Contract rejects
No attestation	Contract rejects
Invalid verifier signature	Contract rejects
Expired attestation	Contract rejects
Reused attestation / nonce	Contract rejects
Prompt-injected tool output triggers unauthorized purchase	Verifier/policy rejects; no settlement
Compromised client submits bare payment	Protected settlement path rejects / resource remains unpaid
Two rapid payments near cap	Only valid cumulative state is accepted
Facilitator unavailable	Local integration test remains runnable; no silent authorization bypass
Verifier unavailable	Fail closed for protected/high-risk payments

12. Final Demo Script
12.1 Scene A — legitimate autonomous payment
1.	User asks the Deep Agent to research a service and permits a small budget.
2.	Deep Agent plans the task and calls a paid x402 research tool.
3.	The endpoint responds with HTTP 402 and payment requirements.
4.	SentinelPay extracts a canonical payment intent from the agent request.
5.	Deterministic policy checks pass; the verifier confirms task alignment and signs the exact authorization.
6.	The protected atomic transaction group is submitted.
7.	Algorand confirms settlement; the paid resource is returned.
8.	Show the successful transaction and the corresponding authorization metadata.
12.2 Scene B — prompt injection / economic attack
9.	The same Deep Agent encounters a malicious tool response containing an instruction to purchase a premium resource.
10.	The agent attempts to follow the instruction.
11.	SentinelPay normalizes the proposed payment and detects that the action is outside the declared task or policy.
12.	No valid attestation is issued.
13.	The agent cannot obtain the required authorized settlement group.
14.	Show that the malicious payment attempt does not settle on Algorand.
15.	Show the paid endpoint refusing the resource and explain that the enforcement is not merely an application warning.
Best visual moment
Show the same agent making both decisions, then show the chain-level difference: legitimate payment confirms; malicious payment fails before settlement. This demonstrates why SentinelPay is an enforcement layer rather than another prompt filter.

13. Build Order
Phase	Deliverable	Definition of done
0 — Scaffold	Repo, environments, TestNet accounts, package setup	All services start locally; secrets isolated
1 — x402 baseline	Unprotected paid endpoint	402 -> payment -> 200 works on TestNet
2 — Contract	SentinelPay contract skeleton + state	Deployable; unit tests pass
3 — Exact authorization	Canonical intent + attestation + contract checks	Wrong amount/destination/nonce fails on-chain
4 — Agent	Deep Agent + protected payment tool	Agent can complete legitimate task end-to-end
5 — Attack	Prompt-injection scenario	Agent attempts malicious payment; settlement fails
6 — Hardening	Concurrency, replay, key handling, fail-closed behavior	Adversarial test suite passes
7 — Demo	Logs, transaction links, slides, rehearsed script	2–3 minute deterministic demo works from clean start
8 — Optional managed deployment	Deploy Deep Agent to LangSmith managed cloud if free access exists	Same agent code works without changing SentinelPay boundary
9 — Competition promotion	MainNet endpoint + required x402 tagging / usage	Meets current challenge checklist

14. Team Ownership
Track	Primary owner	Outputs
Algorand / contract	Member A	Contract, AlgoKit, atomic groups, deploys, contract tests
Deep Agent / x402	Member B	Deep Agent, protected tools, x402 endpoint, integration
Verifier / security	Member C	Policy engine, verifier, attestations, attack scenarios, threat model
Cross-review	All	End-to-end tests, demo, security review, final narrative

15. Explicit Non-Goals
•	No paid API dependency in the core build.
•	No general-purpose fraud detection platform.
•	No wallet custody or unrestricted agent wallet access.
•	No multi-agent marketplace or reputation graph for the MVP.
•	No general-purpose on-chain policy language.
•	No complex frontend beyond what is required to visualize the demo.
•	No MainNet deployment until the TestNet attack / authorization flow is reliable.
•	No claim that the LLM verifier itself is cryptographically trustworthy; the contract and deterministic policy layer are the actual enforcement boundary.
16. Remaining Risks / Open Questions
Risk / question	Decision before implementation freeze
Exact x402 AVM transaction-group structure for the selected scheme	Confirm against the current @x402-avm/core examples and Algorand guide before writing the contract binding logic.
How the facilitator surfaces the final transaction proof	Define the resource-server acceptance criterion for the protected payment path; do not rely on a UI-side success flag.
Deep Agent model choice	Prefer a locally available tool-calling model that is stable under the demo workload; model choice is not part of the security proof.
Managed Deep Agents cost / quota	Use only if free quota is explicit; otherwise local/self-hosted Deep Agents is the baseline.
MainNet funds	Budget the smallest realistic amount needed for the required real payment and keep MainNet keys segregated from TestNet keys.
Contract storage economics	Keep state minimal and measure MBR / state footprint before MainNet promotion.

17. Definition of Done
•	A Deep Agent can complete a paid task through an x402 endpoint on Algorand TestNet.
•	The agent never directly signs an unrestricted payment transaction.
•	Every protected payment has a canonical intent and signed attestation.
•	The Algorand contract checks the exact authorization constraints and spend state.
•	A prompt-injection scenario can cause the agent to request an unauthorized payment, but that payment does not settle.
•	Replay, amount substitution, destination substitution, and cap-overrun tests fail safely.
•	The complete flow works without any paid LLM or SaaS dependency.
•	The demo can explain the distinction between x402 payment transport, Deep Agent autonomy, and SentinelPay enforcement.
•	Before final competition submission, the project is promoted to the current MainNet / GoPlausible requirements if the team elects to enter the leaderboard.
18. Sources & Verification Notes
This document combines the uploaded SentinelPay review with current external verification of Deep Agents and the Algorand x402 challenge / tooling. The uploaded review remains the source of the team’s original scope, roles, and initial threat model. External sources below were used only to update deployment and competition-specific assumptions.
LangChain — Deep Agents Quickstart: https://docs.langchain.com/oss/python/deepagents/quickstart
Deep Agents planning, tool use, subagents, and local execution.
LangChain — Deep Agents Overview: https://docs.langchain.com/oss/javascript/deepagents/overview
Deep Agents as an open-source agent harness and its capabilities.
LangChain — LangSmith Deployment: https://docs.langchain.com/langsmith/deployment
Managed deployment path for Deep Agents.
LangChain — Going to production: https://docs.langchain.com/oss/python/deepagents/going-to-production
Managed deployment, durability, auth, and production considerations.
Algorand Developer Portal — x402 on Algorand: https://dev.algorand.co/resources/x402-on-algorand/
Current Algorand x402 TestNet setup and facilitator integration.
Algorand — Global x402 Challenge: https://algorand.co/global-x402-challenge
Current challenge workflow and MainNet requirements.
Algorand Foundation — Global Challenge build guide: https://algorand.co/blog/the-x402-global-challenge-is-live-how-to-build-submit-your-entry
Current submission / leaderboard requirements.
@x402-avm/core — npm: https://www.npmjs.com/package/@x402-avm/core
Current TypeScript x402 AVM package and Algorand support.
GoPlausible / Algorand ecosystem: https://goplausible.com/
Algorand agentic tooling and x402 facilitator context.
