"""
CRMサービス - 顧客・商談管理のビジネスロジック

Notion Customer DB / Deal DBとの連携を担当します。
"""
from typing import List, Optional
from datetime import date, datetime
from fastapi import HTTPException
from app.models.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from app.models.deal import DealCreate, DealUpdate, DealResponse, DealStatus
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Notion DB IDs (環境変数から取得、未設定時はインメモリモード)
NOTION_CUSTOMER_DB_ID = getattr(settings, 'NOTION_CUSTOMER_DB_ID', None) or ""
NOTION_DEAL_DB_ID = getattr(settings, 'NOTION_DEAL_DB_ID', None) or ""


class CRMService:
    """顧客・商談管理サービス"""

    def __init__(self):
        self._customers: dict[str, dict] = {}
        self._deals: dict[str, dict] = {}
        self._next_customer_id = 1
        self._next_deal_id = 1

    def _generate_customer_id(self) -> str:
        cid = f"cust-{self._next_customer_id}"
        self._next_customer_id += 1
        return cid

    def _generate_deal_id(self) -> str:
        did = f"deal-{self._next_deal_id}"
        self._next_deal_id += 1
        return did

    async def create_customer(self, data: CustomerCreate) -> CustomerResponse:
        now = datetime.utcnow()
        cid = self._generate_customer_id()
        record = {
            "id": cid,
            "company_name": data.company_name,
            "contact_person": data.contact_person,
            "email": data.email,
            "phone": data.phone,
            "address": data.address,
            "notes": data.notes,
            "notion_page_url": "",
            "created_at": now,
            "updated_at": now,
        }
        self._customers[cid] = record
        logger.info(f"Customer created: {cid} - {data.company_name}")
        return self._to_customer_response(record)

    async def get_customers(self) -> List[CustomerResponse]:
        return [self._to_customer_response(c) for c in self._customers.values()]

    async def get_customer(self, customer_id: str) -> CustomerResponse:
        record = self._customers.get(customer_id)
        if not record:
            raise HTTPException(status_code=404, detail="顧客が見つかりません")
        return self._to_customer_response(record)

    async def update_customer(self, customer_id: str, data: CustomerUpdate) -> CustomerResponse:
        record = self._customers.get(customer_id)
        if not record:
            raise HTTPException(status_code=404, detail="顧客が見つかりません")
        if data.company_name is not None:
            record["company_name"] = data.company_name
        if data.contact_person is not None:
            record["contact_person"] = data.contact_person
        if data.email is not None:
            record["email"] = data.email
        if data.phone is not None:
            record["phone"] = data.phone
        if data.address is not None:
            record["address"] = data.address
        if data.notes is not None:
            record["notes"] = data.notes
        record["updated_at"] = datetime.utcnow()
        logger.info(f"Customer updated: {customer_id}")
        return self._to_customer_response(record)

    async def delete_customer(self, customer_id: str) -> None:
        if customer_id not in self._customers:
            raise HTTPException(status_code=404, detail="顧客が見つかりません")
        del self._customers[customer_id]
        logger.info(f"Customer deleted: {customer_id}")

    def _to_customer_response(self, record: dict) -> CustomerResponse:
        return CustomerResponse(
            id=record["id"],
            company_name=record["company_name"],
            contact_person=record["contact_person"],
            email=record.get("email"),
            phone=record.get("phone"),
            address=record.get("address"),
            notes=record.get("notes"),
            notion_page_url=record.get("notion_page_url", ""),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )

    # --- 商談管理 ---

    async def create_deal(self, data: DealCreate) -> DealResponse:
        # 顧客存在チェック
        if data.customer_id not in self._customers:
            raise HTTPException(status_code=400, detail="指定された顧客が見つかりません")
        now = datetime.utcnow()
        did = self._generate_deal_id()
        record = {
            "id": did,
            "customer_id": data.customer_id,
            "name": data.name,
            "amount": data.amount,
            "probability": data.probability,
            "expected_close_date": data.expected_close_date,
            "status": data.status.value if data.status else DealStatus.LEAD.value,
            "close_date": None,
            "notion_page_url": "",
            "created_at": now,
            "updated_at": now,
        }
        self._deals[did] = record
        logger.info(f"Deal created: {did} - {data.name}")
        return self._to_deal_response(record)

    async def get_deals(
        self, customer_id: Optional[str] = None, status: Optional[DealStatus] = None
    ) -> List[DealResponse]:
        deals = list(self._deals.values())
        if customer_id:
            deals = [d for d in deals if d["customer_id"] == customer_id]
        if status:
            deals = [d for d in deals if d["status"] == status.value]
        return [self._to_deal_response(d) for d in deals]

    async def get_deal(self, deal_id: str) -> DealResponse:
        record = self._deals.get(deal_id)
        if not record:
            raise HTTPException(status_code=404, detail="商談が見つかりません")
        return self._to_deal_response(record)

    async def update_deal(self, deal_id: str, data: DealUpdate) -> DealResponse:
        record = self._deals.get(deal_id)
        if not record:
            raise HTTPException(status_code=404, detail="商談が見つかりません")
        if data.name is not None:
            record["name"] = data.name
        if data.amount is not None:
            record["amount"] = data.amount
        if data.probability is not None:
            record["probability"] = data.probability
        if data.expected_close_date is not None:
            record["expected_close_date"] = data.expected_close_date
        if data.status is not None:
            record["status"] = data.status.value
            # 成約・失注時にclose_dateを自動設定
            if data.status in (DealStatus.WON, DealStatus.LOST):
                record["close_date"] = date.today()
        record["updated_at"] = datetime.utcnow()
        logger.info(f"Deal updated: {deal_id}")
        return self._to_deal_response(record)

    async def delete_deal(self, deal_id: str) -> None:
        if deal_id not in self._deals:
            raise HTTPException(status_code=404, detail="商談が見つかりません")
        del self._deals[deal_id]
        logger.info(f"Deal deleted: {deal_id}")

    def _to_deal_response(self, record: dict) -> DealResponse:
        return DealResponse(
            id=record["id"],
            customer_id=record["customer_id"],
            name=record["name"],
            amount=record.get("amount"),
            probability=record.get("probability"),
            expected_close_date=record.get("expected_close_date"),
            status=DealStatus(record["status"]),
            close_date=record.get("close_date"),
            notion_page_url=record.get("notion_page_url", ""),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )


# シングルトンインスタンス
_crm_service: Optional[CRMService] = None


def get_crm_service() -> CRMService:
    """CRMServiceのシングルトンインスタンスを取得"""
    global _crm_service
    if _crm_service is None:
        _crm_service = CRMService()
    return _crm_service