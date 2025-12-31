#!/bin/bash
# Script to restore Azure Container App environment variables

set -euo pipefail

echo "Restoring environment variables for Azure Container App..."

az containerapp update \
  --name backend \
  --resource-group lab_tutor \
  --set-env-vars \
    PORT=8000 \
    LAB_TUTOR_NEO4J_URI="neo4j+s://c6a5bb7a.databases.neo4j.io" \
    LAB_TUTOR_NEO4J_USERNAME="neo4j" \
    LAB_TUTOR_NEO4J_PASSWORD=secretref:neo4j-password \
    LAB_TUTOR_NEO4J_DATABASE="neo4j" \
    XIAOCASE_API_KEY=secretref:xiaocase-api-key \
    XIAOCASE_API_BASE="https://api.xiaocaseai.com/v1" \
    XIAOCASE_MODEL="deepseek-v3.2" \
    LAB_TUTOR_LANGSMITH_API_KEY=secretref:langsmith-api-key \
    LAB_TUTOR_LANGSMITH_PROJECT="concept-relationship-detection" \
    LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING=secretref:azure-storage-conn \
    LAB_TUTOR_AZURE_CONTAINER_NAME="course-teacher-materials" \
    LAB_TUTOR_SECRET_KEY=secretref:lab-tutor-secret-key \
    LAB_TUTOR_DATABASE_URL=secretref:lab-tutor-database-url \
    LAB_TUTOR_CORS_ALLOW_ORIGINS="https://gray-meadow-055f6ba1e.1.azurestaticapps.net,https://gray-meadow-055f6ba1e-staging.1.azurestaticapps.net"

echo "Environment variables restored successfully!"
echo ""
echo "Next steps:"
echo "1. Wait for the container app to restart (1-2 minutes)"
echo "2. Check health: curl https://backend.mangoocean-d0c97d4f.westus2.azurecontainerapps.io/health"
echo "3. Try uploading and extracting course materials again"

