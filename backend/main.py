"""
main.py — FastAPI application for Web Admin Dashboard.

Reuses the existing SQLite database (database.db) and business logic (database.py).
"""
import sys
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config
from database import (
    initialize_database,
    create_promo_code,
    get_promo_code_by_id,
    get_promo_code_by_code,
    get_all_promo_codes,
    update_promo_code_by_id,
    enable_promo_code_by_id,
    disable_promo_code_by_id,
    is_promo_code_used_in_active_campaign,
    get_dashboard_stats,
    create_campaign,
    activate_campaign,
    close_campaign,
    complete_campaign,
    get_active_campaign,
    get_campaign_by_id,
    get_campaigns,
    get_campaign_pending_count,
    get_campaign_remaining_slots,
    get_pending_requests,
    get_pending_requests_count,
    get_request_by_id,
    get_customers,
    get_customers_count,
    review_request,
)
from backend.auth import (
    create_access_token,
    verify_admin_credentials,
)
from backend.dependencies import get_current_admin
from backend.schemas import (
    HealthResponse,
    LoginRequest,
    LoginResponse,
    DashboardStatsResponse,
    ActiveCampaignResponse,
    PromoCodeItem,
    CreatePromoCodeRequest,
    UpdatePromoCodeRequest,
    PromoCodeActionResponse,
    UploadImageResponse,
    CampaignItem,
    CreateCampaignRequest,
    CampaignActionResponse,
    PendingRequestItem,
    RequestDetailResponse,
    RequestActionResponse,
    CustomersResponse,
    CustomerItem,
)

# Initialize database on startup
initialize_database()

# Ensure uploads directory exists
uploads_dir = ROOT_DIR / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Telegram Rewards Bot Admin API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

