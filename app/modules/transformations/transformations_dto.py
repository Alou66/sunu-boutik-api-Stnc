from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.products.products_dto import ProductOut
from app.modules.transformations.transformations_model import TransformationDirection


class TransformationExecuteRequest(BaseModel):
    product_id: int
    direction: TransformationDirection
    # Quantité exprimée dans la forme de départ (celle qu'on consomme).
    quantity: float = Field(gt=0)
    note: Optional[str] = None
    # Généré côté client (identifiant stable par tentative de transformation,
    # réutilisé si la requête est renvoyée) : permet à TransformationService.execute
    # de détecter une resoumission (double clic, retry réseau) et de renvoyer le
    # résultat déjà obtenu au lieu de déplacer le stock une seconde fois.
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


class TransformationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    direction: TransformationDirection
    unit_from: str
    unit_to: str
    quantity_from: float
    quantity_to: float
    note: Optional[str] = None
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime


class TransformationResultOut(BaseModel):
    log: TransformationLogOut
    product: ProductOut


class TransformationLogListOut(BaseModel):
    items: list[TransformationLogOut]
    total: int
    page: int
    page_size: int
    total_pages: int
