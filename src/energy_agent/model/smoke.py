import os


def main() -> None:
    if not (os.getenv("MODEL_GATEWAY_BASE_URL") and os.getenv("MODEL_GATEWAY_API_KEY")):
        print("MODEL_GATEWAY_VALIDATION=BLOCKED_MISSING_CREDENTIALS")
        return
    print("MODEL_GATEWAY_VALIDATION=BLOCKED_LIVE_REQUEST_NOT_CONFIGURED")


if __name__ == "__main__":
    main()
