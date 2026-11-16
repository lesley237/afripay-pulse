package crypto

import "testing"

func TestVerifySignature(t *testing.T) {
	secret := "test_secret_key"
	payload := []byte(`{"external_reference":"MOMO-123","amount":5000}`)
	validSig := ComputeHMAC(payload, secret)

	if !VerifySignature(payload, validSig, secret) {
		t.Fatal("expected valid HMAC signature to pass verification")
	}

	if !VerifySignature(payload, "sha256="+validSig, secret) {
		t.Fatal("expected sha256= prefixed signature to pass verification")
	}

	if VerifySignature(payload, "tampered_signature_123", secret) {
		t.Fatal("expected tampered signature to fail verification")
	}

	if VerifySignature(payload, "", secret) {
		t.Fatal("expected empty signature to fail verification")
	}
}
