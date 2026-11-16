import json
import logging
from typing import Any, Dict
import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger("afripay.ledger")


def settle_payment_atomically(conn: psycopg.Connection, event: Dict[str, Any]) -> str:
    """
    Settles a verified payment inside a single ACID database transaction:
    1. Inserts or updates the transaction record as SETTLED (idempotent on external_reference).
    2. Writes balanced double-entry rows (DEBIT telco clearing, CREDIT merchant wallet).
    """
    external_ref = event["external_reference"]
    provider = event["provider"]
    payer_phone = event["payer_phone"]
    amount = int(event["amount"])
    currency = event.get("currency", "XAF")

    if amount <= 0:
        raise ValueError(f"Invalid non-positive amount: {amount}")

    # Simulated poison-pill failure trigger for testing SQS -> DLQ redrive behavior
    if amount == 999999 or event.get("simulate_failure") is True:
        raise RuntimeError(f"Simulated downstream core-banking outage for ref={external_ref}")

    clearing_account = (
        "TELCO_CLEARING_MTN" if provider == "MTN_MOMO" else "TELCO_CLEARING_ORANGE"
    )

    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            # Guard against duplicate settlement at the DB layer (defense-in-depth)
            cur.execute(
                "SELECT id, status FROM transactions WHERE external_reference = %s",
                (external_ref,),
            )
            existing = cur.fetchone()
            if existing and existing["status"] == "SETTLED":
                logger.info("Transaction %s already settled in Postgres; skipping.", external_ref)
                return str(existing["id"])

            cur.execute(
                """
                INSERT INTO transactions (
                    external_reference, provider, payer_phone, amount, currency, status, raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, 'SETTLED', %s::jsonb)
                RETURNING id
                """,
                (
                    external_ref,
                    provider,
                    payer_phone,
                    amount,
                    currency,
                    json.dumps(event),
                ),
            )
            tx_row = cur.fetchone()
            tx_id = tx_row["id"]

            # Double-Entry Leg 1: DEBIT Telco Clearing Account
            cur.execute(
                """
                INSERT INTO ledger_entries (transaction_id, account_name, entry_type, amount, currency)
                VALUES (%s, %s, 'DEBIT', %s, %s)
                """,
                (tx_id, clearing_account, amount, currency),
            )

            # Double-Entry Leg 2: CREDIT Merchant Wallet Account
            cur.execute(
                """
                INSERT INTO ledger_entries (transaction_id, account_name, entry_type, amount, currency)
                VALUES (%s, 'MERCHANT_WALLET_MAIN', 'CREDIT', %s, %s)
                """,
                (tx_id, amount, currency),
            )

    logger.info(
        "[SETTLED] ref=%s provider=%s amount=%d %s tx_id=%s",
        external_ref,
        provider,
        amount,
        currency,
        tx_id,
    )
    return str(tx_id)
