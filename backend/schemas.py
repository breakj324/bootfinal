"""
schemas.py — Pydantic models for API request and response validation.
"""
from typing import Optional, List, Any
from pydantic import BaseModel, Field


# ── Auth Models ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    status: str = "ok"


# ── Dashboard Models ─────────────────────────────────────────
class DashboardStatsResponse(BaseModel):
    total_users: int
    total_promo_codes: int
    active_promo_codes: int
    pending_requests: int
    accepted_requests: int
    rejected_requests: int
    active_campaigns: int


class ActiveCampaignResponse(BaseModel):
    campaign_id: int
    promo_code: str
    status: str
    max_requests: int
    pending_requests: int
    remaining_slots: int
    created_at: str


# ── Promo Code Models ────────────────────────────────────────
class PromoCodeItem(BaseModel):
    id: int
    code: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    requirements: Optional[str] = None
    example_image: Optional[str] = None
    active: int
    created_at: str


class CreatePromoCodeRequest(BaseModel):
    code: str
    description: str
    instructions: str
    requirements: str
    example_image: Optional[str] = None


class UpdatePromoCodeRequest(BaseModel):
    description: Optional[str] = None
    instructions: Optional[str] = None
    requirements: Optional[str] = None
    example_image: Optional[str] = None


class PromoCodeActionResponse(BaseModel):
    success: bool
    promo_code_id: int
    active: int
    message: str


class UploadImageResponse(BaseModel):
    url: str
    filename: str


# ── Campaign Models ──────────────────────────────────────────
class CampaignItem(BaseModel):
    id: int
    promo_code: str
    status: str
    max_requests: int
    pending_requests: int
    remaining_slots: int
    created_at: str
    closed_at: Optional[str] = None


class CreateCampaignRequest(BaseModel):
    promo_code_id: int
    max_requests: int


class CampaignActionResponse(BaseModel):
    success: bool
    campaign_id: int
    status: str
    message: str


# ── Request Models ───────────────────────────────────────────
class PendingRequestItem(BaseModel):
    id: int
    promo_code: str
    site_id: Optional[str] = None
    first_name: Optional[str] = None
    username: Optional[str] = None
    telegram_user_id: int
    status: str
    created_at: str
    has_screenshot: bool


class RequestDetailResponse(BaseModel):
    id: int
    promo_code: str
    campaign_id: int
    site_id: Optional[str] = None
    first_name: Optional[str] = None
    username: Optional[str] = None
    telegram_user_id: int
    status: str
    created_at: str
    reviewed_at: Optional[str] = None
    has_screenshot: bool
    screenshot_file_id: Optional[str] = None


class RequestActionResponse(BaseModel):
    success: bool
    request_id: int
    status: str
    message: str


# ── Customer Models ──────────────────────────────────────────
class CustomerItem(BaseModel):
    id: int
    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    created_at: str


class CustomersResponse(BaseModel):
    total: int
    page: int
    limit: int
    customers: List[CustomerItem]
