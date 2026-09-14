from app.modules.billing.billing_dto import InvoiceOut
from app.modules.billing.billing_model import Invoice


def to_invoice_out(invoice: Invoice) -> InvoiceOut:
    out = InvoiceOut.model_validate(invoice)
    out.created_by_name = invoice.created_by.full_name if invoice.created_by else None
    out.cancelled_by_name = invoice.cancelled_by.full_name if invoice.cancelled_by else None
    return out
