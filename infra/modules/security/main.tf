variable "environment" {
  type = string
}

variable "momo_webhook_secret" {
  type      = string
  sensitive = true
}

variable "om_webhook_secret" {
  type      = string
  sensitive = true
}

resource "aws_secretsmanager_secret" "webhook_secrets" {
  name                    = "afripay/${var.environment}/webhook-hmac-secrets"
  description             = "HMAC-SHA256 signing secrets for MTN MoMo and Orange Money webhooks"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "webhook_secrets_val" {
  secret_id = aws_secretsmanager_secret.webhook_secrets.id
  secret_string = jsonencode({
    MOMO_WEBHOOK_SECRET = var.momo_webhook_secret
    OM_WEBHOOK_SECRET   = var.om_webhook_secret
  })
}

output "webhook_secret_arn" {
  value = aws_secretsmanager_secret.webhook_secrets.arn
}

output "webhook_secret_name" {
  value = aws_secretsmanager_secret.webhook_secrets.name
}
