import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List

import boto3
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from app.config import settings
from app.ledger import settle_payment_atomically

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("afripay.worker")


def get_sqs_client():
    return boto3.client(
        "sqs",
        endpoint_url=settings.AWS_ENDPOINT_URL,
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def poll_sqs_once() -> int:
    """Polls SQS for up to 10 messages, settles each into Postgres, and deletes on success."""
    sqs = get_sqs_client()
    resp = sqs.receive_message(
        QueueUrl=settings.SQS_MAIN_QUEUE_URL,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=2,
        AttributeNames=["ApproximateReceiveCount"],
    )
    messages = resp.get("Messages", [])
    if not messages:
        return 0

    processed = 0
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        for msg in messages:
            receipt_handle = msg["ReceiptHandle"]
            receive_count = msg.get("Attributes", {}).get("ApproximateReceiveCount", "1")
            try:
                event = json.loads(msg["Body"])
                settle_payment_atomically(conn, event)

                # Delete from SQS ONLY after Postgres ACID commit succeeds
                sqs.delete_message(
                    QueueUrl=settings.SQS_MAIN_QUEUE_URL,
                    ReceiptHandle=receipt_handle,
                )
                processed += 1
            except Exception as exc:
                # Leaving message undeleted allows SQS visibility timeout to expire
                # and redrive to DLQ after maxReceiveCount=3 attempts.
                logger.error(
                    "[RETRY/DLQ] Failed processing SQS msg_id=%s (attempt=%s): %s",
                    msg.get("MessageId"),
                    receive_count,
                    exc,
                )
    return processed


async def background_poller():
    logger.info("Starting background SQS settlement poller on %s", settings.SQS_MAIN_QUEUE_URL)
    while True:
        try:
            await asyncio.to_thread(poll_sqs_once)
        except Exception as exc:
            logger.error("SQS poller loop error: %s", exc)
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(background_poller())
    yield
    task.cancel()


app = FastAPI(title="AfriPay-Pulse Ledger & Settlement API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "payment-worker"}


@app.get("/api/summary")
def get_summary() -> Dict[str, Any]:
    sqs = get_sqs_client()
    main_attrs = sqs.get_queue_attributes(
        QueueUrl=settings.SQS_MAIN_QUEUE_URL,
        AttributeNames=["ApproximateNumberOfMessages"],
    )["Attributes"]
    dlq_attrs = sqs.get_queue_attributes(
        QueueUrl=settings.SQS_DLQ_URL,
        AttributeNames=["ApproximateNumberOfMessages"],
    )["Attributes"]

    with psycopg.connect(settings.POSTGRES_DSN, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_settled,
                    COALESCE(SUM(amount), 0) AS total_volume_xaf,
                    COALESCE(SUM(CASE WHEN provider = 'MTN_MOMO' THEN amount ELSE 0 END), 0) AS mtn_volume_xaf,
                    COALESCE(SUM(CASE WHEN provider = 'ORANGE_MONEY' THEN amount ELSE 0 END), 0) AS orange_volume_xaf
                FROM transactions
                WHERE status = 'SETTLED'
                """
            )
            stats = cur.fetchone()

            cur.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END), 0) AS total_debits,
                    COALESCE(SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END), 0) AS total_credits
                FROM ledger_entries
                """
            )
            ledger_balance = cur.fetchone()

    return {
        "total_settled": stats["total_settled"],
        "total_volume_xaf": stats["total_volume_xaf"],
        "mtn_volume_xaf": stats["mtn_volume_xaf"],
        "orange_volume_xaf": stats["orange_volume_xaf"],
        "ledger_balanced": ledger_balance["total_debits"] == ledger_balance["total_credits"],
        "total_debits_xaf": ledger_balance["total_debits"],
        "total_credits_xaf": ledger_balance["total_credits"],
        "sqs_queued_count": int(main_attrs.get("ApproximateNumberOfMessages", 0)),
        "dlq_quarantined_count": int(dlq_attrs.get("ApproximateNumberOfMessages", 0)),
    }


@app.get("/api/transactions")
def list_transactions(limit: int = 25) -> List[Dict[str, Any]]:
    with psycopg.connect(settings.POSTGRES_DSN, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, external_reference, provider, payer_phone, amount, currency, status, created_at
                FROM transactions
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()


@app.post("/api/dlq/replay")
def replay_dlq_messages() -> Dict[str, Any]:
    """Moves quarantined DLQ messages back to the main SQS queue after fixing simulate_failure."""
    sqs = get_sqs_client()
    resp = sqs.receive_message(
        QueueUrl=settings.SQS_DLQ_URL,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=1,
    )
    messages = resp.get("Messages", [])
    replayed = 0

    for msg in messages:
        try:
            body = json.loads(msg["Body"])
            # Remediate simulated failure flag/amount before re-enqueueing
            if body.get("amount") == 999999:
                body["amount"] = 25000
            body.pop("simulate_failure", None)

            sqs.send_message(
                QueueUrl=settings.SQS_MAIN_QUEUE_URL,
                MessageBody=json.dumps(body),
            )
            sqs.delete_message(
                QueueUrl=settings.SQS_DLQ_URL,
                ReceiptHandle=msg["ReceiptHandle"],
            )
            replayed += 1
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to replay message: {exc}")

    return {"replayed_count": replayed}
