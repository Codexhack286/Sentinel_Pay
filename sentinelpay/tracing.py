"""Central LangSmith tracing bootstrap for SentinelPay.

Importing this module once configures the environment LangSmith reads at call
time and re-exports the ``traceable`` decorator, so every pipeline imports
tracing from a single place instead of wiring up env vars per module.

When LANGSMITH_API_KEY is set, tracing is enabled and traces land in the
``LANGSMITH_PROJECT`` project (defaulting to "sentinelpay"). Without a key,
LANGSMITH_TRACING is set to "false" and every decorated call is a transparent
no-op.
"""

import os

from sentinelpay.config import settings

DEFAULT_PROJECT = "sentinelpay"


def _configure() -> None:
    if settings.LANGSMITH_API_KEY:
        # Respect an explicit override. The value may come from the shell or
        # from .env; pydantic-settings merges both into `settings`, so look
        # there, not at os.environ. An unset LANGSMITH_TRACING defaults to on.
        explicit = "LANGSMITH_TRACING" in settings.model_fields_set
        enabled = settings.LANGSMITH_TRACING if explicit else True
        os.environ["LANGSMITH_TRACING"] = "true" if enabled else "false"
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ.setdefault(
            "LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT or DEFAULT_PROJECT
        )
    else:
        os.environ["LANGSMITH_TRACING"] = "false"


_configure()

from langsmith import traceable  # noqa: E402

__all__ = ["traceable", "DEFAULT_PROJECT"]