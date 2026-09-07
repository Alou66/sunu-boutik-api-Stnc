from app.modules.transformations.transformations_dto import TransformationLogOut
from app.modules.transformations.transformations_model import TransformationLog


def to_log_out(log: TransformationLog) -> TransformationLogOut:
    return TransformationLogOut(
        id=log.id,
        product_id=log.product_id,
        product_name=log.product_name,
        direction=log.direction,
        unit_from=log.unit_from,
        unit_to=log.unit_to,
        quantity_from=log.quantity_from,
        quantity_to=log.quantity_to,
        note=log.note,
        created_by_id=log.created_by_id,
        created_by_name=log.created_by.full_name if log.created_by else None,
        created_at=log.created_at,
    )
