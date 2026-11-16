variable "environment" {
  type = string
}

resource "aws_dynamodb_table" "idempotency_keys" {
  name         = "afripay-${var.environment}-idempotency-keys"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idempotency_key"

  attribute {
    name = "idempotency_key"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = {
    Project     = "afripay-pulse"
    Environment = var.environment
  }
}

output "idempotency_table_name" {
  value = aws_dynamodb_table.idempotency_keys.name
}
