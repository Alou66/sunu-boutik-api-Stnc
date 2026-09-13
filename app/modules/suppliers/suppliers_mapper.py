from app.modules.suppliers.suppliers_dto import SupplierOut
from app.modules.suppliers.suppliers_model import Supplier


def to_supplier_out(supplier: Supplier) -> SupplierOut:
    return SupplierOut.model_validate(supplier)
