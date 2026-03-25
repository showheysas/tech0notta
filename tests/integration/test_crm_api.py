"""
customers.py, deals.py, crm_service.py の C0/C1 カバレッジテスト

C0: CRUD 正常系 (create, list, get, update, delete)
C1: バリデーション, not_found, 成約/失注 close_date 自動設定, フィルタ分岐
"""
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.customer import CustomerCreate, CustomerUpdate
from app.models.deal import DealCreate, DealUpdate, DealStatus
from app.services.crm_service import CRMService


# ============================================================
# CRMService - Customer
# ============================================================

class TestCRMCustomer:
    @pytest.fixture(autouse=True)
    def setup_service(self):
        self.svc = CRMService()

    @pytest.mark.asyncio
    async def test_create_customer(self):
        """C0: 顧客作成成功"""
        data = CustomerCreate(
            company_name="テスト株式会社",
            contact_person="田中太郎",
            email="tanaka@example.com",
        )
        result = await self.svc.create_customer(data)
        assert result.company_name == "テスト株式会社"
        assert result.contact_person == "田中太郎"
        assert result.id.startswith("cust-")

    @pytest.mark.asyncio
    async def test_list_customers(self):
        """C0: 顧客一覧"""
        await self.svc.create_customer(
            CustomerCreate(company_name="A社", contact_person="A")
        )
        await self.svc.create_customer(
            CustomerCreate(company_name="B社", contact_person="B")
        )
        result = await self.svc.get_customers()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_customer(self):
        """C0: 顧客詳細取得"""
        created = await self.svc.create_customer(
            CustomerCreate(company_name="C社", contact_person="C")
        )
        result = await self.svc.get_customer(created.id)
        assert result.company_name == "C社"

    @pytest.mark.asyncio
    async def test_get_customer_not_found(self):
        """C1: 顧客未発見 → 404"""
        with pytest.raises(HTTPException) as exc_info:
            await self.svc.get_customer("nonexistent")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_customer(self):
        """C0: 顧客更新成功"""
        created = await self.svc.create_customer(
            CustomerCreate(company_name="D社", contact_person="D")
        )
        result = await self.svc.update_customer(
            created.id, CustomerUpdate(company_name="D社改")
        )
        assert result.company_name == "D社改"

    @pytest.mark.asyncio
    async def test_update_customer_not_found(self):
        """C1: 更新対象未発見 → 404"""
        with pytest.raises(HTTPException) as exc_info:
            await self.svc.update_customer("nonexistent", CustomerUpdate(company_name="X"))
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_customer_partial_fields(self):
        """C1: 一部フィールドのみ更新"""
        created = await self.svc.create_customer(
            CustomerCreate(company_name="E社", contact_person="E", email="e@example.com")
        )
        result = await self.svc.update_customer(
            created.id, CustomerUpdate(email="new@example.com", phone="090-1234-5678")
        )
        assert result.email == "new@example.com"
        assert result.phone == "090-1234-5678"
        assert result.company_name == "E社"  # 変更なし

    @pytest.mark.asyncio
    async def test_delete_customer(self):
        """C0: 顧客削除成功"""
        created = await self.svc.create_customer(
            CustomerCreate(company_name="F社", contact_person="F")
        )
        await self.svc.delete_customer(created.id)
        with pytest.raises(HTTPException):
            await self.svc.get_customer(created.id)

    @pytest.mark.asyncio
    async def test_delete_customer_not_found(self):
        """C1: 削除対象未発見 → 404"""
        with pytest.raises(HTTPException) as exc_info:
            await self.svc.delete_customer("nonexistent")
        assert exc_info.value.status_code == 404


# ============================================================
# CRMService - Deal
# ============================================================

