import json
import sys
from datetime import date, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import sessionmaker

from app.models.job import Job, JobStatus
from app.models.task import ExtractedTask, TaskExtractResponse
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


class DummyMetadata:
    def __init__(self, meeting_date: str, **extra):
        self.meeting_date = meeting_date
        self._data = {
            "mtg_name": extra.get("mtg_name", "定例会"),
            "participants": extra.get("participants", ["田中"]),
            "company_name": extra.get("company_name", "Tech0"),
            "meeting_date": meeting_date,
            "meeting_type": extra.get("meeting_type", "定例"),
            "project": extra.get("project", "Project X"),
            "project_id": extra.get("project_id"),
            "key_stakeholders": extra.get("key_stakeholders", []),
            "key_team": extra.get("key_team"),
            "search_keywords": extra.get("search_keywords"),
            "is_knowledge": extra.get("is_knowledge", False),
            "materials_url": extra.get("materials_url"),
            "notes": extra.get("notes"),
            "related_meetings": extra.get("related_meetings", []),
        }

    def to_dict(self):
        return self._data


def build_test_session_factory(db_session):
    connection = db_session.connection()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    return factory


def refresh_job(db_session, job_id: str) -> Job:
    db_session.expire_all()
    return db_session.query(Job).filter(Job.job_id == job_id).one()


def test_list_jobs_filters_authorized_projects_and_updates_transcribing_jobs(db_session, monkeypatch):
    transcribing_job = create_job(
        db_session,
        job_id="job-transcribing",
        status=JobStatus.TRANSCRIBING.value,
        job_metadata=json.dumps({"project_id": "project-1"}, ensure_ascii=False),
    )
    create_job(
        db_session,
        job_id="job-other",
        status=JobStatus.COMPLETED.value,
        job_metadata=json.dumps({"project_id": "project-2"}, ensure_ascii=False),
    )
    called_job_ids = []

    def fake_check_and_update(job, db):
        called_job_ids.append(job.job_id)
        return job

    install_fake_module(
        monkeypatch,
        "app.services.transcription_service",
        check_and_update_transcription_status=fake_check_and_update,
    )

    result = jobs.list_jobs(authorized_ids={"project-1"}, db=db_session)

    assert [item.job_id for item in result] == [transcribing_job.job_id]
    assert called_job_ids == ["job-transcribing"]


@pytest.mark.asyncio
async def test_extract_metadata_rejects_job_without_summary(db_session, test_user):
    job = create_job(db_session, job_id="job-no-summary", summary=None)

    with pytest.raises(HTTPException) as exc_info:
        await jobs.extract_metadata(
            job_id=job.job_id,
            background_tasks=BackgroundTasks(),
            current_user=test_user,
            db=db_session,
        )

    assert exc_info.value.status_code == 400
    assert "要約が完了していません" in exc_info.value.detail


