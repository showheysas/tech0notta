import json
import sys
from datetime import date, datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import sessionmaker

from app.models.job import Job, JobStatus
from app.models.task import TaskPriority
from app.routers import jobs


def install_fake_module(monkeypatch, module_name: str, **attrs):
    module = ModuleType(module_name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


def create_job(db_session, **overrides) -> Job:
    job = Job(
        job_id=overrides.pop("job_id", f"job-{db_session.query(Job).count() + 1}"),
        filename=overrides.pop("filename", "meeting.wav"),
        file_size=overrides.pop("file_size", 123),
        status=overrides.pop("status", JobStatus.PENDING.value),
        summary=overrides.pop("summary", None),
        transcription=overrides.pop("transcription", None),
        job_metadata=overrides.pop("job_metadata", None),
        extracted_tasks=overrides.pop("extracted_tasks", None),
        meeting_date=overrides.pop("meeting_date", None),
        created_at=overrides.pop("created_at", datetime(2026, 3, 22, 12, 0, 0)),
        updated_at=overrides.pop("updated_at", datetime(2026, 3, 22, 12, 0, 0)),
        transcription_job_id=overrides.pop("transcription_job_id", None),
    )
    for key, value in overrides.items():
        setattr(job, key, value)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def build_test_session_factory(db_session):
    connection = db_session.connection()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    return factory


def refresh_job(db_session, job_id: str) -> Job:
    db_session.expire_all()
    return db_session.query(Job).filter(Job.job_id == job_id).one()


class DummyMetadata:
    def __init__(self, meeting_date: str | None):
        self.meeting_date = meeting_date

    def to_dict(self):
        return {
            "mtg_name": "Weekly Sync",
            "participants": ["alice"],
            "meeting_date": self.meeting_date,
            "project_id": "project-1",
        }


def test_job_response_from_job_ignores_invalid_json_payloads(db_session):
    job = create_job(
        db_session,
        job_id="job-invalid-json",
        job_metadata="{bad-json",
        extracted_tasks="{bad-json",
    )

    result = jobs.JobResponse.from_job(job)

    assert result.metadata is None
    assert result.extracted_tasks is None


def test_get_job_stats_counts_each_status(db_session, test_user):
    create_job(db_session, job_id="job-1", status=JobStatus.SUMMARIZED.value)
    create_job(db_session, job_id="job-2", status=JobStatus.EXTRACTING_METADATA.value)
    create_job(db_session, job_id="job-3", status=JobStatus.REVIEWING.value)
    create_job(db_session, job_id="job-4", status=JobStatus.COMPLETED.value)
    create_job(db_session, job_id="job-5", status=JobStatus.FAILED.value)

    result = jobs.get_job_stats(current_user=test_user, db=db_session)

    assert result.total_meetings == 5
    assert result.pending_approval == 2
    assert result.reviewing == 1
    assert result.synced_notion == 1


def test_list_jobs_applies_status_filter_without_authorization_filter(db_session, monkeypatch):
    create_job(db_session, job_id="job-completed", status=JobStatus.COMPLETED.value)
    create_job(db_session, job_id="job-failed", status=JobStatus.FAILED.value)
    install_fake_module(
        monkeypatch,
        "app.services.transcription_service",
        check_and_update_transcription_status=lambda job, db: job,
    )

    result = jobs.list_jobs(
        status=JobStatus.COMPLETED.value,
        authorized_ids=None,
        db=db_session,
    )

    assert [item.job_id for item in result] == ["job-completed"]


def test_list_jobs_ignores_auto_update_errors_and_returns_results(db_session, monkeypatch):
    create_job(
        db_session,
        job_id="job-transcribing",
        status=JobStatus.TRANSCRIBING.value,
        job_metadata=json.dumps({"project_id": "project-1"}),
    )
    install_fake_module(
        monkeypatch,
        "app.services.transcription_service",
        check_and_update_transcription_status=lambda job, db: (_ for _ in ()).throw(RuntimeError("update failed")),
    )

    result = jobs.list_jobs(authorized_ids=None, db=db_session)

    assert [item.job_id for item in result] == ["job-transcribing"]


def test_update_job_customer_returns_payload(db_session, test_user):
    job = create_job(db_session, job_id="job-customer")

    result = jobs.update_job_customer(
        job_id=job.job_id,
        data=jobs.JobCustomerUpdate(customer_id="customer-1"),
        current_user=test_user,
        db=db_session,
    )

    assert result["job_id"] == job.job_id
    assert result["customer_id"] == "customer-1"


def test_update_job_customer_rejects_missing_job(db_session, test_user):
    with pytest.raises(HTTPException) as exc_info:
        jobs.update_job_customer(
            job_id="missing-job",
            data=jobs.JobCustomerUpdate(customer_id="customer-1"),
            current_user=test_user,
            db=db_session,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_extract_metadata_rejects_missing_job(db_session, test_user):
    with pytest.raises(HTTPException) as exc_info:
        await jobs.extract_metadata(
            job_id="missing-job",
            background_tasks=BackgroundTasks(),
            current_user=test_user,
            db=db_session,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_extract_metadata_reraises_http_exception_from_task_service(db_session, test_user, monkeypatch):
    job = create_job(
        db_session,
        job_id="job-http-exc",
        status=JobStatus.SUMMARIZED.value,
        summary="summary",
        transcription="transcript",
    )
    metadata_service = SimpleNamespace(extract_metadata=AsyncMock(return_value=DummyMetadata("2026-03-20")))
    task_service = SimpleNamespace(
        extract_tasks=AsyncMock(side_effect=HTTPException(status_code=418, detail="stop"))
    )
    install_fake_module(
        monkeypatch,
        "app.services.metadata_service",
        get_metadata_service=lambda: metadata_service,
    )
    install_fake_module(
        monkeypatch,
        "app.services.task_service",
        get_task_service=lambda: task_service,
    )

    with pytest.raises(HTTPException) as exc_info:
        await jobs.extract_metadata(
            job_id=job.job_id,
            background_tasks=BackgroundTasks(),
            current_user=test_user,
            db=db_session,
        )

    updated_job = refresh_job(db_session, job.job_id)
    assert exc_info.value.status_code == 418
    assert updated_job.status == JobStatus.EXTRACTING_METADATA.value


def test_update_job_rejects_missing_job(db_session, test_user):
    with pytest.raises(HTTPException) as exc_info:
        jobs.update_job(
            job_id="missing-job",
            data=jobs.JobUpdateRequest(summary="updated"),
            current_user=test_user,
            db=db_session,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_process_approval_background_returns_when_job_missing(db_session, monkeypatch):
    session_factory = build_test_session_factory(db_session)
    monkeypatch.setattr("app.database.SessionLocal", lambda: session_factory())

    await jobs.process_approval_background(
        job_id="missing-job",
        request=jobs.JobApproveRequest(register_tasks=True, send_notifications=False),
    )


@pytest.mark.asyncio
async def test_process_approval_background_skips_task_registration_when_disabled(db_session, monkeypatch):
    job = create_job(
        db_session,
        job_id="job-skip-register",
        status=JobStatus.CREATING_NOTION.value,
        summary="summary",
        job_metadata=json.dumps({"mtg_name": "Meeting"}),
        extracted_tasks=json.dumps([{"title": "task-1"}]),
    )
    session_factory = build_test_session_factory(db_session)
    monkeypatch.setattr("app.database.SessionLocal", lambda: session_factory())
    notion_client = SimpleNamespace(create_meeting_record=AsyncMock(return_value=None))
    install_fake_module(
        monkeypatch,
        "app.services.notion_client",
        get_notion_client=lambda: notion_client,
    )

    await jobs.process_approval_background(
        job_id=job.job_id,
        request=jobs.JobApproveRequest(register_tasks=False, send_notifications=False),
    )

    updated_job = refresh_job(db_session, job.job_id)
    assert updated_job.status == JobStatus.COMPLETED.value
    assert updated_job.error_message is None


@pytest.mark.asyncio
async def test_process_approval_background_skips_task_registration_without_extracted_tasks(db_session, monkeypatch):
    job = create_job(
        db_session,
        job_id="job-no-tasks",
        status=JobStatus.CREATING_NOTION.value,
        summary="summary",
        job_metadata=None,
        extracted_tasks=None,
    )
    session_factory = build_test_session_factory(db_session)
    monkeypatch.setattr("app.database.SessionLocal", lambda: session_factory())
    notion_client = SimpleNamespace(create_meeting_record=AsyncMock(return_value=None))
    install_fake_module(
        monkeypatch,
        "app.services.notion_client",
        get_notion_client=lambda: notion_client,
    )

    await jobs.process_approval_background(
        job_id=job.job_id,
        request=jobs.JobApproveRequest(register_tasks=True, send_notifications=False),
    )

    updated_job = refresh_job(db_session, job.job_id)
    assert updated_job.status == JobStatus.COMPLETED.value
    assert updated_job.error_message is None


@pytest.mark.asyncio
async def test_process_approval_background_handles_invalid_metadata_and_register_failure(db_session, monkeypatch):
    job = create_job(
        db_session,
        job_id="job-register-warning",
        status=JobStatus.CREATING_NOTION.value,
        summary="summary",
        job_metadata="{bad-json",
        extracted_tasks=json.dumps(
            [
                {
                    "title": "task-1",
                    "description": "desc",
                    "assignee": "alice",
                    "due_date": "bad-date",
                    "priority": TaskPriority.LOW.value,
                }
            ]
        ),
    )
    session_factory = build_test_session_factory(db_session)
    monkeypatch.setattr("app.database.SessionLocal", lambda: session_factory())

    notion_client = SimpleNamespace(
        create_meeting_record=AsyncMock(return_value={"id": "page-1", "url": "https://example.com/page-1"})
    )
    fake_task_service = SimpleNamespace(
        register_tasks=AsyncMock(side_effect=RuntimeError("register failed"))
    )
    install_fake_module(
        monkeypatch,
        "app.services.notion_client",
        get_notion_client=lambda: notion_client,
    )
    install_fake_module(
        monkeypatch,
        "app.services.task_service",
        get_task_service=lambda: fake_task_service,
    )

    await jobs.process_approval_background(
        job_id=job.job_id,
        request=jobs.JobApproveRequest(register_tasks=True, send_notifications=False, project_id="project-1"),
    )

    updated_job = refresh_job(db_session, job.job_id)
    register_request = fake_task_service.register_tasks.await_args.args[0]

    assert updated_job.status == JobStatus.COMPLETED.value
    assert updated_job.error_message.startswith("WARNING:")
    assert register_request.tasks[0].priority == TaskPriority.LOW
    assert register_request.tasks[0].due_date == date.today() + timedelta(days=7)


@pytest.mark.asyncio
async def test_process_approval_background_handles_notification_failure(db_session, monkeypatch):
    job = create_job(
        db_session,
        job_id="job-slack-failure",
        status=JobStatus.CREATING_NOTION.value,
        summary="summary",
        job_metadata=json.dumps({"mtg_name": "Meeting"}),
    )
    session_factory = build_test_session_factory(db_session)
    monkeypatch.setattr("app.database.SessionLocal", lambda: session_factory())

    notion_client = SimpleNamespace(
        create_meeting_record=AsyncMock(return_value={"id": "page-1", "url": "https://example.com/page-1"})
    )
    slack_service = SimpleNamespace(
        send_meeting_approved_notification=AsyncMock(side_effect=RuntimeError("slack down"))
    )
    install_fake_module(
        monkeypatch,
        "app.services.notion_client",
        get_notion_client=lambda: notion_client,
    )
    install_fake_module(
        monkeypatch,
        "app.services.slack_service",
        get_slack_service=lambda: slack_service,
    )

    await jobs.process_approval_background(
        job_id=job.job_id,
        request=jobs.JobApproveRequest(register_tasks=False, send_notifications=True),
    )

    updated_job = refresh_job(db_session, job.job_id)
    assert updated_job.status == JobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_process_approval_background_handles_outer_exception(monkeypatch):
    class ExplodingDb:
        def __init__(self):
            self.closed = False

        def query(self, *args, **kwargs):
            raise RuntimeError("db failed")

        def close(self):
            self.closed = True

    fake_db = ExplodingDb()
    monkeypatch.setattr("app.database.SessionLocal", lambda: fake_db)

    await jobs.process_approval_background(
        job_id="job-outer-failure",
        request=jobs.JobApproveRequest(register_tasks=False, send_notifications=False),
    )

    assert fake_db.closed is True


@pytest.mark.asyncio
async def test_approve_job_rejects_missing_job(db_session, test_user):
    with pytest.raises(HTTPException) as exc_info:
        await jobs.approve_job(
            job_id="missing-job",
            request=jobs.JobApproveRequest(),
            background_tasks=BackgroundTasks(),
            current_user=test_user,
            db=db_session,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_approve_job_rejects_invalid_status(db_session, test_user):
    job = create_job(db_session, job_id="job-invalid-status", status=JobStatus.COMPLETED.value)

    with pytest.raises(HTTPException) as exc_info:
        await jobs.approve_job(
            job_id=job.job_id,
            request=jobs.JobApproveRequest(),
            background_tasks=BackgroundTasks(),
            current_user=test_user,
            db=db_session,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_approve_job_ignores_invalid_metadata_json_when_project_id_missing(db_session, test_user):
    job = create_job(
        db_session,
        job_id="job-invalid-metadata",
        status=JobStatus.REVIEWING.value,
        job_metadata="{bad-json",
    )
    background_tasks = BackgroundTasks()

    result = await jobs.approve_job(
        job_id=job.job_id,
        request=jobs.JobApproveRequest(project_id=None),
        background_tasks=background_tasks,
        current_user=test_user,
        db=db_session,
    )

    assert result.status == "processing"
    assert background_tasks.tasks[0].args[1].project_id is None


@pytest.mark.asyncio
async def test_debug_notion_task_config_reports_service_states(monkeypatch):
    install_fake_module(
        monkeypatch,
        "app.config",
        settings=SimpleNamespace(
            NOTION_API_KEY="secret",
            NOTION_DATABASE_ID="database",
            NOTION_TASK_DB_ID="task-db-123456",
            NOTION_PROJECT_DB_ID="project-db",
            NOTION_USER_DB_ID="user-db",
        ),
    )
    install_fake_module(
        monkeypatch,
        "app.services.notion_task_service",
        get_notion_task_service=lambda: SimpleNamespace(enabled=True),
    )
    install_fake_module(
        monkeypatch,
        "app.services.notion_client",
        get_notion_service=lambda: SimpleNamespace(enabled=False),
    )

    result = await jobs.debug_notion_task_config()

    assert result["notion_api_key_set"] is True
    assert result["notion_task_service_enabled"] is True
    assert result["notion_service_enabled"] is False


@pytest.mark.asyncio
async def test_debug_notion_task_config_reports_lookup_errors(monkeypatch):
    install_fake_module(
        monkeypatch,
        "app.config",
        settings=SimpleNamespace(
            NOTION_API_KEY="",
            NOTION_DATABASE_ID="",
            NOTION_TASK_DB_ID="",
            NOTION_PROJECT_DB_ID="",
            NOTION_USER_DB_ID="",
        ),
    )
    install_fake_module(
        monkeypatch,
        "app.services.notion_task_service",
        get_notion_task_service=lambda: (_ for _ in ()).throw(RuntimeError("task service down")),
    )
    install_fake_module(
        monkeypatch,
        "app.services.notion_client",
        get_notion_service=lambda: (_ for _ in ()).throw(RuntimeError("notion service down")),
    )

    result = await jobs.debug_notion_task_config()

    assert "task service down" in result["notion_task_service_error"]
    assert "notion service down" in result["notion_service_error"]


def test_get_job_returns_job_response(db_session, test_user):
    job = create_job(db_session, job_id="job-get")

    result = jobs.get_job(job_id=job.job_id, current_user=test_user, db=db_session)

    assert result.job_id == "job-get"


def test_get_job_rejects_missing_job(db_session, test_user):
    with pytest.raises(HTTPException) as exc_info:
        jobs.get_job(job_id="missing-job", current_user=test_user, db=db_session)

    assert exc_info.value.status_code == 404
