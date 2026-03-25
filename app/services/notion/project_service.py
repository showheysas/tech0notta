"""Notion 案件 CRUD 操作"""
import logging
from typing import Optional

from app.services.notion.base import NotionServiceBase

logger = logging.getLogger(__name__)


class NotionProjectService(NotionServiceBase):
    """案件の一覧取得・作成を担当するサービス"""

    async def list_projects(self) -> list[dict]:
        """Notion案件DBから案件一覧を取得する"""
        if not self.enabled or not self.project_database_id:
            logger.warning("Project DB is not configured.")
            return []

        try:
            results = self.client.databases.query(
                database_id=self.project_database_id,
                sorts=[{"property": "案件名", "direction": "ascending"}]
            )

            projects = []
            for page in results.get("results", []):
                props = page.get("properties", {})
                project = {
                    "id": page["id"],
                    "url": page.get("url", ""),
                }

                title_prop = props.get("案件名", {})
                if title_prop.get("title"):
                    project["name"] = "".join(
                        t.get("plain_text", "") for t in title_prop["title"]
                    )
                else:
                    project["name"] = ""

                status_prop = props.get("ステータス", {})
                if status_prop.get("select"):
                    project["status"] = status_prop["select"].get("name", "")
                else:
                    project["status"] = ""

                importance_prop = props.get("重要度", {})
                if importance_prop.get("select"):
                    project["importance"] = importance_prop["select"].get("name", "")
                else:
                    project["importance"] = ""

                company_prop = props.get("企業名", {})
                if company_prop.get("relation"):
                    project["company_ids"] = [r["id"] for r in company_prop["relation"]]
                elif company_prop.get("rich_text"):
                    project["company_name"] = "".join(
                        t.get("plain_text", "") for t in company_prop["rich_text"]
                    )

                amount_prop = props.get("受注金額", {})
                if amount_prop.get("number") is not None:
                    project["amount"] = amount_prop["number"]

                close_date_prop = props.get("受注時期目安", {})
                if close_date_prop.get("date"):
                    project["expected_close_date"] = close_date_prop["date"].get("start", "")

                start_prop = props.get("案件開始日", {})
                if start_prop.get("date"):
                    project["start_date"] = start_prop["date"].get("start", "")

                end_prop = props.get("案件終了日", {})
                if end_prop.get("date"):
                    project["end_date"] = end_prop["date"].get("start", "")

                member_prop = props.get("メンバー", {})
                if member_prop.get("relation"):
                    project["member_ids"] = [r["id"] for r in member_prop["relation"]]
                else:
                    project["member_ids"] = []

                projects.append(project)

            logger.info(f"Listed {len(projects)} projects from Notion")
            return projects

        except Exception as e:
            logger.error(f"Error listing projects from Notion: {e}", exc_info=True)
            raise

    async def create_project_record(
        self,
        data: dict
    ) -> Optional[dict]:
        """
        Notion案件DBに案件レコードを作成する

        data keys:
            name, status, importance, situation, company_name, department,
            amount, expected_close_date, director, pdm, biz, tech, design,
            start_date, end_date, dropbox_url
        """
        if not self.enabled or not self.project_database_id:
            logger.warning("Project DB is not configured.")
            return None

        try:
            properties = {
                "案件名": {
                    "title": [{"text": {"content": data.get("name", "")}}]
                }
            }

            if data.get("status"):
                properties["ステータス"] = {"select": {"name": data["status"]}}

            if data.get("importance"):
                properties["重要度"] = {"select": {"name": data["importance"]}}

            if data.get("situation"):
                properties["状況"] = {"select": {"name": data["situation"]}}

            if data.get("department"):
                properties["部署名"] = {
                    "rich_text": [{"text": {"content": data["department"]}}]
                }

            if data.get("amount") is not None:
                properties["受注金額"] = {"number": data["amount"]}

            if data.get("expected_close_date"):
                properties["受注時期目安"] = {"date": {"start": data["expected_close_date"]}}

            for role_key, prop_name in [
                ("director", "ディレクター"),
                ("pdm", "PdM"),
                ("biz", "Biz"),
                ("tech", "Tech"),
                ("design", "Design"),
            ]:
                if data.get(role_key):
                    val = data[role_key]
                    if isinstance(val, list):
                        text = "、".join(val)
                    else:
                        text = str(val)
                    properties[prop_name] = {
                        "rich_text": [{"text": {"content": text}}]
                    }

            if data.get("start_date"):
                properties["案件開始日"] = {"date": {"start": data["start_date"]}}

            if data.get("end_date"):
                properties["案件終了日"] = {"date": {"start": data["end_date"]}}

            if data.get("dropbox_url"):
                properties["DropBoxURL"] = {"url": data["dropbox_url"]}

            response = self.client.pages.create(
                parent={"database_id": self.project_database_id},
                properties=properties
            )

            page_id = response["id"]
            page_url = response["url"]

            logger.info(f"Project record created in Notion: {page_id}")

            return {
                "id": page_id,
                "url": page_url,
                "name": data.get("name", "")
            }

        except Exception as e:
            logger.error(f"Error creating project record in Notion: {e}", exc_info=True)
            raise
