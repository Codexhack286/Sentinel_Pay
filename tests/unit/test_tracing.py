"""Tests for the LangSmith tracing bootstrap (sentinelpay/tracing.py).

The wiring bug this guards: `_configure` previously looked at ``os.environ``
(via ``setdefault``) to respect ``LANGSMITH_TRACING=false``, but values from
``.env`` land in ``settings``, not ``os.environ``. So a key in ``.env`` plus
``LANGSMITH_TRACING=false`` still traced. The override must be read from
``settings`` (which merges shell env and .env), distinguished from the
"unset" default via ``model_fields_set``.
"""

import os
import types

import pytest

import sentinelpay.tracing as tracing

_ENV_KEYS = ("LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGSMITH_PROJECT")


def _fake_settings(api_key, tracing_value, explicit=False):
    s = types.SimpleNamespace(
        LANGSMITH_API_KEY=api_key,
        LANGSMITH_TRACING=tracing_value,
        LANGSMITH_PROJECT=None,
    )
    s.model_fields_set = {"LANGSMITH_TRACING"} if explicit else set()
    return s


@pytest.fixture
def clean_env():
    saved = {k: os.environ.get(k) for k in _ENV_KEYS}
    for k in _ENV_KEYS:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_tracing_defaults_on_when_key_present(monkeypatch, clean_env):
    monkeypatch.setattr(tracing, "settings", _fake_settings("key-1", False))
    tracing._configure()
    assert os.environ["LANGSMITH_TRACING"] == "true"


def test_explicit_false_disables_even_with_key(monkeypatch, clean_env):
    monkeypatch.setattr(tracing, "settings", _fake_settings("key-1", False, explicit=True))
    tracing._configure()
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_explicit_true_enables_with_key(monkeypatch, clean_env):
    monkeypatch.setattr(tracing, "settings", _fake_settings("key-1", True, explicit=True))
    tracing._configure()
    assert os.environ["LANGSMITH_TRACING"] == "true"


def test_no_key_disables_tracing(monkeypatch, clean_env):
    monkeypatch.setattr(tracing, "settings", _fake_settings(None, False))
    tracing._configure()
    assert os.environ["LANGSMITH_TRACING"] == "false"