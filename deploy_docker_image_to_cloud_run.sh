#!/bin/bash
docker build --platform linux/amd64 -t picnic-bot:latest .
docker tag picnic-bot:latest europe-west4-docker.pkg.dev/sebastian-atkinson-sndbx-w/picnic-bot/picnic-bot:latest
docker push europe-west4-docker.pkg.dev/sebastian-atkinson-sndbx-w/picnic-bot/picnic-bot:latest

gcloud run services update picnic-bot \   
  --region=europe-west4 \
  --project=sebastian-atkinson-sndbx-w \
  --image=europe-west4-docker.pkg.dev/sebastian-atkinson-sndbx-w/picnic-bot/picnic-bot:latest