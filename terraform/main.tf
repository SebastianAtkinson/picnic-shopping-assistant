terraform {
  required_version = ">= 1.0"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Artifact Registry repository for Docker images
resource "google_artifact_registry_repository" "picnic_bot" {
  location      = var.region
  repository_id = "picnic-bot"
  description   = "Docker repository for Picnic Bot"
  format        = "DOCKER"
}

# Secret Manager secrets
resource "google_secret_manager_secret" "telegram_token" {
  secret_id = "TELEGRAM_BOT_TOKEN"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "telegram_token" {
  secret      = google_secret_manager_secret.telegram_token.id
  secret_data = var.telegram_bot_token
}

resource "google_secret_manager_secret" "anthropic_key" {
  secret_id = "ANTHROPIC_API_KEY"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "anthropic_key" {
  secret      = google_secret_manager_secret.anthropic_key.id
  secret_data = var.anthropic_api_key
}

# Service account for Cloud Run
resource "google_service_account" "picnic_bot" {
  account_id   = "picnic-bot-sa"
  display_name = "Picnic Bot Service Account"
}

# Grant service account access to secrets
resource "google_secret_manager_secret_iam_member" "telegram_token_access" {
  secret_id = google_secret_manager_secret.telegram_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.picnic_bot.email}"
}

resource "google_secret_manager_secret_iam_member" "anthropic_key_access" {
  secret_id = google_secret_manager_secret.anthropic_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.picnic_bot.email}"
}

# Cloud Run service
resource "google_cloud_run_v2_service" "picnic_bot" {
  name     = var.cloud_run_service_name
  location = var.region
  
  template {
    service_account = google_service_account.picnic_bot.email
    
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.picnic_bot.repository_id}/picnic-bot:${var.image_tag}"
      
      ports {
        container_port = 8080
      }
      
      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
      
      env {
        name = "TELEGRAM_BOT_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.telegram_token.secret_id
            version = "latest"
          }
        }
      }
      
      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_key.secret_id
            version = "latest"
          }
        }
      }
      
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
    
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
  }
  
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
  
  depends_on = [
    google_secret_manager_secret_version.telegram_token,
    google_secret_manager_secret_version.anthropic_key
  ]
}

# Make service publicly accessible
resource "google_cloud_run_service_iam_member" "public_access" {
  service  = google_cloud_run_v2_service.picnic_bot.name
  location = google_cloud_run_v2_service.picnic_bot.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}