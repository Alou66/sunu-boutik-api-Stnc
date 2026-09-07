from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.billing.billing_service import InvoiceNotFoundError
from app.modules.payments.payments_dto import PaymentCreate, PaymentOut, PaymentVoidRequest
from app.modules.payments.payments_mapper import to_payment_out
from app.modules.payments.payments_service import (
    AmountExceedsBalanceError,
    InvoiceAlreadyPaidError,
    PaymentAlreadyVoidedError,
    PaymentNotFoundError,
    PaymentService,
)

router = APIRouter(prefix="/invoices", tags=["payments"])


@router.post("/{invoice_id}/payments", response_model=PaymentOut, status_code=201)
def create_payment(
    invoice_id: int,
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        payment = PaymentService(db).create(
            current_user.shop_id, current_user.id, invoice_id,
            payload.amount, payload.amount_received, payload.note, payload.idempotency_key,
        )
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (InvoiceAlreadyPaidError, AmountExceedsBalanceError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_payment_out(payment)


@router.get("/{invoice_id}/payments", response_model=list[PaymentOut])
def list_payments(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        payments = PaymentService(db).list_for_invoice(current_user.shop_id, invoice_id)
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return [to_payment_out(p) for p in payments]


@router.post("/{invoice_id}/payments/{payment_id}/void", response_model=PaymentOut)
def void_payment(
    invoice_id: int,
    payment_id: int,
    payload: PaymentVoidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        payment = PaymentService(db).void(current_user.shop_id, current_user.id, invoice_id, payment_id, payload.reason)
    except (InvoiceNotFoundError, PaymentNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PaymentAlreadyVoidedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_payment_out(payment)
