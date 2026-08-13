"""Attack B — Client / Verifier Bypass Test.
Verifies that bare payment submissions without SentinelPay attestation fail settlement.
"""

from fastapi.testclient import TestClient
from services.api.app import app

client = TestClient(app)


def test_bare_payment_without_sentinelpay_rejected():
    # Attempt 1: Direct request with standard or missing auth
    resp1 = client.get("/paid-dataset", headers={"Authorization": "Bearer fake_token"})
    assert resp1.status_code == 403
    assert "Invalid authorization scheme; SentinelPay-AVM required" in resp1.json()["detail"]

    # Attempt 2: Fake malformed SentinelPay header
    resp2 = client.get("/paid-dataset", headers={"Authorization": "SentinelPay-AVM invalid_base64_data"})
    assert resp2.status_code == 403
    assert "Failed to decode or verify settlement proof" in resp2.json()["detail"]
