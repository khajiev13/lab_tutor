import hashlib
import logging

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient
from fastapi import UploadFile

from app.core.settings import settings

logger = logging.getLogger(__name__)


class BlobService:
    def __init__(self):
        self.connection_string = settings.azure_storage_connection_string
        self.container_name = settings.azure_container_name
        self.service_client = None
        self.container_client = None

        if self.connection_string:
            try:
                self.service_client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
                self.container_client = self.service_client.get_container_client(
                    self.container_name
                )
                if not self.container_client.exists():
                    self.container_client.create_container()
                logger.info("Successfully connected to Azure Blob Storage")
            except Exception as e:
                logger.error(f"Failed to initialize BlobService: {e}")
        else:
            logger.warning(
                "Azure Storage Connection String is missing. Blob Service will not work."
            )

    async def upload_bytes(
        self, content: bytes, destination_path: str, *, overwrite: bool = True
    ) -> str:
        if not self.container_client:
            raise Exception("Blob service is not configured")

        blob_client = self.container_client.get_blob_client(destination_path)
        try:
            blob_client.upload_blob(content, overwrite=overwrite)
            return blob_client.url
        except Exception as e:
            logger.error(f"Failed to upload bytes to {destination_path}: {e}")
            raise

    async def upload_file(self, file: UploadFile, destination_path: str) -> str:
        if not self.container_client:
            raise Exception("Blob service is not configured")

        try:
            # Reset file pointer to the beginning
            await file.seek(0)
            content = await file.read()

            return await self.upload_bytes(content, destination_path, overwrite=True)
        except Exception as e:
            logger.error(f"Failed to upload file {destination_path}: {e}")
            raise

    @staticmethod
    def sha256_hex(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def delete_file(self, blob_path: str) -> None:
        if not self.container_client:
            raise Exception("Blob service is not configured")

        blob_client = self.container_client.get_blob_client(blob_path)
        try:
            blob_client.delete_blob()
        except ResourceNotFoundError:
            # Treat missing blobs as already deleted (idempotent delete).
            return
        except Exception as e:
            logger.error(f"Failed to delete file {blob_path}: {e}")
            raise

    async def delete_folder(self, folder_path: str) -> None:
        if not self.container_client:
            raise Exception("Blob service is not configured")

        try:
            blobs = self.container_client.list_blobs(name_starts_with=folder_path)
            for blob in blobs:
                try:
                    self.container_client.delete_blob(blob.name)
                except ResourceNotFoundError:
                    # Idempotent deletion; ignore missing blobs.
                    continue
        except Exception as e:
            logger.error(f"Failed to delete folder {folder_path}: {e}")
            raise

    async def list_files(self, folder_path: str) -> list[str]:
        if not self.container_client:
            raise Exception("Blob service is not configured")

        try:
            blobs = self.container_client.list_blobs(name_starts_with=folder_path)
            return [blob.name for blob in blobs]
        except Exception as e:
            logger.error(f"Failed to list files in {folder_path}: {e}")
            raise

    def download_file(self, blob_path: str) -> bytes:
        """Download a blob by path and return its bytes."""
        if not self.container_client:
            raise Exception("Blob service is not configured")

        blob_client = self.container_client.get_blob_client(blob_path)
        try:
            downloader = blob_client.download_blob()
            return downloader.readall()
        except Exception as e:
            logger.error(f"Failed to download file {blob_path}: {e}")
            raise

    def get_blob_info(self, blob_path: str) -> dict:
        """Return JSON-serializable blob metadata/properties for debugging/observability."""
        if not self.container_client:
            raise Exception("Blob service is not configured")

        blob_client = self.container_client.get_blob_client(blob_path)
        try:
            props = blob_client.get_blob_properties()
            # Keep the return value JSON-friendly (no datetime objects).
            return {
                "name": getattr(props, "name", blob_path),
                "url": blob_client.url,
                "size_bytes": getattr(props, "size", None),
                "content_type": getattr(
                    getattr(props, "content_settings", None), "content_type", None
                ),
                "etag": getattr(props, "etag", None),
                "last_modified": props.last_modified.isoformat()
                if getattr(props, "last_modified", None)
                else None,
                "creation_time": props.creation_time.isoformat()
                if getattr(props, "creation_time", None)
                else None,
                "metadata": getattr(props, "metadata", None) or {},
            }
        except Exception as e:
            logger.error(f"Failed to get blob properties for {blob_path}: {e}")
            raise


blob_service = BlobService()
