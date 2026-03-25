from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.job import Job, JobStatus
from app.routers import upload


class DummyUploadFile:
    def __init__(self, filename: str, content_type: str, data: bytes, size: int | None = None):
        self.filename = filename
        self.content_type = content_type
        self._data = data
        self.size = len(data) if size is None else size

    async def read(self) -> bytes:
        return self._data


@pytest.mark.asyncio
async def test_upload_audio_stores_audio_file_without_extraction(db_session, monkeypatch):
    blob_service = MagicMock()
    blob_service.upload_file.return_value = ("blob-audio", "https://example.com/blob-audio")

    audio_extractor = MagicMock()
    audio_extractor.is_video_file.return_value = False

    monkeypatch.setattr(upload, "get_blob_storage_service", lambda: blob_service)
    monkeypatch.setattr(upload, "get_audio_extractor", lambda: audio_extractor)

    file = DummyUploadFile("meeting.wav", "audio/wav", b"audio-bytes")

    response = await upload.upload_audio(file=file, db=db_session)

    job = db_session.query(Job).one()
    assert response["status"] == JobStatus.UPLOADED.value
    assert response["blob_url"] == "https://example.com/blob-audio"
    assert "audio extracted from video" not in response["message"]
    assert job.filename == "meeting.wav"
    assert job.status == JobStatus.UPLOADED.value
    blob_service.upload_file.assert_called_once_with(
        file_data=b"audio-bytes",
        filename="meeting.wav",
        content_type="audio/wav",
    )


@pytest.mark.asyncio
async def test_upload_audio_rejects_oversized_file(db_session):
    file = DummyUploadFile(
        "too-large.wav",
        "audio/wav",
        b"x",
        size=upload.settings.max_file_size_bytes + 1,
    )

    with pytest.raises(HTTPException) as exc_info:
        await upload.upload_audio(file=file, db=db_session)

    assert exc_info.value.status_code == 400
    assert "File size exceeds maximum allowed size" in exc_info.value.detail
    assert db_session.query(Job).count() == 0


@pytest.mark.asyncio
async def test_upload_audio_rejects_invalid_content_type(db_session):
    file = DummyUploadFile("notes.txt", "text/plain", b"hello")

    with pytest.raises(HTTPException) as exc_info:
        await upload.upload_audio(file=file, db=db_session)

    assert exc_info.value.status_code == 400
    assert "Invalid file format" in exc_info.value.detail
    assert db_session.query(Job).count() == 0


@pytest.mark.asyncio
async def test_upload_audio_extracts_audio_from_video(db_session, monkeypatch):
    blob_service = MagicMock()
    blob_service.upload_file.return_value = ("blob-video", "https://example.com/blob-video")

    audio_extractor = MagicMock()
    audio_extractor.is_video_file.return_value = True
    audio_extractor.extract_audio.return_value = (b"wav-bytes", "meeting.wav")

    monkeypatch.setattr(upload, "get_blob_storage_service", lambda: blob_service)
    monkeypatch.setattr(upload, "get_audio_extractor", lambda: audio_extractor)

    file = DummyUploadFile("meeting.mp4", "video/mp4", b"video-bytes")

    response = await upload.upload_audio(file=file, db=db_session)

    job = db_session.query(Job).one()
    assert response["status"] == JobStatus.UPLOADED.value
    assert "audio extracted from video" in response["message"]
    assert job.status == JobStatus.UPLOADED.value
    blob_service.upload_file.assert_called_once_with(
        file_data=b"wav-bytes",
        filename="meeting.wav",
        content_type="audio/wav",
    )


@pytest.mark.asyncio
async def test_upload_audio_marks_job_failed_when_extraction_fails(db_session, monkeypatch):
    blob_service = MagicMock()

    audio_extractor = MagicMock()
    audio_extractor.is_video_file.return_value = True
    audio_extractor.extract_audio.side_effect = RuntimeError("ffmpeg failed")

    monkeypatch.setattr(upload, "get_blob_storage_service", lambda: blob_service)
    monkeypatch.setattr(upload, "get_audio_extractor", lambda: audio_extractor)

    file = DummyUploadFile("meeting.mp4", "video/mp4", b"video-bytes")

    with pytest.raises(HTTPException) as exc_info:
        await upload.upload_audio(file=file, db=db_session)

    job = db_session.query(Job).one()
    assert exc_info.value.status_code == 500
    assert "Failed to extract audio from video" in exc_info.value.detail
    assert job.status == JobStatus.FAILED.value
    assert "ffmpeg failed" in job.error_message
    blob_service.upload_file.assert_not_called()


@pytest.mark.asyncio
async def test_upload_audio_marks_job_failed_when_blob_upload_fails(db_session, monkeypatch):
    blob_service = MagicMock()
    blob_service.upload_file.side_effect = RuntimeError("blob failure")

    audio_extractor = MagicMock()
    audio_extractor.is_video_file.return_value = False

    monkeypatch.setattr(upload, "get_blob_storage_service", lambda: blob_service)
    monkeypatch.setattr(upload, "get_audio_extractor", lambda: audio_extractor)

    file = DummyUploadFile("meeting.wav", "audio/wav", b"audio-bytes")

    with pytest.raises(HTTPException) as exc_info:
        await upload.upload_audio(file=file, db=db_session)

    job = db_session.query(Job).one()
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to upload file"
    assert job.status == JobStatus.FAILED.value
    assert job.error_message == "blob failure"
