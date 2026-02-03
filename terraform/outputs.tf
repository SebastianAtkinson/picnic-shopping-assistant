output "service_url" {
  description = "URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.picnic_bot.uri
}

output "artifact_registry_url" {
  description = "Artifact Registry repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.picnic_bot.repository_id}"
}

output "service_account_email" {
  description = "Service account email"
  value       = google_service_account.picnic_bot.email
}