package handler

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"

	awsclient "github.com/lesley237/afripay-pulse/services/webhook-gateway/internal/aws"
	"github.com/lesley237/afripay-pulse/services/webhook-gateway/internal/crypto"
)

type WebhookPayload struct {
	ExternalReference string `json:"external_reference"`
	PayerPhone        string `json:"payer_phone"`
	Amount            int64  `json:"amount"`
	Currency          string `json:"currency"`
	Status            string `json:"status"`
}

type WebhookHandler struct {
	AWS     *awsclient.Client
	Secrets *awsclient.WebhookSecrets
}

func (h *WebhookHandler) HandleWebhook(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}

	// Extract provider from URL path: /webhooks/mtn or /webhooks/orange
	providerParam := strings.ToLower(strings.TrimPrefix(r.URL.Path, "/webhooks/"))
	var providerCode string
	var signingSecret string

	switch providerParam {
	case "mtn":
		providerCode = "MTN_MOMO"
		signingSecret = h.Secrets.MomoSecret
	case "orange":
		providerCode = "ORANGE_MONEY"
		signingSecret = h.Secrets.OmSecret
	default:
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "unsupported provider; use /webhooks/mtn or /webhooks/orange"})
		return
	}

	// 1. Read raw body (limit to 1MB to prevent memory exhaustion attacks)
	bodyBytes, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "unable to read request body"})
		return
	}
	defer r.Body.Close()

	// 2. Verify HMAC-SHA256 signature
	sigHeader := r.Header.Get("X-Signature")
	if !crypto.VerifySignature(bodyBytes, sigHeader, signingSecret) {
		log.Printf("[SECURITY] Rejected forged webhook for provider=%s remote=%s", providerCode, r.RemoteAddr)
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid HMAC signature"})
		return
	}

	// 3. Parse & validate payload fields
	var payload WebhookPayload
	if err := json.Unmarshal(bodyBytes, &payload); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON payload"})
		return
	}
	if payload.ExternalReference == "" || payload.Amount <= 0 || payload.PayerPhone == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "missing required fields: external_reference, payer_phone, amount"})
		return
	}

	// 4. Enforce idempotency via DynamoDB conditional write
	idempotencyKey := fmt.Sprintf("%s#%s", providerCode, payload.ExternalReference)
	isNew, err := h.AWS.AcquireIdempotencyLock(r.Context(), idempotencyKey, providerCode)
	if err != nil {
		log.Printf("[ERROR] DynamoDB idempotency check failed: %v", err)
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "internal state store error"})
		return
	}

	if !isNew {
		log.Printf("[IDEMPOTENCY] Duplicate webhook ignored key=%s", idempotencyKey)
		writeJSON(w, http.StatusOK, map[string]string{
			"status":             "duplicate_ignored",
			"external_reference": payload.ExternalReference,
		})
		return
	}

	// 5. Enqueue verified event to SQS
	enrichedEvent, _ := json.Marshal(map[string]any{
		"provider":           providerCode,
		"external_reference": payload.ExternalReference,
		"payer_phone":        payload.PayerPhone,
		"amount":             payload.Amount,
		"currency":           defaultCurrency(payload.Currency),
		"provider_status":    payload.Status,
	})

	msgID, err := h.AWS.EnqueuePaymentEvent(r.Context(), enrichedEvent, providerCode, payload.ExternalReference)
	if err != nil {
		log.Printf("[ERROR] Failed to enqueue SQS message: %v", err)
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to queue payment event"})
		return
	}

	log.Printf("[ACCEPTED] Queued payment provider=%s ref=%s amount=%d sqs_msg_id=%s",
		providerCode, payload.ExternalReference, payload.Amount, msgID)

	writeJSON(w, http.StatusAccepted, map[string]string{
		"status":             "queued",
		"external_reference": payload.ExternalReference,
		"sqs_message_id":     msgID,
	})
}

func defaultCurrency(c string) string {
	if c == "" {
		return "XAF"
	}
	return c
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}
