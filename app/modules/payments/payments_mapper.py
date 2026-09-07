from app.modules.payments.payments_dto import PaymentOut
from app.modules.payments.payments_model import Payment


def to_payment_out(payment: Payment) -> PaymentOut:
    return PaymentOut.model_validate(payment)