class TestCRMDeal:
    @pytest.fixture(autouse=True)
    async def setup_service(self):
        self.svc = CRMService()
        self.customer = await self.svc.create_customer(
            CustomerCreate(company_name="テスト社", contact_person="テスト")
        )

    @pytest.mark.asyncio
    async def test_create_deal(self):
        """C0: 商談作成成功"""
        data = DealCreate(
            customer_id=self.customer.id,
            name="商談A",
            amount=1000000,
            probability=50,
        )
        result = await self.svc.create_deal(data)
        assert result.name == "商談A"
        assert result.status == DealStatus.LEAD

    @pytest.mark.asyncio
    async def test_create_deal_invalid_customer(self):
        """C1: 顧客未発見 → 400"""
        data = DealCreate(customer_id="nonexistent", name="商談X")
        with pytest.raises(HTTPException) as exc_info:
            await self.svc.create_deal(data)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_list_deals(self):
        """C0: 商談一覧"""
        await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談1")
        )
        await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談2")
        )
        result = await self.svc.get_deals()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_deals_filter_by_customer(self):
        """C1: customer_idフィルタ"""
        other = await self.svc.create_customer(
            CustomerCreate(company_name="別社", contact_person="別")
        )
        await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談A")
        )
        await self.svc.create_deal(
            DealCreate(customer_id=other.id, name="商談B")
        )
        result = await self.svc.get_deals(customer_id=self.customer.id)
        assert len(result) == 1
        assert result[0].name == "商談A"

    @pytest.mark.asyncio
    async def test_list_deals_filter_by_status(self):
        """C1: statusフィルタ"""
        await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談C", status=DealStatus.IN_PROGRESS)
        )
        await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談D", status=DealStatus.LEAD)
        )
        result = await self.svc.get_deals(status=DealStatus.IN_PROGRESS)
        assert len(result) == 1
        assert result[0].name == "商談C"

    @pytest.mark.asyncio
    async def test_get_deal(self):
        """C0: 商談詳細取得"""
        created = await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談E")
        )
        result = await self.svc.get_deal(created.id)
        assert result.name == "商談E"

    @pytest.mark.asyncio
    async def test_get_deal_not_found(self):
        """C1: 商談未発見 → 404"""
        with pytest.raises(HTTPException) as exc_info:
            await self.svc.get_deal("nonexistent")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_deal(self):
        """C0: 商談更新成功"""
        created = await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談F")
        )
        result = await self.svc.update_deal(
            created.id, DealUpdate(name="商談F改", amount=2000000)
        )
        assert result.name == "商談F改"
        assert result.amount == 2000000

    @pytest.mark.asyncio
    async def test_update_deal_not_found(self):
        """C1: 更新対象未発見 → 404"""
        with pytest.raises(HTTPException) as exc_info:
            await self.svc.update_deal("nonexistent", DealUpdate(name="X"))
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_deal_won_sets_close_date(self):
        """C1: 成約→close_date自動設定"""
        created = await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談G")
        )
        result = await self.svc.update_deal(
            created.id, DealUpdate(status=DealStatus.WON)
        )
        assert result.status == DealStatus.WON
        assert result.close_date == date.today()

    @pytest.mark.asyncio
    async def test_update_deal_lost_sets_close_date(self):
        """C1: 失注→close_date自動設定"""
        created = await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談H")
        )
        result = await self.svc.update_deal(
            created.id, DealUpdate(status=DealStatus.LOST)
        )
        assert result.status == DealStatus.LOST
        assert result.close_date == date.today()

    @pytest.mark.asyncio
    async def test_update_deal_partial_fields(self):
        """C1: 一部フィールドのみ更新"""
        created = await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談I", amount=100)
        )
        result = await self.svc.update_deal(
            created.id, DealUpdate(probability=80, expected_close_date=date(2026, 6, 30))
        )
        assert result.probability == 80
        assert result.expected_close_date == date(2026, 6, 30)
        assert result.name == "商談I"  # 変更なし
        assert result.amount == 100  # 変更なし

    @pytest.mark.asyncio
    async def test_delete_deal(self):
        """C0: 商談削除成功"""
        created = await self.svc.create_deal(
            DealCreate(customer_id=self.customer.id, name="商談J")
        )
        await self.svc.delete_deal(created.id)
        with pytest.raises(HTTPException):
            await self.svc.get_deal(created.id)

    @pytest.mark.asyncio
    async def test_delete_deal_not_found(self):
        """C1: 削除対象未発見 → 404"""
        with pytest.raises(HTTPException) as exc_info:
            await self.svc.delete_deal("nonexistent")
        assert exc_info.value.status_code == 404


# ============================================================
# Router バリデーション (customers.py, deals.py)
# ============================================================

class TestCustomerRouterValidation:
    @pytest.mark.asyncio
    async def test_create_customer_empty_company_name(self, test_user):
        """C1: 会社名空 → 400"""
        from app.routers.customers import create_customer
        with pytest.raises(HTTPException) as exc_info:
            await create_customer(
                data=CustomerCreate(company_name="  ", contact_person="田中"),
                current_user=test_user,
            )
        assert exc_info.value.status_code == 400
        assert "会社名は必須" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_customer_empty_contact_person(self, test_user):
        """C1: 担当者名空 → 400"""
        from app.routers.customers import create_customer
        with pytest.raises(HTTPException) as exc_info:
            await create_customer(
                data=CustomerCreate(company_name="テスト社", contact_person="  "),
                current_user=test_user,
            )
        assert exc_info.value.status_code == 400
        assert "担当者名は必須" in exc_info.value.detail


class TestDealRouterValidation:
    @pytest.mark.asyncio
    async def test_create_deal_empty_customer_id(self, test_user):
        """C1: 顧客ID空 → 400"""
        from app.routers.deals import create_deal
        with pytest.raises(HTTPException) as exc_info:
            await create_deal(
                data=DealCreate(customer_id="  ", name="商談"),
                current_user=test_user,
            )
        assert exc_info.value.status_code == 400
        assert "顧客IDは必須" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_deal_empty_name(self, test_user):
        """C1: 商談名空 → 400"""
        from app.routers.deals import create_deal
        with pytest.raises(HTTPException) as exc_info:
            await create_deal(
                data=DealCreate(customer_id="cust-1", name="  "),
                current_user=test_user,
            )
        assert exc_info.value.status_code == 400
        assert "商談名は必須" in exc_info.value.detail
