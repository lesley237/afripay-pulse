module "messaging" {
  source      = "../../modules/messaging"
  environment = "local"
}

module "database" {
  source      = "../../modules/database"
  environment = "local"
}

module "security" {
  source              = "../../modules/security"
  environment         = "local"
  momo_webhook_secret = "dev_momo_hmac_secret_key_change_in_prod"
  om_webhook_secret   = "dev_om_hmac_secret_key_change_in_prod"
}

output "sqs_main_queue_url" {
  value = module.messaging.main_queue_url
}

output "sqs_dlq_url" {
  value = module.messaging.dlq_url
}

output "dynamodb_idempotency_table" {
  value = module.database.idempotency_table_name
}

output "secrets_manager_name" {
  value = module.security.webhook_secret_name
}
