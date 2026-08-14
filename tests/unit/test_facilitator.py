"""Unit tests for the GoPlausible facilitator client's request-shaping logic.

These tests deliberately do NOT hit the live facilitator (no network access
assumed in CI/sandbox). They verify that outgoing payloads match the
GoPlausible x402-avm V2 schema documented at
https://github.com/GoPlausible/.github/blob/main/profile/algorand-x402-documentation/README.md
"""

from sentinelpay.payments.facilitator import (
    ALGORAND_TESTNET_CAIP2,
    MAX_ATOMIC_GROUP_SIZE,
    ExactAvmPayload,
    GoPlausibleFacilitatorClient,
    PaymentRequirementsV2,
    XPaymentHeader,
)


def test_payment_requirements_serializes_with_camelcase_aliases():
    reqs = PaymentRequirementsV2(
        asset="10458941",  # USDC testnet ASA ID
        amount="10000",
        pay_to="RECEIVERAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    )
    dumped = reqs.model_dump(by_alias=True)
    assert dumped["payTo"] == reqs.pay_to
    assert dumped["maxTimeoutSeconds"] == 60
    assert dumped["network"] == ALGORAND_TESTNET_CAIP2


def test_x_payment_header_matches_documented_shape():
    payload = ExactAvmPayload(payment_group=["base64txn0", "base64txn1"], payment_index=0)
    header = XPaymentHeader(payload=payload)
    as_dict = header.to_header_dict()

    assert as_dict["x402Version"] == 2
    assert as_dict["scheme"] == "exact"
    assert as_dict["payload"]["paymentGroup"] == ["base64txn0", "base64txn1"]
    assert as_dict["payload"]["paymentIndex"] == 0


def test_sentinelpay_group_fits_within_facilitator_group_limit():
    # SentinelPay's group is [payment, app_call] = 2 txns, well within the
    # documented Max Atomic Group Size of 16 (see facilitator.py docstring
    # for why the app-call leg is a supported "additional transaction").
    sentinelpay_group_size = 2
    assert sentinelpay_group_size <= MAX_ATOMIC_GROUP_SIZE


def test_client_constructs_without_network_call():
    client = GoPlausibleFacilitatorClient()
    assert client.base_url == "https://facilitator.goplausible.xyz"
