package awsclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	sqstypes "github.com/aws/aws-sdk-go-v2/service/sqs/types"
)

type WebhookSecrets struct {
	MomoSecret string `json:"MOMO_WEBHOOK_SECRET"`
	OmSecret   string `json:"OM_WEBHOOK_SECRET"`
}

type Client struct {
	DynamoDB       *dynamodb.Client
	SQS            *sqs.Client
	SecretsManager *secretsmanager.Client
	TableName      string
	QueueURL       string
	SecretName     string
}

func NewClient(ctx context.Context) (*Client, error) {
	endpoint := getEnv("AWS_ENDPOINT_URL", "http://localhost:4566")
	region := getEnv("AWS_REGION", "us-east-1")

	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(region))
	if err != nil {
		return nil, fmt.Errorf("failed to load AWS config: %w", err)
	}

	ddbClient := dynamodb.NewFromConfig(cfg, func(o *dynamodb.Options) {
		if endpoint != "" {
			o.BaseEndpoint = aws.String(endpoint)
		}
	})

	sqsClient := sqs.NewFromConfig(cfg, func(o *sqs.Options) {
		if endpoint != "" {
			o.BaseEndpoint = aws.String(endpoint)
		}
	})

	smClient := secretsmanager.NewFromConfig(cfg, func(o *secretsmanager.Options) {
		if endpoint != "" {
			o.BaseEndpoint = aws.String(endpoint)
		}
	})

	return &Client{
		DynamoDB:       ddbClient,
		SQS:            sqsClient,
		SecretsManager: smClient,
		TableName:      getEnv("IDEMPOTENCY_TABLE_NAME", "afripay-local-idempotency-keys"),
		QueueURL:       getEnv("SQS_MAIN_QUEUE_URL", "http://localhost:4566/000000000000/afripay-local-payment-events"),
		SecretName:     getEnv("WEBHOOK_SECRET_NAME", "afripay/local/webhook-hmac-secrets"),
	}, nil
}

func (c *Client) FetchWebhookSecrets(ctx context.Context) (*WebhookSecrets, error) {
	out, err := c.SecretsManager.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
		SecretId: aws.String(c.SecretName),
	})
	if err != nil {
		return nil, fmt.Errorf("failed to fetch secret %s: %w", c.SecretName, err)
	}

	var secrets WebhookSecrets
	if err := json.Unmarshal([]byte(*out.SecretString), &secrets); err != nil {
		return nil, fmt.Errorf("failed to parse secret JSON: %w", err)
	}
	return &secrets, nil
}

func (c *Client) AcquireIdempotencyLock(ctx context.Context, key string, provider string) (bool, error) {
	expiresAt := time.Now().Add(7 * 24 * time.Hour).Unix()

	_, err := c.DynamoDB.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(c.TableName),
		Item: map[string]ddbtypes.AttributeValue{
			"idempotency_key": &ddbtypes.AttributeValueMemberS{Value: key},
			"provider":        &ddbtypes.AttributeValueMemberS{Value: provider},
			"locked_at":       &ddbtypes.AttributeValueMemberS{Value: time.Now().UTC().Format(time.RFC3339)},
			"expires_at":      &ddbtypes.AttributeValueMemberN{Value: fmt.Sprintf("%d", expiresAt)},
		},
		ConditionExpression: aws.String("attribute_not_exists(idempotency_key)"),
	})

	if err != nil {
		var condErr *ddbtypes.ConditionalCheckFailedException
		if errors.As(err, &condErr) {
			return false, nil
		}
		return false, fmt.Errorf("dynamodb put item failed: %w", err)
	}

	return true, nil
}

func (c *Client) EnqueuePaymentEvent(ctx context.Context, payload []byte, provider string, externalRef string) (string, error) {
	out, err := c.SQS.SendMessage(ctx, &sqs.SendMessageInput{
		QueueUrl:    aws.String(c.QueueURL),
		MessageBody: aws.String(string(payload)),
		MessageAttributes: map[string]sqstypes.MessageAttributeValue{
			"Provider": {
				DataType:    aws.String("String"),
				StringValue: aws.String(provider),
			},
			"ExternalReference": {
				DataType:    aws.String("String"),
				StringValue: aws.String(externalRef),
			},
		},
	})
	if err != nil {
		return "", fmt.Errorf("sqs send message failed: %w", err)
	}
	return *out.MessageId, nil
}

func getEnv(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}