# Mount static uploads
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# ── CORS Configuration ──────────────────────────────────────────
allowed_origins = [
    origin.strip()
    for origin in [
        config.DASHBOARD_ORIGIN,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    if origin
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


import time
import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("backend")

# ── Request Timing & Access Middleware ──────────────────────────
@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000
    
    # Avoid logging health check every second if polled rapidly
    path = request.url.path
    if path != "/api/health" or response.status_code >= 400:
        logger.info(f"{request.method} {path} -> {response.status_code} ({duration_ms:.2f}ms)")
    
    response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
    return response


# ── Global Exception Handler (prevents stacktrace leakage) ──────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # Log exception type and message safely on server side without credentials
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc.__class__.__name__} - {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# ── Health Endpoint (Public) ────────────────────────────────────
@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Public health check endpoint.
    Performs a lightweight, bounded SELECT 1 check against PostgreSQL.
    """
    from database import check_database_health
    db_ok = check_database_health()
    if not db_ok:
        logger.warning("Health check detected PostgreSQL connectivity degradation")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": "unavailable"}
        )
    return HealthResponse(status="ok")


# ── Auth Endpoints ──────────────────────────────────────────────
@app.post("/api/auth/login", response_model=LoginResponse, tags=["Auth"])
async def admin_login(payload: LoginRequest):
    """Authenticate admin and issue JWT access token."""
    if not verify_admin_credentials(payload.username, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"username": payload.username})
    return LoginResponse(token=token, username=payload.username)


# ── Dashboard Overview Endpoints (Protected) ────────────────────
@app.get("/api/dashboard/stats", response_model=DashboardStatsResponse, tags=["Dashboard"])
async def dashboard_stats(admin=Depends(get_current_admin)):
    """Return aggregated dashboard statistics from the real database."""
    stats = get_dashboard_stats()
    return DashboardStatsResponse(**stats)


@app.get("/api/dashboard/active-campaign", response_model=Optional[ActiveCampaignResponse], tags=["Dashboard"])
async def dashboard_active_campaign(admin=Depends(get_current_admin)):
    """Return current active campaign details, or null if none active."""
    camp = get_active_campaign()
    if not camp:
        return None

    camp_id = camp["id"]
    pending = get_campaign_pending_count(camp_id)
    remaining = get_campaign_remaining_slots(camp_id)

    return ActiveCampaignResponse(
        campaign_id=camp_id,
        promo_code=camp["promo_code"],
        status=camp["status"],
        max_requests=camp["max_requests"],
        pending_requests=pending,
        remaining_slots=remaining,
        created_at=camp["created_at"],
    )


# ── Promo Codes Endpoints (Protected) ───────────────────────────
@app.get("/api/promo-codes", response_model=List[PromoCodeItem], tags=["Promo Codes"])
async def list_promo_codes(admin=Depends(get_current_admin)):
    """Return all promo codes."""
    promos = get_all_promo_codes()
    return [
        PromoCodeItem(
            id=p["id"],
            code=p["code"],
            description=p.get("description"),
            instructions=p.get("instructions"),
            requirements=p.get("requirements"),
            example_image=p.get("example_image"),
            active=p["active"],
            created_at=p["created_at"],
        )
        for p in promos
    ]


@app.post("/api/promo-codes", response_model=PromoCodeItem, status_code=status.HTTP_201_CREATED, tags=["Promo Codes"])
async def create_new_promo_code(payload: CreatePromoCodeRequest, admin=Depends(get_current_admin)):
    """Create a new promo code. Validates required fields and code uniqueness."""
    normalized_code = payload.code.strip().upper()
    if not normalized_code:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Promo code is required")
    if not payload.description or not payload.description.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Description is required")
    if not payload.instructions or not payload.instructions.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Instructions are required")
    if not payload.requirements or not payload.requirements.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Requirements are required")

    existing = get_promo_code_by_code(normalized_code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Promo code '{normalized_code}' already exists",
        )

    try:
        promo_id = create_promo_code(
            code=normalized_code,
            description=payload.description.strip(),
            instructions=payload.instructions.strip(),
            requirements=payload.requirements.strip(),
            example_image=payload.example_image.strip() if payload.example_image else None,
            active=1,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create promo code")

    created = get_promo_code_by_id(promo_id)
    if not created:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created promo code")

    return PromoCodeItem(
        id=created["id"],
        code=created["code"],
        description=created.get("description"),
        instructions=created.get("instructions"),
        requirements=created.get("requirements"),
        example_image=created.get("example_image"),
        active=created["active"],
        created_at=created["created_at"],
    )


@app.get("/api/promo-codes/{promo_id}", response_model=PromoCodeItem, tags=["Promo Codes"])
async def get_single_promo_code(promo_id: int, admin=Depends(get_current_admin)):
    """Retrieve details of a single promo code by ID."""
    promo = get_promo_code_by_id(promo_id)
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Promo code #{promo_id} not found")

    return PromoCodeItem(
        id=promo["id"],
        code=promo["code"],
        description=promo.get("description"),
        instructions=promo.get("instructions"),
        requirements=promo.get("requirements"),
        example_image=promo.get("example_image"),
        active=promo["active"],
        created_at=promo["created_at"],
    )


@app.put("/api/promo-codes/{promo_id}", response_model=PromoCodeItem, tags=["Promo Codes"])
async def update_existing_promo_code(promo_id: int, payload: UpdatePromoCodeRequest, admin=Depends(get_current_admin)):
    """Update promo code fields (description, instructions, requirements, example_image). Code is immutable."""
    promo = get_promo_code_by_id(promo_id)
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Promo code #{promo_id} not found")

    update_promo_code_by_id(
        promo_code_id=promo_id,
        description=payload.description.strip() if payload.description is not None else None,
        instructions=payload.instructions.strip() if payload.instructions is not None else None,
        requirements=payload.requirements.strip() if payload.requirements is not None else None,
        example_image=payload.example_image.strip() if payload.example_image is not None else None,
    )

    updated = get_promo_code_by_id(promo_id)
    return PromoCodeItem(
        id=updated["id"],
        code=updated["code"],
        description=updated.get("description"),
        instructions=updated.get("instructions"),
        requirements=updated.get("requirements"),
        example_image=updated.get("example_image"),
        active=updated["active"],
        created_at=updated["created_at"],
    )


@app.post("/api/promo-codes/{promo_id}/enable", response_model=PromoCodeActionResponse, tags=["Promo Codes"])
async def enable_promo(promo_id: int, admin=Depends(get_current_admin)):
    """Enable a disabled promo code."""
    promo = get_promo_code_by_id(promo_id)
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Promo code #{promo_id} not found")

    enable_promo_code_by_id(promo_id)
    return PromoCodeActionResponse(
        success=True,
        promo_code_id=promo_id,
        active=1,
        message=f"Promo code '{promo['code']}' enabled successfully",
    )


@app.post("/api/promo-codes/{promo_id}/disable", response_model=PromoCodeActionResponse, tags=["Promo Codes"])
async def disable_promo(promo_id: int, admin=Depends(get_current_admin)):
    """
    Disable a promo code.
    Fails with 409 Conflict if the promo code is currently in use by an active/full campaign.
    """
    promo = get_promo_code_by_id(promo_id)
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Promo code #{promo_id} not found")

    if is_promo_code_used_in_active_campaign(promo_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot disable promo code '{promo['code']}' while it is used by an active campaign. Please close the active campaign first.",
        )

    disable_promo_code_by_id(promo_id)
    return PromoCodeActionResponse(
        success=True,
        promo_code_id=promo_id,
        active=0,
        message=f"Promo code '{promo['code']}' disabled successfully",
    )


@app.post("/api/promo-codes/upload-image", response_model=UploadImageResponse, tags=["Promo Codes"])
async def upload_promo_image(file: UploadFile = File(...), admin=Depends(get_current_admin)):
    """
    Upload an example image for a promo code.
    Validates file type (JPEG, PNG, WEBP) and size (<= 5MB).
    """
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{file.content_type}'. Allowed types: JPEG, PNG, WEBP",
        )

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum allowed size of 5MB",
        )

    # Determine extension
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    ext = ext_map.get(file.content_type, ".jpg")

    uploads_dir = ROOT_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    filename = f"promo_{uuid.uuid4().hex[:12]}{ext}"
    target_path = uploads_dir / filename

    target_path.write_bytes(content)

    return UploadImageResponse(
        url=f"/uploads/{filename}",
        filename=filename,
    )


# ── Campaigns Endpoints (Protected) ─────────────────────────────
@app.get("/api/campaigns", response_model=List[CampaignItem], tags=["Campaigns"])
async def list_campaigns(
    status_filter: Optional[str] = Query(None, alias="status"),
    promo_code: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin=Depends(get_current_admin),
):
    """Return campaigns with pending counts and remaining slots."""
    camps = get_campaigns(promo_code=promo_code, status=status_filter)
    # Apply pagination slice
    paged = camps[offset : offset + limit]

    result = []
    for c in paged:
        pending = get_campaign_pending_count(c["id"])
        remaining = get_campaign_remaining_slots(c["id"])
        result.append(
            CampaignItem(
                id=c["id"],
                promo_code=c["promo_code"],
                status=c["status"],
                max_requests=c["max_requests"],
                pending_requests=pending,
                remaining_slots=remaining,
                created_at=c["created_at"],
                closed_at=c.get("closed_at"),
            )
        )
    return result


@app.post("/api/campaigns", response_model=CampaignItem, status_code=status.HTTP_201_CREATED, tags=["Campaigns"])
async def create_new_campaign(payload: CreateCampaignRequest, admin=Depends(get_current_admin)):
    """Create a new campaign for a promo code. Starts in 'closed' status."""
    if not isinstance(payload.max_requests, int) or payload.max_requests <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="max_requests must be a positive integer greater than 0",
        )

    promo = get_promo_code_by_id(payload.promo_code_id)
    if not promo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promo code #{payload.promo_code_id} not found",
        )

    if promo["active"] != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot create a campaign for a disabled promo code",
        )

    try:
        camp_id = create_campaign(
            promo_code=payload.promo_code_id,
            max_requests=payload.max_requests,
            status="closed",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    camp = get_campaign_by_id(camp_id)
    pending = get_campaign_pending_count(camp_id)
    remaining = get_campaign_remaining_slots(camp_id)

    return CampaignItem(
        id=camp["id"],
        promo_code=camp["promo_code"],
        status=camp["status"],
        max_requests=camp["max_requests"],
        pending_requests=pending,
        remaining_slots=remaining,
        created_at=camp["created_at"],
        closed_at=camp.get("closed_at"),
    )


@app.get("/api/campaigns/{campaign_id}", response_model=CampaignItem, tags=["Campaigns"])
async def get_single_campaign(campaign_id: int, admin=Depends(get_current_admin)):
    """Retrieve details of a single campaign by ID."""
    camp = get_campaign_by_id(campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign #{campaign_id} not found")

    pending = get_campaign_pending_count(campaign_id)
    remaining = get_campaign_remaining_slots(campaign_id)

    return CampaignItem(
        id=camp["id"],
        promo_code=camp["promo_code"],
        status=camp["status"],
        max_requests=camp["max_requests"],
        pending_requests=pending,
        remaining_slots=remaining,
        created_at=camp["created_at"],
        closed_at=camp.get("closed_at"),
    )


@app.post("/api/campaigns/{campaign_id}/activate", response_model=CampaignActionResponse, tags=["Campaigns"])
async def activate_existing_campaign(campaign_id: int, admin=Depends(get_current_admin)):
    """
    Activate a closed campaign.
    Enforces the One Active Campaign rule and promo code active status.
    """
    camp = get_campaign_by_id(campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign #{campaign_id} not found")

    if camp["status"] == "active":
        return CampaignActionResponse(
            success=True,
            campaign_id=campaign_id,
            status="active",
            message="Campaign is already active",
        )

    if camp["status"] == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot activate a completed campaign",
        )

    # Check promo code is still active
    promo = get_promo_code_by_id(camp["promo_code_id"])
    if not promo or promo["active"] != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot activate campaign because associated promo code is disabled",
        )

    # Enforce One Active Campaign rule
    active_camp = get_active_campaign()
    if active_camp and active_camp["id"] != campaign_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"كاينة Campaign أخرى مفتوحة حالياً (#{active_camp['id']} - {active_camp['promo_code']}). سدها أولاً قبل ما تفتح هادي.",
        )

    try:
        activate_campaign(campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    updated = get_campaign_by_id(campaign_id)
    return CampaignActionResponse(
        success=True,
        campaign_id=campaign_id,
        status=updated["status"],
        message=f"Campaign #{campaign_id} ({updated['promo_code']}) activated successfully",
    )


@app.post("/api/campaigns/{campaign_id}/close", response_model=CampaignActionResponse, tags=["Campaigns"])
async def close_existing_campaign(campaign_id: int, admin=Depends(get_current_admin)):
    """Close an active or full campaign."""
    camp = get_campaign_by_id(campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign #{campaign_id} not found")

    if camp["status"] in ("closed", "completed"):
        return CampaignActionResponse(
            success=True,
            campaign_id=campaign_id,
            status=camp["status"],
            message="Campaign is already closed",
        )

    close_campaign(campaign_id)
    return CampaignActionResponse(
        success=True,
        campaign_id=campaign_id,
        status="closed",
        message=f"Campaign #{campaign_id} closed successfully",
    )


@app.post("/api/campaigns/{campaign_id}/complete", response_model=CampaignActionResponse, tags=["Campaigns"])
async def complete_existing_campaign(campaign_id: int, admin=Depends(get_current_admin)):
    """Mark a campaign as completed."""
    camp = get_campaign_by_id(campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign #{campaign_id} not found")

    complete_campaign(campaign_id)
    return CampaignActionResponse(
        success=True,
        campaign_id=campaign_id,
        status="completed",
        message=f"Campaign #{campaign_id} marked as completed",
    )


# ── Pending Requests Endpoints (Protected) ──────────────────────
@app.get("/api/requests/pending", response_model=List[PendingRequestItem], tags=["Requests"])
async def list_pending_requests(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin=Depends(get_current_admin),
):
    """Return pending requests with pagination."""
    reqs = get_pending_requests(limit=limit, offset=offset)
    return [
        PendingRequestItem(
            id=r["id"],
            promo_code=r["promo_code"],
            site_id=r.get("site_id"),
            first_name=r.get("first_name"),
            username=r.get("username"),
            telegram_user_id=r["telegram_user_id"],
            status=r["status"],
            created_at=r["created_at"],
            has_screenshot=bool(r.get("screenshot_file_id")),
        )
        for r in reqs
    ]


@app.get("/api/requests/{request_id}", response_model=RequestDetailResponse, tags=["Requests"])
async def get_request_detail(request_id: int, admin=Depends(get_current_admin)):
    """Return full details for a specific request."""
    req = get_request_by_id(request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request #{request_id} not found",
        )

    return RequestDetailResponse(
        id=req["id"],
        promo_code=req["promo_code"],
        campaign_id=req["campaign_id"],
        site_id=req.get("site_id"),
        first_name=req.get("first_name"),
        username=req.get("username"),
        telegram_user_id=req["telegram_user_id"],
        status=req["status"],
        created_at=req["created_at"],
        reviewed_at=req.get("reviewed_at"),
        has_screenshot=bool(req.get("screenshot_file_id")),
        screenshot_file_id=req.get("screenshot_file_id"),
    )


# ── Request Review Actions (Protected) ──────────────────────────
@app.post("/api/requests/{request_id}/accept", response_model=RequestActionResponse, tags=["Requests"])
async def accept_customer_request(request_id: int, admin=Depends(get_current_admin)):
    """Accept a customer request reusing existing Phase 16 atomic review_request logic."""
    req = get_request_by_id(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if req["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request already processed (current status: {req['status']})",
        )

    success, message = review_request(request_id, "accepted")
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return RequestActionResponse(
        success=True,
        request_id=request_id,
        status="accepted",
        message="Request accepted successfully",
    )


@app.post("/api/requests/{request_id}/reject", response_model=RequestActionResponse, tags=["Requests"])
async def reject_customer_request(request_id: int, admin=Depends(get_current_admin)):
    """Reject a customer request reusing existing Phase 16 atomic review_request logic."""
    req = get_request_by_id(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if req["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request already processed (current status: {req['status']})",
        )

    success, message = review_request(request_id, "rejected")
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return RequestActionResponse(
        success=True,
        request_id=request_id,
        status="rejected",
        message="Request rejected successfully",
    )


# ── Customers Endpoints (Protected) ─────────────────────────────
@app.get("/api/customers", response_model=CustomersResponse, tags=["Customers"])
async def list_customers(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    admin=Depends(get_current_admin),
):
    """Return paginated customer directory with optional search."""
    offset = (page - 1) * limit
    total = get_customers_count(search=search)
    users = get_customers(limit=limit, offset=offset, search=search)

    items = [
        CustomerItem(
            id=u["id"],
            telegram_user_id=u["telegram_user_id"],
            username=u.get("username"),
            first_name=u.get("first_name"),
            created_at=u["created_at"],
        )
        for u in users
    ]

    return CustomersResponse(
        total=total,
        page=page,
        limit=limit,
        customers=items,
    )
