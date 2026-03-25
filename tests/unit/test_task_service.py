import json
import sys
from datetime import date, datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.task import (
    ExtractedTask,
    TaskDecomposeRequest,
    TaskExtractRequest,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
)
from app.services.task_service import TaskService


def build_openai_service(content: str):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    create = MagicMock(return_value=response)
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
async def test_extract_tasks_applies_defaults_and_invalid_due_date_fallback(monkeypatch):
    content = json.dumps(
        {
            "tasks": [
                {
                    "title": "要件整理",
                    "assignee": "   ",
                    "due_date": "invalid-date",
                    "is_abstract": True,
                },
                {
                    "title": "資料共有",
                    "assignee": "田中",
                    "due_date": "2026-03-25",
                },
            ]
        }
    )
    monkeypatch.setattr(
        "app.services.task_service.get_azure_openai_service",
        lambda: build_openai_service(content),
    )
    service = TaskService()
    request = TaskExtractRequest(
        job_id="job-1",
        summary="summary",
        meeting_date=date(2026, 3, 20),
    )

    result = await service.extract_tasks(request)

    assert result.job_id == "job-1"
    assert result.tasks[0].assignee == "未割り当て"
    assert result.tasks[0].due_date == date(2026, 3, 27)
    assert result.tasks[0].is_abstract is True
    assert result.tasks[1].assignee == "田中"
    assert result.tasks[1].due_date == date(2026, 3, 25)


@pytest.mark.asyncio
async def test_extract_tasks_raises_when_openai_response_is_invalid_json(monkeypatch):
    monkeypatch.setattr(
        "app.services.task_service.get_azure_openai_service",
        lambda: build_openai_service("{invalid"),
    )
    service = TaskService()
    request = TaskExtractRequest(
        job_id="job-1",
        summary="summary",
        meeting_date=date(2026, 3, 20),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.extract_tasks(request)

    assert exc_info.value.status_code == 500
    assert "AI応答の形式が不正" in exc_info.value.detail


@pytest.mark.asyncio
async def test_decompose_task_rejects_less_than_three_subtasks(monkeypatch):
    content = json.dumps(
        {
            "subtasks": [
                {"title": "調査", "description": "desc", "order": 1},
                {"title": "整理", "description": "desc", "order": 2},
            ]
        }
    )
    monkeypatch.setattr(
        "app.services.task_service.get_azure_openai_service",
        lambda: build_openai_service(content),
    )
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.decompose_task(
            TaskDecomposeRequest(
                task_title="企画作成",
                task_description="詳細あり",
                parent_due_date=date(2026, 3, 31),
            )
        )

    assert exc_info.value.status_code == 500
    assert "最低3個必要" in exc_info.value.detail


@pytest.mark.asyncio
async def test_decompose_task_limits_subtasks_to_five_and_reindexes(monkeypatch):
    content = json.dumps(
        {
            "subtasks": [
                {"title": f"task-{index}", "description": "desc", "order": index + 10}
                for index in range(6)
            ]
        }
    )
    monkeypatch.setattr(
        "app.services.task_service.get_azure_openai_service",
        lambda: build_openai_service(content),
    )
    service = TaskService()

    result = await service.decompose_task(
        TaskDecomposeRequest(
            task_title="企画作成",
            task_description=None,
            parent_due_date=date(2026, 3, 31),
        )
    )

    assert len(result.subtasks) == 5
    assert [subtask.order for subtask in result.subtasks] == [1, 2, 3, 4, 5]
    assert result.subtasks[0].title == "task-0"
    assert result.subtasks[-1].title == "task-4"


@pytest.mark.asyncio
async def test_get_tasks_sorts_by_priority_and_marks_overdue(monkeypatch):
    now = datetime(2026, 3, 22, 12, 0, 0)
    notion_tasks = ["low", "high", "completed"]

    parsed_map = {
        "low": {
            "id": "low",
            "title": "Low",
            "assignee": "A",
            "due_date": date(2026, 3, 25),
            "status": TaskStatus.NOT_STARTED,
            "priority": TaskPriority.LOW,
            "project_id": "project-1",
            "meeting_id": None,
            "parent_task_id": None,
            "completion_date": None,
            "notion_page_url": "https://example.com/low",
            "created_at": now,
            "updated_at": now,
        },
        "high": {
            "id": "high",
            "title": "High",
            "assignee": "B",
            "due_date": date.today() - timedelta(days=1),
            "status": TaskStatus.NOT_STARTED,
            "priority": TaskPriority.HIGH,
            "project_id": "project-1",
            "meeting_id": None,
            "parent_task_id": None,
            "completion_date": None,
            "notion_page_url": "https://example.com/high",
            "created_at": now,
            "updated_at": now,
        },
        "completed": {
            "id": "completed",
            "title": "Completed",
            "assignee": "C",
            "due_date": date.today() - timedelta(days=5),
            "status": TaskStatus.COMPLETED,
            "priority": TaskPriority.MEDIUM,
            "project_id": "project-1",
            "meeting_id": None,
            "parent_task_id": None,
            "completion_date": date.today() - timedelta(days=2),
            "notion_page_url": "https://example.com/completed",
            "created_at": now,
            "updated_at": now,
        },
    }

    notion_service = SimpleNamespace(
        query_tasks=AsyncMock(return_value=notion_tasks),
        parse_task_response=lambda key: parsed_map[key],
    )
    install_notion_task_service(monkeypatch, notion_service)

    service = TaskService()
    result = await service.get_tasks(sort_by="priority", sort_order="desc")

    assert [task.id for task in result] == ["high", "completed", "low"]
    assert result[0].is_overdue is True
    assert result[1].is_overdue is False


@pytest.mark.asyncio
async def test_update_task_rejects_empty_title():
    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.update_task("task-1", TaskUpdate(title="   "))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "タスク名は必須です"


@pytest.mark.asyncio
async def test_update_task_sets_completion_date_for_completed_status(monkeypatch):
    now = datetime(2026, 3, 22, 12, 0, 0)
    notion_service = SimpleNamespace(update_task=AsyncMock())
    install_notion_task_service(monkeypatch, notion_service)

    service = TaskService()
    service.get_task = AsyncMock(
        return_value=TaskResponse(
            id="task-1",
            title="Task",
            due_date=date(2026, 3, 31),
            status=TaskStatus.COMPLETED,
            priority=TaskPriority.MEDIUM,
            notion_page_url="https://example.com/task-1",
            created_at=now,
            updated_at=now,
        )
    )

    result = await service.update_task("task-1", TaskUpdate(status=TaskStatus.COMPLETED))

    assert result.status == TaskStatus.COMPLETED
    assert notion_service.update_task.await_count == 1
    assert notion_service.update_task.await_args.kwargs["completion_date"] == date.today()


@pytest.mark.asyncio
async def test_delete_task_converts_not_found_error_to_http_404(monkeypatch):
    notion_service = SimpleNamespace(delete_task=AsyncMock(side_effect=Exception("404 not found")))
    install_notion_task_service(monkeypatch, notion_service)

    service = TaskService()

    with pytest.raises(HTTPException) as exc_info:
        await service.delete_task("task-404")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "タスクが見つかりません"
