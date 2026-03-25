import json
import sys
from datetime import date, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import app.services.task_service as task_service_module
from app.models.task import (
    SubTaskItem,
    TaskDecomposeRequest,
    TaskExtractRequest,
    TaskPriority,
    TaskRegisterRequest,
    TaskStatus,
    TaskToRegister,
    TaskUpdate,
)
from app.services.task_service import TaskService


def build_openai_service(*, content: str | None = None, side_effect=None):
    create = MagicMock()
    if side_effect is not None:
        create.side_effect = side_effect
    else:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
        create.return_value = response

    return SimpleNamespace(
        deployment_name="test-deployment",
        client=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create)
            )
        ),
    )


def install_notion_task_service(monkeypatch, notion_service):
    module = ModuleType("app.services.notion_task_service")
    module.get_notion_task_service = lambda: notion_service
    monkeypatch.setitem(sys.modules, "app.services.notion_task_service", module)


@pytest.mark.asyncio
async def test_extract_tasks_wraps_unexpected_exception(monkeypatch):
    monkeypatch.setattr(
        "app.services.task_service.get_azure_openai_service",
        lambda: build_openai_service(side_effect=RuntimeError("openai boom")),
    )
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.extract_tasks(
            TaskExtractRequest(
                job_id="job-1",
                summary="summary",
                meeting_date=date(2026, 3, 20),
            )
        )

    assert exc_info.value.status_code == 500
    assert "openai boom" in exc_info.value.detail


@pytest.mark.asyncio
async def test_decompose_task_raises_when_openai_response_is_invalid_json(monkeypatch):
    monkeypatch.setattr(
        "app.services.task_service.get_azure_openai_service",
        lambda: build_openai_service(content="{bad-json"),
    )
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.decompose_task(
            TaskDecomposeRequest(
                task_title="parent",
                task_description="desc",
                parent_due_date=date(2026, 3, 31),
            )
        )

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_decompose_task_wraps_unexpected_exception(monkeypatch):
    monkeypatch.setattr(
        "app.services.task_service.get_azure_openai_service",
        lambda: build_openai_service(side_effect=RuntimeError("decompose boom")),
    )
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.decompose_task(
            TaskDecomposeRequest(
                task_title="parent",
                task_description=None,
                parent_due_date=date(2026, 3, 31),
            )
        )

    assert exc_info.value.status_code == 500
    assert "decompose boom" in exc_info.value.detail


@pytest.mark.asyncio
async def test_register_tasks_creates_parent_and_subtasks_and_skips_failed_task(monkeypatch):
    notion_service = SimpleNamespace(
        create_task=AsyncMock(
            side_effect=["parent-1", "subtask-1", RuntimeError("task failed")]
        )
    )
    install_notion_task_service(monkeypatch, notion_service)
    service = TaskService()

    request = TaskRegisterRequest(
        job_id="job-1",
        project_id="project-1",
        meeting_page_id="meeting-page-1",
        tasks=[
            TaskToRegister(
                title="parent task",
                description="desc",
                assignee="alice",
                due_date=date(2026, 3, 31),
                priority=TaskPriority.HIGH,
                subtasks=[SubTaskItem(title="child", description="sub", order=1)],
            ),
            TaskToRegister(
                title="broken task",
                description=None,
                assignee="bob",
                due_date=date(2026, 4, 1),
                priority=TaskPriority.LOW,
                subtasks=[],
            ),
        ],
    )

    result = await service.register_tasks(request)

    assert result.job_id == "job-1"
    assert result.registered_count == 2
    assert result.task_ids == ["parent-1", "subtask-1"]
    assert notion_service.create_task.await_count == 3
    assert notion_service.create_task.await_args_list[0].kwargs["meeting_page_id"] == "meeting-page-1"
    assert notion_service.create_task.await_args_list[1].kwargs["parent_task_id"] == "parent-1"


@pytest.mark.asyncio
async def test_register_tasks_wraps_unexpected_exception(monkeypatch):
    module = ModuleType("app.services.notion_task_service")
    module.get_notion_task_service = lambda: (_ for _ in ()).throw(RuntimeError("notion unavailable"))
    monkeypatch.setitem(sys.modules, "app.services.notion_task_service", module)
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.register_tasks(
            TaskRegisterRequest(
                job_id="job-1",
                tasks=[],
            )
        )

    assert exc_info.value.status_code == 500
    assert "notion unavailable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_tasks_wraps_unexpected_exception(monkeypatch):
    notion_service = SimpleNamespace(query_tasks=AsyncMock(side_effect=RuntimeError("query failed")))
    install_notion_task_service(monkeypatch, notion_service)
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.get_tasks()

    assert exc_info.value.status_code == 500
    assert "query failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_task_returns_response_for_completed_task(monkeypatch):
    now = datetime(2026, 3, 22, 12, 0, 0)
    notion_service = SimpleNamespace(
        get_task=AsyncMock(return_value="raw-task"),
        parse_task_response=lambda _: {
            "id": "task-1",
            "title": "Task",
            "assignee": "alice",
            "due_date": date.today(),
            "status": TaskStatus.COMPLETED,
            "priority": TaskPriority.MEDIUM,
            "project_id": "project-1",
            "meeting_id": "meeting-1",
            "parent_task_id": None,
            "completion_date": date.today(),
            "notion_page_url": "https://example.com/task-1",
            "created_at": now,
            "updated_at": now,
        },
    )
    install_notion_task_service(monkeypatch, notion_service)
    service = TaskService()

    result = await service.get_task("task-1")

    assert result.id == "task-1"
    assert result.status == TaskStatus.COMPLETED
    assert result.is_overdue is False


@pytest.mark.asyncio
async def test_get_task_converts_missing_task_to_http_404(monkeypatch):
    notion_service = SimpleNamespace(get_task=AsyncMock(side_effect=RuntimeError("404 not found")))
    install_notion_task_service(monkeypatch, notion_service)
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.get_task("task-404")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_task_converts_missing_task_to_http_404(monkeypatch):
    notion_service = SimpleNamespace(update_task=AsyncMock(side_effect=RuntimeError("404 not found")))
    install_notion_task_service(monkeypatch, notion_service)
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.update_task("task-404", TaskUpdate(title="valid"))

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_task_wraps_unexpected_exception(monkeypatch):
    notion_service = SimpleNamespace(update_task=AsyncMock(side_effect=RuntimeError("update failed")))
    install_notion_task_service(monkeypatch, notion_service)
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.update_task("task-1", TaskUpdate(title="valid"))

    assert exc_info.value.status_code == 500
    assert "update failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_delete_task_succeeds(monkeypatch):
    notion_service = SimpleNamespace(delete_task=AsyncMock(return_value=None))
    install_notion_task_service(monkeypatch, notion_service)
    service = TaskService()

    await service.delete_task("task-1")

    notion_service.delete_task.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_delete_task_wraps_unexpected_exception(monkeypatch):
    notion_service = SimpleNamespace(delete_task=AsyncMock(side_effect=RuntimeError("delete failed")))
    install_notion_task_service(monkeypatch, notion_service)
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.delete_task("task-1")

    assert exc_info.value.status_code == 500
    assert "delete failed" in exc_info.value.detail


def test_get_task_service_returns_singleton(monkeypatch):
    monkeypatch.setattr(task_service_module, "_task_service", None)

    first = task_service_module.get_task_service()
    second = task_service_module.get_task_service()

    assert isinstance(first, TaskService)
    assert first is second
