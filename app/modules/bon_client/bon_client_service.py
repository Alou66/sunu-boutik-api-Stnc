from sqlalchemy.orm import Session

from app.modules.bon_client.bon_client_model import BonClient
from app.modules.bon_client.bon_client_repository import BonClientRepository


class BonClientNotFoundError(Exception):
    pass


class BonClientValidationError(Exception):
    pass


class BonClientService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = BonClientRepository(db)

    def list(self, shop_id: int, page: int, page_size: int, search: str | None) -> tuple[list[BonClient], int]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        return self._repo.list_paginated(shop_id, page, page_size, search)

    def get(self, shop_id: int, bon_client_id: int) -> BonClient:
        bon_client = self._repo.get_by_id(shop_id, bon_client_id)
        if not bon_client:
            raise BonClientNotFoundError("Bon client introuvable")
        return bon_client

    def create(self, shop_id: int, title: str, content: str) -> BonClient:
        title = (title or "").strip()
        content = (content or "").strip()
        if not title:
            raise BonClientValidationError("Le titre du bon client est requis")
        if not content:
            raise BonClientValidationError("Le contenu du bon client est requis")
        bon_client = BonClient(shop_id=shop_id, title=title, content=content)
        return self._repo.save_new(bon_client)

    def update(self, shop_id: int, bon_client_id: int, title: str | None, content: str | None) -> BonClient:
        # title/content=None signifie "champ non fourni, ne pas toucher" — le routeur
        # ne passe la valeur que si la clé était présente dans le payload
        # (payload.model_dump(exclude_unset=True)).
        bon_client = self.get(shop_id, bon_client_id)
        if title is not None:
            title = title.strip()
            if not title:
                raise BonClientValidationError("Le titre du bon client est requis")
            bon_client.title = title
        if content is not None:
            content = content.strip()
            if not content:
                raise BonClientValidationError("Le contenu du bon client est requis")
            bon_client.content = content
        return self._repo.save(bon_client)

    def delete(self, shop_id: int, bon_client_id: int) -> None:
        bon_client = self.get(shop_id, bon_client_id)
        self._repo.delete(bon_client)
