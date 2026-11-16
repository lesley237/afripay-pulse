import argparse
import hashlib
import hmac
import json
import random
import time
import urllib.error
import urllib.request
import uuid

GATEWAY_URL = "http://localhost:8080"
SECRETS = {
    "mtn": "dev_momo_hmac_secret_key_change_in_prod",
    "orange": "dev_om_hmac_secret_key_change_in_prod",
}


def sign_payload(raw_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()


def send_webhook(provider: str, payload: dict, bad_sig: bool = False):
    raw = json.dumps(payload).encode("utf-8")
    sig = "forged_signature_000" if bad_sig else sign_payload(raw, SECRETS[provider])
    req = urllib.request.Request(
        f"{GATEWAY_URL}/webhooks/{provider}",
        data=raw,
        headers={"Content-Type": "application/json", "X-Signature": sig},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"[{provider.upper()}] HTTP {resp.status} -> {resp.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"[{provider.upper()}] HTTP {e.code} -> {e.read().decode()}")


def run_simulation(count: int):
    phones = ["237670123456", "237677987654", "237690112233", "237655443322"]
    amounts = [2500, 5000, 10000, 15000, 25000, 50000, 100000]

    for i in range(count):
        provider = random.choice(["mtn", "orange"])
        prefix = "MOMO" if provider == "mtn" else "OM"
        payload = {
            "external_reference": f"{prefix}-{uuid.uuid4().hex[:10].upper()}",
            "payer_phone": random.choice(phones),
            "amount": random.choice(amounts),
            "currency": "XAF",
            "status": "SUCCESSFUL",
        }

        print(f"\n--- Event {i+1}/{count}: {payload['external_reference']} ({payload['amount']} XAF) ---")
        send_webhook(provider, payload)

        # 30% chance telco retries the exact same webhook (tests DynamoDB idempotency)
        if random.random() < 0.30:
            print("  -> Simulating telco duplicate retry...")
            send_webhook(provider, payload)

        # 15% chance an attacker sends a forged webhook (tests HMAC 401 defense)
        if random.random() < 0.15:
            print("  -> Simulating forged webhook attack...")
            send_webhook(provider, payload, bad_sig=True)

        time.sleep(0.3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AfriPay Telco Webhook Chaos Simulator")
    parser.add_argument("--count", type=int, default=8, help="Number of payments to simulate")
    parser.add_argument("--poison", action="store_true", help="Send a poison-pill payment (999999 XAF) to trigger DLQ")
    args = parser.parse_args()

    if args.poison:
        poison_payload = {
            "external_reference": f"MOMO-POISON-{uuid.uuid4().hex[:6].upper()}",
            "payer_phone": "237670000999",
            "amount": 999999,
            "currency": "XAF",
            "status": "SUCCESSFUL",
        }
        print(f"Sending poison-pill webhook: {poison_payload['external_reference']}")
        send_webhook("mtn", poison_payload)
    else:
        run_simulation(args.count)
