#!/usr/bin/env bash
set -e

VARS=(
  -var="project_id=$GOOGLE_CLOUD_PROJECT"
  -var="telegram_bot_token=$TELEGRAM_BOT_TOKEN"
  -var="anthropic_api_key=$ANTHROPIC_API_KEY"
  -var="picnic_username=$PICNIC_USERNAME"
  -var="picnic_password=$PICNIC_PASSWORD"
)

PROJECT=$GOOGLE_CLOUD_PROJECT
REGION=europe-west4

echo "Importing resources for project: $PROJECT"

terraform import "${VARS[@]}" \
  google_artifact_registry_repository.picnic_bot \
  "projects/$PROJECT/locations/$REGION/repositories/picnic-bot"

terraform import "${VARS[@]}" \
  google_secret_manager_secret.telegram_token \
  "projects/$PROJECT/secrets/TELEGRAM_BOT_TOKEN"

terraform import "${VARS[@]}" \
  google_secret_manager_secret.anthropic_key \
  "projects/$PROJECT/secrets/ANTHROPIC_API_KEY"

terraform import "${VARS[@]}" \
  google_secret_manager_secret.picnic_username \
  "projects/$PROJECT/secrets/PICNIC_USERNAME"

terraform import "${VARS[@]}" \
  google_secret_manager_secret.picnic_password \
  "projects/$PROJECT/secrets/PICNIC_PASSWORD"

terraform import "${VARS[@]}" \
  google_service_account.picnic_bot \
  "projects/$PROJECT/serviceAccounts/picnic-bot-sa@$PROJECT.iam.gserviceaccount.com"

terraform import "${VARS[@]}" \
  google_cloud_run_v2_service.picnic_bot \
  "projects/$PROJECT/locations/$REGION/services/picnic-bot"

echo "Import complete. Run 'terraform plan' to verify."
