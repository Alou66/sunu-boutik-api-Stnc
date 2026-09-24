import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.billing.billing_dto import InvoiceCancelRequest, InvoiceCreate, InvoiceListOut, InvoiceOut, InvoiceUpdate
from app.modules.billing.billing_mapper import to_invoice_out
from app.modules.billing.billing_pdf import build_invoice_pdf
from app.modules.billing.billing_service import (
    InsufficientStockError,
    InvoiceAlreadyCancelledError,
    InvoiceClientNotFoundError,
    InvoiceLineProductNotFoundError,
    InvoiceLockedError,
    InvoiceNotCancelledError,
    InvoiceNotFoundError,
    InvoiceService,
    InvoiceValidationError,
    NumberingConflictError,
)

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=InvoiceListOut)
def list_invoices(
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    date: str | None = None,
    status_filter: str | None = None,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    try:
        items, total = InvoiceService(db).list(
            current_user.shop_id, page, page_size, search, date, status_filter, employee_id
        )
    except InvoiceValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    total_pages = max((total + page_size - 1) // page_size, 1)

    return InvoiceListOut(
        items=[to_invoice_out(inv) for inv in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=InvoiceOut, status_code=201)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        invoice = InvoiceService(db).create(
            current_user.shop_id, payload.client_id, payload.client_name, payload.note, payload.lines,
            created_by_id=current_user.id, idempotency_key=payload.idempotency_key,
        )
    except InvoiceValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvoiceClientNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NumberingConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InvoiceLineProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_invoice_out(invoice)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        invoice = InvoiceService(db).get(current_user.shop_id, invoice_id)
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_invoice_out(invoice)


@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        invoice = InvoiceService(db).update(
            current_user.shop_id, invoice_id, payload.client_id, payload.client_name, payload.note, payload.lines,
        )
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvoiceLockedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvoiceValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvoiceClientNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvoiceLineProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_invoice_out(invoice)


@router.post("/{invoice_id}/cancel", response_model=InvoiceOut)
def cancel_invoice(
    invoice_id: int,
    payload: InvoiceCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        invoice = InvoiceService(db).cancel(current_user.shop_id, invoice_id, current_user.id, payload.reason)
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (InvoiceAlreadyCancelledError, InvoiceLockedError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_invoice_out(invoice)


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        InvoiceService(db).delete(current_user.shop_id, invoice_id)
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvoiceNotCancelledError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return None


@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = InvoiceService(db)
    try:
        invoice = service.get(current_user.shop_id, invoice_id)
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    shop = service.get_shop(current_user.shop_id)
    client = service.get_client_unscoped(invoice.client_id)

    pdf_bytes = build_invoice_pdf(invoice, shop, client)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=facture-{invoice.number}.pdf"},
    )
