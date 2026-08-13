"""Development launcher for SentinelPay API and Verifier services."""

import uvicorn
from sentinelpay.config import settings


def main():
    print(f"Starting SentinelPay x402 Development API on port {settings.API_PORT}...")
    uvicorn.run("services.api.app:app", host="127.0.0.1", port=settings.API_PORT, reload=True)


if __name__ == "__main__":
    main()
