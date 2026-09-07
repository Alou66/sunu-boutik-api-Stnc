from app.modules.cashier.cashier_dto import CaisseEntryOut
from app.modules.payments.payments_model import Payment


def to_caisse_entry_out(payment: Payment) -> CaisseEntryOut:
    return CaisseEntryOut(
        id=payment.id,
        invoice_id=payment.invoice_id,
        invoice_number=payment.invoice.number,
        client_name=(payment.invoice.client.name if payment.invoice.client else payment.invoice.client_name)
        or "Client comptant",
        amount=payment.amount,
        created_at=payment.created_at,
    )
