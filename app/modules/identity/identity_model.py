import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.session import Base


class UserRole(str, enum.Enum):
    OWNER = "owner"
    EMPLOYEE = "employee"
    ADMIN = "admin"


class ShopStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    address = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    phone2 = Column(String(50), nullable=True)
    phone3 = Column(String(50), nullable=True)
    ninea = Column(String(50), nullable=True)
    rc = Column(String(100), nullable=True)
    status = Column(Enum(ShopStatus), default=ShopStatus.PENDING, nullable=False)
    logo_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    users = relationship("User", back_populates="shop", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="shop", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="shop", cascade="all, delete-orphan")
    clients = relationship("Client", back_populates="shop", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="shop", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="shop", cascade="all, delete-orphan")
    transformation_logs = relationship("TransformationLog", back_populates="shop", cascade="all, delete-orphan")
    bon_clients = relationship("BonClient", back_populates="shop", cascade="all, delete-orphan")
    suppliers = relationship("Supplier", back_populates="shop", cascade="all, delete-orphan")
    stock_receipts = relationship("StockReceipt", back_populates="shop", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=True, index=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    phone = Column(String(50), nullable=True)
    hashed_password = Column(String(255), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.OWNER, nullable=False)
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=False, nullable=False)
    # Incrémenté à chaque désactivation : les JWT déjà émis portent le token_version
    # au moment de leur création (claim "tv") et sont rejetés si ce nombre a bougé,
    # même après une réactivation du compte (voir core/deps.get_current_user).
    token_version = Column(Integer, default=0, nullable=False)
    # Réinitialisation du mot de passe par e-mail (voir
    # IdentityService.request_password_reset / confirm_password_reset). Un seul
    # code actif par utilisateur : une nouvelle demande écrase l'ancien, et un
    # code consommé/expiré/épuisé est remis à NULL (usage unique). Seul le HMAC
    # du code est stocké, jamais le code.
    reset_code_hash = Column(String(64), nullable=True)
    reset_code_expires_at = Column(DateTime, nullable=True)
    reset_code_attempts = Column(Integer, default=0, nullable=False, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="users")
