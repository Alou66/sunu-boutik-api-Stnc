from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String, Boolean, text
from sqlalchemy.orm import relationship

from app.db.session import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        # Filet de sécurité applicatif doublé ici : un article transformable a
        # forcément une forme secondaire et un taux de conversion positif (la
        # forme principale réutilise `unit`, déjà non-null). Voir la validation
        # côté service dans products_service.py — cette contrainte est le
        # dernier rempart.
        CheckConstraint(
            "NOT is_transformable OR ("
            "unit_secondaire IS NOT NULL AND conversion_ratio > 0 AND unit_price_secondaire >= 0"
            ")",
            name="ck_products_transformable_fields",
        ),
        CheckConstraint("quantity_secondaire >= 0", name="ck_products_quantity_secondaire_non_negative"),
        # Filet de sécurité applicatif doublé ici (comme pour quantity_secondaire
        # ci-dessus) : aucune vente/transformation ne doit pouvoir faire passer le
        # stock en forme principale sous zéro, même en cas de bug applicatif — la
        # vraie protection contre la survente concurrente reste le verrou FOR
        # UPDATE posé sur la ligne produit (voir billing_service.py::_apply_lines).
        CheckConstraint("quantity >= 0", name="ck_products_quantity_non_negative"),
        # Index unique insensible à la casse : "Riz", "riz" et "RIZ" sont le même
        # article dans une boutique donnée (même principe que
        # uq_clients_shop_id_lower_name). La vérification applicative de
        # products_service.py (message d'erreur clair, 409) reste la première
        # ligne de défense ; cet index est le filet de sécurité en base, y
        # compris contre deux créations simultanées du même nom.
        Index("uq_products_shop_id_upper_name", "shop_id", text("upper(name)"), unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    reference = Column(String(100), nullable=True)
    unit_price = Column(Float, nullable=False, default=0)
    # Prix d'achat (coût fournisseur), distinct du prix de vente ci-dessus.
    # Sert de valeur par défaut pour "Coût U" dans le module Approvisionnement
    # (voir stock_receipts_service.py::_build_lines) ; l'utilisateur peut
    # toujours le surcharger ligne par ligne au moment de la réception.
    purchase_price = Column(Float, nullable=False, default=0, server_default="0")
    quantity = Column(Float, nullable=False, default=0)
    unit = Column(String(20), default="unite")
    pack_size = Column(Float, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ---- Transformation (ex: 1 carton -> 4 seaux) ----
    # `unit` ci-dessus sert de nom à la forme principale (ex: "carton") quand
    # is_transformable est vrai ; `quantity` ci-dessus est le stock dans cette
    # forme principale. Les colonnes suivantes couvrent la forme secondaire.
    is_transformable = Column(Boolean, nullable=False, default=False, server_default="false")
    unit_secondaire = Column(String(20), nullable=True)
    # 1 unité de forme principale (`unit`) = conversion_ratio unité(s) de forme
    # secondaire (`unit_secondaire`).
    conversion_ratio = Column(Float, nullable=True)
    unit_price_secondaire = Column(Float, nullable=True)
    purchase_price_secondaire = Column(Float, nullable=True)
    quantity_secondaire = Column(Float, nullable=False, default=0, server_default="0")

    shop = relationship("Shop", back_populates="products")
    category = relationship("Category", back_populates="products")
