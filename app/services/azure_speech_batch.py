import httpx
import logging
import time
from typing import Optional
from urllib.parse import urlparse
from app.config import settings

logger = logging.getLogger(__name__)


class AzureSpeechBatchService:
    def __init__(self):
        raw_endpoint = getattr(settings, "AZURE_SPEECH_ENDPOINT", "") or \
            f"https://{settings.AZURE_SPEECH_REGION}.api.cognitive.microsoft.com"
        self.endpoint = raw_endpoint.rstrip("/")
        self.headers = {
            "Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY,
            "Content-Type": "application/json",
        }
        self.api_version = settings.AZURE_SPEECH_API_VERSION

    def transcribe_blob(
        self,
        blob_sas_url: str,
        locale: str = "ja-JP",
        timeout_seconds: int = 1800,
        poll_interval_seconds: int = 5,
    ) -> str:
        transcription_id = self._create_transcription(blob_sas_url, locale)
        self._wait_for_completion(
            transcription_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        return self._fetch_transcription_text(transcription_id)

    def submit_transcription(self, blob_sas_url: str, locale: str = "ja-JP") -> str:
        return self._create_transcription(blob_sas_url, locale)

    def get_transcription_status(self, transcription_id: str) -> dict:
        response = httpx.get(
            f"{self.endpoint}/speechtotext/transcriptions/{transcription_id}",
            headers=self.headers,
            params={"api-version": self.api_version},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return {"status": data.get("status"), "error": data.get("error")}

    def fetch_transcription_text(self, transcription_id: str) -> str:
        return self._fetch_transcription_text(transcription_id)

    def _create_transcription(self, blob_sas_url: str, locale: str) -> str:
        url = f"{self.endpoint}/speechtotext/transcriptions:submit"
        payload = {
            "contentUrls": [blob_sas_url],
            "locale": locale,
            "displayName": "meeting-notes-transcription",
            "properties": {
                "punctuationMode": "DictatedAndAutomatic",
                "timeToLiveHours": 6,
            },
        }
        response = httpx.post(
            url,
            headers=self.headers,
            json=payload,
            params={"api-version": self.api_version},
            timeout=60,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Batch submit failed: {response.text}")
            raise e
        location = response.headers.get("Location") or response.headers.get("Operation-Location")
        if location:
            return self._extract_transcription_id(location)
        data = response.json()
        transcription_url = data.get("self")
        if not transcription_url:
            raise RuntimeError("Failed to get transcription URL from Azure Speech response")
        return self._extract_transcription_id(transcription_url)

    def _wait_for_completion(
        self,
        transcription_id: str,
        timeout_seconds: int,
        poll_interval_seconds: int,
    ) -> None:
        start_time = time.time()
        while True:
            response = httpx.get(
                f"{self.endpoint}/speechtotext/transcriptions/{transcription_id}",
                headers=self.headers,
                params={"api-version": self.api_version},
                timeout=60,
            )
            response.raise_for_status()
            status = response.json().get("status")
            if status in {"Succeeded", "Failed"}:
                if status == "Failed":
                    error = response.json().get("error")
                    raise RuntimeError(f"Batch transcription failed: {error}")
                return
            if time.time() - start_time > timeout_seconds:
                raise TimeoutError("Batch transcription timed out")
            time.sleep(poll_interval_seconds)

    def _fetch_transcription_text(self, transcription_id: str) -> str:
        files_url = f"{self.endpoint}/speechtotext/transcriptions/{transcription_id}/files"
        response = httpx.get(
            files_url,
            headers=self.headers,
            params={"api-version": self.api_version},
            timeout=60,
        )
        response.raise_for_status()
        files = response.json().get("values", [])
        content_url: Optional[str] = None
        for item in files:
            if item.get("kind") == "Transcription":
                content_url = item.get("links", {}).get("contentUrl")
                break
        if not content_url:
            raise RuntimeError("Transcription content URL not found")
        content_response = httpx.get(content_url, timeout=60)
        content_response.raise_for_status()
        content = content_response.json()
        return self._extract_transcription_text(content)

    def _extract_transcription_id(self, url: str) -> str:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        for marker in ("transcriptions", "transcriptions:submit"):
            try:
                idx = parts.index(marker)
                if idx + 1 < len(parts):
                    return parts[idx + 1]
            except ValueError:
                continue
        raise RuntimeError("Failed to parse transcription ID from Azure Speech URL")

    def _extract_transcription_text(self, content: dict) -> str:
        combined = content.get("combinedRecognizedPhrases")
        if combined:
            return " ".join([item.get("display", "") for item in combined]).strip()
        recognized = content.get("recognizedPhrases")
        if recognized:
            return " ".join([item.get("display", "") for item in recognized]).strip()
        return ""


_azure_speech_batch_service = None


def get_azure_speech_batch_service() -> AzureSpeechBatchService:
    global _azure_speech_batch_service
    if _azure_speech_batch_service is None:
        _azure_speech_batch_service = AzureSpeechBatchService()
    return _azure_speech_batch_service
