from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin
from app.core.email import (
    send_owner_password_reset_email,
    send_shop_approved_email,
    send_shop_reactivated_email,
    send_shop_rejected_email,
    send_shop_suspended_email,
)
from app.core.limiter import limiter
from app.db.session import get_db
from app.modules.admin.admin_dto import (
    MessageOut,
    OverviewOut,
    RejectRequest,
    ShopAdminOut,
    ShopListOut,
    ShopStatsOut,
    SuspendRequest,
)
from app.modules.admin.admin_mapper import to_shop_admin_out
from app.modules.admin.admin_service import (
    AdminService,
    InvalidShopStatusError,
    OwnerNotFoundError,
    ShopNotFoundError,
)
from app.modules.identity.identity_dto import LoginRequest, Token
from app.modules.identity.identity_model import User
from app.modules.identity.identity_service import AccountDisabledError, IdentityService, InvalidCredentialsError

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def admin_login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        token = IdentityService(db).login_admin(payload.email, payload.password)
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except AccountDisabledError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return Token(access_token=token)


@router.get("/overview", response_model=OverviewOut)
def overview(db: Session = Depends(get_db), _admin: User = Depends(get_current_admin)):
    return OverviewOut(**AdminService(db).overview())


@router.get("/shops", response_model=ShopListOut)
def list_shops(
    status_filter: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    shops, owners_by_shop, total, page, page_size, total_pages = AdminService(db).list_shops(
        status_filter, page, page_size, search
    )
    return ShopListOut(
        items=[to_shop_admin_out(shop, owners_by_shop.get(shop.id)) for shop in shops],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/shops/{shop_id}/stats", response_model=ShopStatsOut)
def shop_stats(shop_id: int, db: Session = Depends(get_db), _admin: User = Depends(get_current_admin)):
    try:
        stats = AdminService(db).shop_stats(shop_id)
    except ShopNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ShopStatsOut(**stats)


@router.post("/shops/{shop_id}/approve", response_model=ShopAdminOut)
def approve_shop(
    shop_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    try:
        shop, owner, temp_password = AdminService(db).approve_shop(shop_id)
    except ShopNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if owner:
        origin = request.headers.get("origin")
        background_tasks.add_task(
            send_shop_approved_email, owner.full_name, owner.email, shop.name, temp_password, origin
        )

    return to_shop_admin_out(shop, owner)


@router.post("/shops/{shop_id}/reject", response_model=ShopAdminOut)
def reject_shop(
    shop_id: int,
    payload: RejectRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    try:
        shop, owner = AdminService(db).reject_shop(shop_id)
    except ShopNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if owner:
        origin = request.headers.get("origin")
        background_tasks.add_task(
            send_shop_rejected_email, owner.full_name, owner.email, shop.name, payload.reason, origin
        )

    return to_shop_admin_out(shop, owner)


@router.patch("/shops/{shop_id}/suspend", response_model=ShopAdminOut)
def suspend_shop(
    shop_id: int,
    payload: SuspendRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    try:
        shop, owner = AdminService(db).suspend_shop(shop_id, payload.reason)
    except ShopNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidShopStatusError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if owner:
        origin = request.headers.get("origin")
        background_tasks.add_task(
            send_shop_suspended_email, owner.full_name, owner.email, shop.name, payload.reason, origin
        )

    return to_shop_admin_out(shop, owner)


@router.patch("/shops/{shop_id}/reactivate", response_model=ShopAdminOut)
def reactivate_shop(
    shop_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    try:
        shop, owner = AdminService(db).reactivate_shop(shop_id)
    except ShopNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidShopStatusError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if owner:
        origin = request.headers.get("origin")
        background_tasks.add_task(
            send_shop_reactivated_email, owner.full_name, owner.email, shop.name, origin
        )

    return to_shop_admin_out(shop, owner)


@router.post("/shops/{shop_id}/owner/reset-password", response_model=MessageOut)
def reset_owner_password(
    shop_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    try:
        shop, owner, temp_password = AdminService(db).reset_owner_password(shop_id)
    except ShopNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OwnerNotFoundError as e:
        raise HTTPException(status_code=409, detail=str(e))

    origin = request.headers.get("origin")
    background_tasks.add_task(
        send_owner_password_reset_email, owner.full_name, owner.email, shop.name, temp_password, origin
    )

    return MessageOut(message=f"Un nouveau mot de passe a été envoyé à {owner.email}")