@pytest.mark.asyncio
async def test_extract_metadata_updates_job_with_metadata_and_tasks(db_session, test_user, monkeypatch):
    job = create_job(
        db_session,
        job_id="job-success",
        summary="会議要約",
        transcription="文字起こし",
    )
    metadata = DummyMetadata("2026-03-20", project_id="project-1")
    metadata_service = SimpleNamespace(extract_metadata=AsyncMock(return_value=metadata))
    task_service = SimpleNamespace(
        extract_tasks=AsyncMock(
            return_value=TaskExtractResponse(
                job_id=job.job_id,
                tasks=[
                    ExtractedTask(
                        title="議事録整理",
                        description="詳細",
                        assignee="田中",
                        due_date=date(2026, 3, 27),
                        is_abstract=False,
                    )
                ],
            )
        )
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

    result = await jobs.extract_metadata(
        job_id=job.job_id,
        background_tasks=BackgroundTasks(),
        current_user=test_user,
        db=db_session,
    )

    updated_job = refresh_job(db_session, job.job_id)
    assert result.status == JobStatus.REVIEWING.value
    assert updated_job.status == JobStatus.REVIEWING.value
    assert updated_job.meeting_date == date(2026, 3, 20)
    assert json.loads(updated_job.job_metadata)["project_id"] == "project-1"
    assert json.loads(updated_job.extracted_tasks)[0]["title"] == "議事録整理"


@pytest.mark.asyncio
async def test_extract_metadata_marks_job_failed_when_service_raises(db_session, test_user, monkeypatch):
    job = create_job(
        db_session,
        job_id="job-failure",
        summary="会議要約",
        transcription="文字起こし",
    )
    metadata_service = SimpleNamespace(extract_metadata=AsyncMock(side_effect=RuntimeError("metadata failed")))

    install_fake_module(
        monkeypatch,
        "app.services.metadata_service",
        get_metadata_service=lambda: metadata_service,
    )

    with pytest.raises(HTTPException) as exc_info:
        await jobs.extract_metadata(
            job_id=job.job_id,
            background_tasks=BackgroundTasks(),
            current_user=test_user,
            db=db_session,
        )

    updated_job = refresh_job(db_session, job.job_id)
    assert exc_info.value.status_code == 500
    assert updated_job.status == JobStatus.FAILED.value
    assert updated_job.error_message == "metadata failed"


def test_update_job_rejects_status_outside_reviewing_or_summarized(db_session, test_user):
    job = create_job(db_session, job_id="job-completed", status=JobStatus.COMPLETED.value)

    with pytest.raises(HTTPException) as exc_info:
        jobs.update_job(
            job_id=job.job_id,
            data=jobs.JobUpdateRequest(summary="updated"),
            current_user=test_user,
            db=db_session,
        )

    assert exc_info.value.status_code == 400
    assert "更新できません" in exc_info.value.detail


def test_update_job_updates_summary_metadata_and_ignores_invalid_meeting_date(db_session, test_user):
    job = create_job(db_session, job_id="job-reviewing", status=JobStatus.REVIEWING.value)

    result = jobs.update_job(
        job_id=job.job_id,
        data=jobs.JobUpdateRequest(
            summary="更新後要約",
            metadata=jobs.MetadataResponse(mtg_name="定例会", meeting_date="invalid-date"),
            extracted_tasks=[jobs.ExtractedTaskResponse(title="確認作業")],
        ),
        current_user=test_user,
        db=db_session,
    )

    updated_job = refresh_job(db_session, job.job_id)
    assert result.summary == "更新後要約"
    assert updated_job.summary == "更新後要約"
    assert json.loads(updated_job.job_metadata)["mtg_name"] == "定例会"
    assert updated_job.meeting_date is None
    assert json.loads(updated_job.extracted_tasks)[0]["title"] == "確認作業"


@pytest.mark.asyncio
async def test_approve_job_sets_creating_notion_and_queues_background_task(db_session, test_user):
    job = create_job(
        db_session,
        job_id="job-approve",
        status=JobStatus.REVIEWING.value,
        job_metadata=json.dumps({"project_id": "project-1"}, ensure_ascii=False),
    )
    background_tasks = BackgroundTasks()
    request = jobs.JobApproveRequest(register_tasks=True, send_notifications=True)

    result = await jobs.approve_job(
        job_id=job.job_id,
        request=request,
        background_tasks=background_tasks,
        current_user=test_user,
        db=db_session,
    )

    updated_job = refresh_job(db_session, job.job_id)
    assert result.status == "processing"
    assert updated_job.status == JobStatus.CREATING_NOTION.value
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is jobs.process_approval_background
    assert background_tasks.tasks[0].args[0] == job.job_id
    assert background_tasks.tasks[0].args[1].project_id == "project-1"


@pytest.mark.asyncio
async def test_process_approval_background_registers_tasks_and_marks_job_completed(db_session, monkeypatch):
    job = create_job(
        db_session,
        job_id="job-background",
        status=JobStatus.CREATING_NOTION.value,
        summary="要約",
        job_metadata=json.dumps({"mtg_name": "定例会", "project_id": "project-1"}, ensure_ascii=False),
        extracted_tasks=json.dumps(
            [
                {
                    "title": "資料送付",
                    "description": "送付する",
                    "assignee": "田中",
                    "due_date": "2026-03-25",
                    "priority": "高",
                    "is_abstract": False,
                }
            ],
            ensure_ascii=False,
        ),
    )

    session_factory = build_test_session_factory(db_session)
    monkeypatch.setattr("app.database.SessionLocal", lambda: session_factory())

    notion_client = SimpleNamespace(
        create_meeting_record=AsyncMock(return_value={"id": "page-1", "url": "https://notion.example/page-1"}),
        update_meeting_project_relation=AsyncMock(),
        update_meeting_tasks_relation=AsyncMock(),
    )
    fake_task_service = SimpleNamespace(
        register_tasks=AsyncMock(
            return_value=SimpleNamespace(registered_count=1, task_ids=["task-1"])
        )
    )
    slack_service = SimpleNamespace(
        send_meeting_approved_notification=AsyncMock()
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
    install_fake_module(
        monkeypatch,
        "app.services.slack_service",
        get_slack_service=lambda: slack_service,
    )

    await jobs.process_approval_background(
        job_id=job.job_id,
        request=jobs.JobApproveRequest(
            register_tasks=True,
            send_notifications=True,
            project_id="project-1",
        ),
    )

    updated_job = refresh_job(db_session, job.job_id)
    register_request = fake_task_service.register_tasks.await_args.args[0]

    assert updated_job.status == JobStatus.COMPLETED.value
    assert updated_job.notion_page_url == "https://notion.example/page-1"
    assert updated_job.error_message is None
    assert register_request.tasks[0].priority.value == "高"
    notion_client.update_meeting_project_relation.assert_awaited_once()
    notion_client.update_meeting_tasks_relation.assert_awaited_once()
    slack_service.send_meeting_approved_notification.assert_awaited_once()
