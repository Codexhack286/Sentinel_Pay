"""
Tests for the standalone SentinelPay Verifier Service (services/verifier/app.py).

This FastAPI service had zero test coverage before now - it's a separate
deployable node (per docs/architecture.md, an "independent verification and
attestation issuance node"), distinct from the gateway class it wraps.
"""

from fastapi.testclient import TestClient

from services.verifier.app import app, gateway

client = TestClient(app)


def test_health_endpoint_reports_public_key():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "online"
    assert body["service"] == "SentinelPay Verifier"
    assert body["public_key"] == gateway.verifier.public_key_b64


def test_verify_endpoint_authorizes_legitimate_request():
    payload = {
        "intent": {
            "agent_id": "agent-1",
            "declared_goal": "Research solar energy market statistics",
            "tool_name": "paid_research",
            "resource": "energy-dataset",
            "destination": "MERCHANT_ADDR",
            "amount": 50000,
            "currency": "uALGO",
        },
        "policy": {
            "policy_id": "policy-1",
            "agent_id": "agent-1",
            "max_per_transaction": 200000,
            "daily_spend_limit": 1000000,
            "allowed_tools": ["paid_research"],
            "allowed_destinations": ["MERCHANT_ADDR"],
            "allowed_categories": ["research", "energy"],
        },
    }
    resp = client.post("/verify", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "authorized"
    assert body["attestation"] is not None


def test_verify_endpoint_denies_policy_violation():
    payload = {
        "intent": {
            "agent_id": "agent-1",
            "declared_goal": "Research solar energy market statistics",
            "tool_name": "paid_research",
            "resource": "energy-dataset",
            "destination": "MERCHANT_ADDR",
            "amount": 999999999,  # exceeds max_per_transaction
            "currency": "uALGO",
        },
        "policy": {
            "policy_id": "policy-1",
            "agent_id": "agent-1",
            "max_per_transaction": 200000,
            "daily_spend_limit": 1000000,
            "allowed_tools": ["paid_research"],
            "allowed_destinations": ["MERCHANT_ADDR"],
            "allowed_categories": ["research", "energy"],
        },
    }
    resp = client.post("/verify", json=payload)
    assert resp.status_code == 200  # denial is a normal response, not an HTTP error
    body = resp.json()
    assert body["status"] == "denied"
    assert body["attestation"] is None


def test_verify_endpoint_rejects_malformed_request_body():
    resp = client.post("/verify", json={"intent": {}, "policy": {}})
    assert resp.status_code == 422  # pydantic validation error, missing required fields
