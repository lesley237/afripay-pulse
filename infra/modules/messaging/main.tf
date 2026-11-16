variable "environment" {
  type = string
}

resource "aws_sqs_queue" "payment_events_dlq" {
  name                      = "afripay-${var.environment}-payment-events-dlq"
  message_retention_seconds = 1209600

  tags = {
    Project     = "afripay-pulse"
    Environment = var.environment
    Role        = "dead-letter-queue"
  }
}

resource "aws_sqs_queue" "payment_events" {
  name                       = "afripay-${var.environment}-payment-events"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.payment_events_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Project     = "afripay-pulse"
    Environment = var.environment
    Role        = "primary-ingestion-queue"
  }
}

output "main_queue_url" {
  value = aws_sqs_queue.payment_events.url
}

output "main_queue_arn" {
  value = aws_sqs_queue.payment_events.arn
}

output "dlq_url" {
  value = aws_sqs_queue.payment_events_dlq.url
}

output "dlq_arn" {
  value = aws_sqs_queue.payment_events_dlq.arn
}
