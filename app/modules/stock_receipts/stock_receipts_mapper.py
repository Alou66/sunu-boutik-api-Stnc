from app.modules.stock_receipts.stock_receipts_dto import (
    StockMovementOut,
    StockReceiptLineOut,
    StockReceiptOut,
)
from app.modules.stock_receipts.stock_receipts_model import StockMovement, StockReceipt, StockReceiptLine


def to_line_out(line: StockReceiptLine) -> StockReceiptLineOut:
    return StockReceiptLineOut.model_validate(line)


def to_receipt_out(receipt: StockReceipt) -> StockReceiptOut:
    return StockReceiptOut(
        id=receipt.id,
        supplier_id=receipt.supplier_id,
        supplier_name=receipt.supplier.name if receipt.supplier else None,
        reference=receipt.reference,
        status=receipt.status,
        total_cost=receipt.total_cost,
        note=receipt.note,
        created_by_id=receipt.created_by_id,
        created_by_name=receipt.created_by.full_name if receipt.created_by else None,
        validated_by_id=receipt.validated_by_id,
        validated_by_name=receipt.validated_by.full_name if receipt.validated_by else None,
        validated_at=receipt.validated_at,
        created_at=receipt.created_at,
        lines=[to_line_out(line) for line in receipt.lines],
    )


def to_movement_out(movement: StockMovement) -> StockMovementOut:
    return StockMovementOut(
        id=movement.id,
        product_id=movement.product_id,
        product_name=movement.product_name,
        source_type=movement.source_type,
        source_id=movement.source_id,
        unit_target=movement.unit_target,
        quantity_delta=movement.quantity_delta,
        created_by_id=movement.created_by_id,
        created_by_name=movement.created_by.full_name if movement.created_by else None,
        created_at=movement.created_at,
    )
