from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin
from app.core.email import send_shop_approved_email, send_shop_rejected_email
from app.db.session import get_db
from app.modules.admin.admin_dto import OverviewOut, RejectRequest, ShopAdminOut, ShopListOut, ShopStatsOut
from app.modules.admin.admin_mapper import to_shop_admin_out
from app.modules.admin.admin_service import AdminService, ShopNotFoundError
from app.modules.identity.identity_model import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", response_model=OverviewOut)
def overview(db: Session = Depends(get_db), _admin: User = Depends(get_current_admin)):
    return OverviewOut(**AdminService(db).overview())


@router.get("/shops", response_model=ShopListOut)
def list_shops(
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    shops, owners_by_shop, total, page, page_size, total_pages = AdminService(db).list_shops(
        status_filter, page, page_size
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
