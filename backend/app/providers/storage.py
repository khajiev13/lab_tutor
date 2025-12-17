import logging

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

    async def upload_file(self, file: UploadFile, destination_path: str) -> str:
        if not self.container_client:
            raise Exception("Blob service is not configured")

        blob_client = self.container_client.get_blob_client(destination_path)

        try:
            # Reset file pointer to the beginning
            await file.seek(0)
            content = await file.read()

            # Upload the file
            blob_client.upload_blob(content, overwrite=True)

            return blob_client.url
        except Exception as e:
            logger.error(f"Failed to upload file {destination_path}: {e}")
            raise

    async def delete_file(self, blob_path: str) -> None:
        if not self.container_client:
            raise Exception("Blob service is not configured")

        blob_client = self.container_client.get_blob_client(blob_path)
        try:
            blob_client.delete_blob()
        except Exception as e:
            logger.error(f"Failed to delete file {blob_path}: {e}")
            raise

    async def delete_folder(self, folder_path: str) -> None:
        if not self.container_client:
            raise Exception("Blob service is not configured")

        try:
            blobs = self.container_client.list_blobs(name_starts_with=folder_path)
            for blob in blobs:
                self.container_client.delete_blob(blob.name)
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


blob_service = BlobService()
