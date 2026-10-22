from app.modules.stock_initializations.stock_initializations_model import StockInitialization
from app.modules.stock_initializations.stock_initializations_dto import StockInitializationLineOut, StockInitializationOut


def to_initialization_out(init: StockInitialization) -> StockInitializationOut:
    return StockInitializationOut(
        id=init.id,
        shop_id=init.shop_id,
        note=init.note,
        created_by_id=init.created_by_id,
        created_at=init.created_at,
        lines=[
            StockInitializationLineOut(
                id=line.id,
                product_id=line.product_id,
                product_name=line.product_name,
                unit_target=line.unit_target,
                quantity=line.quantity,
                created_at=line.created_at,
            )
            for line in init.lines
        ],
    )
