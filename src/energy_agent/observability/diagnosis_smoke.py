import os


def main() -> None:
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        print("LANGFUSE_DIAGNOSIS_VALIDATION=BLOCKED_MISSING_CREDENTIALS")
        return
    print("LANGFUSE_DIAGNOSIS_VALIDATION=BLOCKED_LIVE_DIAGNOSIS_NOT_CONFIGURED")


if __name__ == "__main__":
    main()
