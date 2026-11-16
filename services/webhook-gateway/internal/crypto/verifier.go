package crypto

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// ComputeHMAC generates a hex-encoded HMAC-SHA256 signature for a payload.
func ComputeHMAC(payload []byte, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	return hex.EncodeToString(mac.Sum(nil))
}

// VerifySignature validates an incoming X-Signature header in constant time
// to prevent timing side-channel attacks.
func VerifySignature(payload []byte, providedSignature string, secret string) bool {
	if providedSignature == "" || secret == "" {
		return false
	}

	// Support both raw hex ("a1b2...") and prefixed ("sha256=a1b2...") headers
	cleanSig := strings.TrimPrefix(strings.TrimSpace(providedSignature), "sha256=")
	expectedSig := ComputeHMAC(payload, secret)

	return hmac.Equal([]byte(cleanSig), []byte(expectedSig))
}
