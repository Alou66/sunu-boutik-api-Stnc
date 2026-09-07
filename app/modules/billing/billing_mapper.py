from app.modules.billing.billing_dto import InvoiceOut
from app.modules.billing.billing_model import Invoice


def to_invoice_out(invoice: Invoice) -> InvoiceOut:
    return InvoiceOut.model_validate(invoice)
