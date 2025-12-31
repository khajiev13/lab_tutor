# Extraction Failure Fix

## Problem

Extraction was failing in Azure deployment with the error:
```
Extraction Failed
There was an error processing your course materials. Please check your files and try again.
```

## Root Cause

The GitHub Actions workflow file (`.github/workflows/backend.yml`) was using `--set-env-vars PORT=8000` during deployment, which **replaced all environment variables** instead of just setting PORT. This removed critical configuration including:

- `XIAOCASE_API_KEY` - Required for LLM extraction
- `XIAOCASE_API_BASE` - LLM API endpoint
- `XIAOCASE_MODEL` - Model to use for extraction
- All other environment variables (Neo4j, storage, etc.)

When the `DocumentLLMExtractor` tried to initialize, it would throw:
```python
ValueError: LLM is required for extraction. Set LAB_TUTOR_LLM_API_KEY (or XiaoCase fallback env vars).
```

## Solution

### 1. Fixed GitHub Workflow

Updated `.github/workflows/backend.yml` to remove the `--set-env-vars` flag from deployment:

```yaml
- name: Deploy to Azure Container Apps
  shell: bash
  run: |
    set -euo pipefail
    az containerapp update \
      --name "$AZURE_CONTAINERAPP_NAME" \
      --resource-group "$AZURE_RESOURCE_GROUP" \
      --image "$ACR_LOGIN_SERVER/$IMAGE_NAME:${GITHUB_SHA}" \
      --only-show-errors
```

This ensures environment variables persist across deployments.

### 2. Restore Environment Variables

Run the provided script to restore all environment variables:

```bash
./fix-azure-env.sh
```

Or manually run:

```bash
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
```

### 3. Verify the Fix

After restoring environment variables:

1. Wait 1-2 minutes for the container to restart
2. Check health endpoint:
   ```bash
   curl https://backend.mangoocean-d0c97d4f.westus2.azurecontainerapps.io/health
   ```
3. Try uploading and extracting course materials again

## Future Deployments

With the workflow fix in place, future deployments will:
1. Build and push the new Docker image
2. Update the container app to use the new image
3. **Preserve all existing environment variables**

## Technical Details

The extraction process works as follows:

1. Teacher uploads course files (PDF, DOCX, TXT) to Azure Blob Storage
2. Teacher clicks "Start Extraction"
3. Background task processes each file:
   - Downloads file from blob storage
   - Extracts text content
   - Calls LLM API (via `DocumentLLMExtractor`) to extract concepts
   - Stores results in SQL and Neo4j graph database
4. UI shows extraction progress and results

The `DocumentLLMExtractor` requires these environment variables (with backwards compatibility aliases):
- `LAB_TUTOR_LLM_API_KEY` (or `XIAOCASE_API_KEY`, `OPENAI_API_KEY`)
- `LAB_TUTOR_LLM_BASE_URL` (or `XIAOCASE_API_BASE`, default: xiaocaseai.com)
- `LAB_TUTOR_LLM_MODEL` (or `XIAOCASE_MODEL`, default: deepseek-v3.2)

## Prevention

To prevent this issue in the future:
1. Never use `--set-env-vars` in deployment scripts without listing ALL variables
2. Use `--replace-env-vars` if you need to update specific variables
3. Consider using infrastructure-as-code (Terraform/Bicep) to manage environment variables
4. Add health checks to CI/CD to catch missing environment variables early

