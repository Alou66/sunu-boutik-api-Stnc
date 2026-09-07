import io
import zipfile
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.billing.billing_dto import InvoiceCreate, InvoiceListOut, InvoiceOut, InvoiceUpdate
from app.modules.billing.billing_mapper import to_invoice_out
from app.modules.billing.billing_pdf import build_export_ticket_pdf, build_invoice_pdf
from app.modules.billing.billing_service import (
    InsufficientStockError,
    InvoiceClientNotFoundError,
    InvoiceLineProductNotFoundError,
    InvoiceLockedError,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    try:
        items, total = InvoiceService(db).list(current_user.shop_id, page, page_size, search, date, status_filter)
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


@router.get("/export")
def export_invoices_zip(
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    if date_from:
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Format date_from invalide (AAAA-MM-JJ)")
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            raise HTTPException(400, "Format date_to invalide (AAAA-MM-JJ)")
    else:
        if now.month == 12:
            end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            end = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

    service = InvoiceService(db)
    invoices = service.list_for_period(current_user.shop_id, start, end)
    shop = service.get_shop(current_user.shop_id)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for inv in invoices:
            client = service.get_client_unscoped(inv.client_id)
            pdf_bytes = build_export_ticket_pdf(inv, shop, client)
            safe_num = inv.number.replace("/", "-").replace("\\", "-")
            zf.writestr(f"{safe_num}.pdf", pdf_bytes)

    zip_buffer.seek(0)
    period_str = f"{start.strftime('%Y-%m-%d')}_{(end - timedelta(days=1)).strftime('%Y-%m-%d')}"
    filename = f"EIP_factures_{period_str}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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


@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(
    invoice_id: int,
    format: str = "ticket",
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

    pdf_bytes = build_invoice_pdf(invoice, shop, client, format)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=facture-{invoice.number}.pdf"},
    )
