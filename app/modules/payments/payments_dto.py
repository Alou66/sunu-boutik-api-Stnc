from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PaymentCreate(BaseModel):
    amount: float = Field(gt=0)
    amount_received: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    # Généré côté client (un identifiant stable par tentative d'encaissement,
    # réutilisé si la requête est renvoyée) : permet à PaymentService.create de
    # détecter une resoumission (double clic, retry réseau) et de renvoyer le
    # paiement déjà créé au lieu d'en créer un doublon.
    idempotency_key: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_amount_received(self) -> "PaymentCreate":
        if self.amount_received is not None and self.amount_received < self.amount:
            raise ValueError("Le montant reçu ne peut pas être inférieur au montant encaissé")
        return self


class PaymentVoidRequest(BaseModel):
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Le motif d'annulation est requis")
        return v


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    amount: float
    amount_received: Optional[float] = None
    change: Optional[float] = None
    note: Optional[str] = None
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    is_voided: bool
