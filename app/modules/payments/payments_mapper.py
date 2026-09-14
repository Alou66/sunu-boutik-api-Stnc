from app.modules.payments.payments_dto import PaymentOut
from app.modules.payments.payments_model import Payment


def to_payment_out(payment: Payment) -> PaymentOut:
    out = PaymentOut.model_validate(payment)
    out.created_by_name = payment.created_by.full_name if payment.created_by else None
    return out
