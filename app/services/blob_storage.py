from azure.storage.blob import (
    BlobServiceClient,
    BlobClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
)
from app.config import settings
import logging
from typing import Optional
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class BlobStorageService:
    def __init__(self):
        self.blob_service_client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        self.container_name = settings.AZURE_STORAGE_CONTAINER_NAME
        self._account_name, self._account_key = self._parse_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        self._ensure_container_exists()

    def _parse_connection_string(self, conn_str: str) -> tuple[str, str]:
        parts = {}
        for segment in conn_str.split(";"):
            if "=" in segment:
                key, value = segment.split("=", 1)
                parts[key] = value
        account_name = parts.get("AccountName")
        account_key = parts.get("AccountKey")
        if not account_name or not account_key:
            raise ValueError("Azure Storage connection string is missing AccountName or AccountKey")
        return account_name, account_key

    def _ensure_container_exists(self):
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            if not container_client.exists():
                container_client.create_container()
                logger.info(f"Container '{self.container_name}' created")
        except Exception as e:
            logger.error(f"Error ensuring container exists: {e}")
            raise

    def upload_file(
        self,
        file_data: bytes,
        filename: str,
        content_type: Optional[str] = None
    ) -> tuple[str, str]:
        try:
            blob_name = f"{uuid.uuid4()}_{filename}"
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )

            content_settings = None
            if content_type:
                content_settings = ContentSettings(content_type=content_type)

            blob_client.upload_blob(
                file_data,
                content_settings=content_settings,
                overwrite=True
            )

            blob_url = blob_client.url
            logger.info(f"File uploaded successfully: {blob_name}")
            return blob_name, blob_url

        except Exception as e:
            logger.error(f"Error uploading file to blob storage: {e}")
            raise

    def download_file(self, blob_name: str) -> bytes:
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            download_stream = blob_client.download_blob()
            return download_stream.readall()

        except Exception as e:
            logger.error(f"Error downloading file from blob storage: {e}")
            raise

    def delete_file(self, blob_name: str) -> bool:
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            blob_client.delete_blob()
            logger.info(f"File deleted successfully: {blob_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting file from blob storage: {e}")
            return False

    def get_blob_url(self, blob_name: str) -> str:
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )
        return blob_client.url

    def get_blob_sas_url(self, blob_name: str, expiry_minutes: int = 120) -> str:
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )
        expiry_time = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
        sas_token = generate_blob_sas(
            account_name=self._account_name,
            account_key=self._account_key,
            container_name=self.container_name,
            blob_name=blob_name,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time,
        )
        return f"{blob_client.url}?{sas_token}"


_blob_storage_service = None


def get_blob_storage_service() -> BlobStorageService:
    global _blob_storage_service
    if _blob_storage_service is None:
        _blob_storage_service = BlobStorageService()
    return _blob_storage_service
