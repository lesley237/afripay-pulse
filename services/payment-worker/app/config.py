import os


class Settings:
    AWS_ENDPOINT_URL: str = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "test")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "test")

    SQS_MAIN_QUEUE_URL: str = os.getenv(
        "SQS_MAIN_QUEUE_URL",
        "http://localhost:4566/000000000000/afripay-local-payment-events",
    )
    SQS_DLQ_URL: str = os.getenv(
        "SQS_DLQ_URL",
        "http://localhost:4566/000000000000/afripay-local-payment-events-dlq",
    )

    POSTGRES_DSN: str = os.getenv(
        "POSTGRES_DSN",
        "postgresql://afripay:local_dev_password@localhost:5432/afripay_ledger",
    )


settings = Settings()
