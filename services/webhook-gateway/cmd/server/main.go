package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"time"

	awsclient "github.com/lesley237/afripay-pulse/services/webhook-gateway/internal/aws"
	"github.com/lesley237/afripay-pulse/services/webhook-gateway/internal/handler"
)

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	client, err := awsclient.NewClient(ctx)
	if err != nil {
		log.Fatalf("Failed to initialize AWS/Floci client: %v", err)
	}

	secrets, err := client.FetchWebhookSecrets(ctx)
	if err != nil {
		log.Fatalf("Failed to load HMAC secrets from Secrets Manager: %v", err)
	}
	log.Println("Loaded HMAC signing secrets from Secrets Manager successfully.")

	wh := &handler.WebhookHandler{
		AWS:     client,
		Secrets: secrets,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"healthy","service":"webhook-gateway"}`))
	})
	mux.HandleFunc("/webhooks/", wh.HandleWebhook)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	server := &http.Server{
		Addr:         ":" + port,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	log.Printf("AfriPay Webhook Gateway listening on :%s", port)
	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("Server stopped: %v", err)
	}
}
