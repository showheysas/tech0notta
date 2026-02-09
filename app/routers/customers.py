from fastapi import APIRouter, HTTPException
from typing import List
from app.models.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from app.services.crm_service import get_crm_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.post("", response_model=CustomerResponse)
async def create_customer(data: CustomerCreate):
    """
    顧客を作成する

    必須フィールド: company_name, contact_person
    """
    if not data.company_name or not data.company_name.strip():
        raise HTTPException(status_code=400, detail="会社名は必須です")
    if not data.contact_person or not data.contact_person.strip():
        raise HTTPException(status_code=400, detail="担当者名は必須です")

    service = get_crm_service()
    return await service.create_customer(data)


@router.get("", response_model=List[CustomerResponse])
async def list_customers():
    """
    顧客一覧を取得する
    """
    service = get_crm_service()
    return await service.get_customers()


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: str):
    """
    顧客詳細を取得する（関連議事録・タスク含む）
    """
    service = get_crm_service()
    return await service.get_customer(customer_id)


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(customer_id: str, data: CustomerUpdate):
    """
    顧客情報を更新する
    """
    service = get_crm_service()
    return await service.update_customer(customer_id, data)


@router.delete("/{customer_id}")
async def delete_customer(customer_id: str):
    """
    顧客を削除する
    """
    service = get_crm_service()
    await service.delete_customer(customer_id)
    return {"message": "顧客を削除しました"}
