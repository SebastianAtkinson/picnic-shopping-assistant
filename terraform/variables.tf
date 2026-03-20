variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "europe-west4"
}

variable "cloud_run_service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "picnic-bot"
}

variable "telegram_bot_token" {
  description = "Telegram bot token"
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key"
  type        = string
  sensitive   = true
}

variable "picnic_username" {
  description = "Picnic account username (email)"
  type        = string
  sensitive   = true
}

variable "picnic_password" {
  description = "Picnic account password"
  type        = string
  sensitive   = true
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

variable "webhook_url" {
  description = "Public HTTPS URL of the Cloud Run service (used as Telegram webhook)"
  type        = string
  default     = ""
}