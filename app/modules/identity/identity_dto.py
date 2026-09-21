from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


def _normalize(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordCheck(BaseModel):
    phone: str


class ResetPasswordRequest(BaseModel):
    phone: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordConfirm(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class MessageResponse(BaseModel):
    message: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterResponse(BaseModel):
    message: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    role: str
    shop_id: Optional[int] = None
    must_change_password: bool


class MeUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("full_name", "phone")
    @classmethod
    def normalize(cls, v: Optional[str]) -> Optional[str]:
        return _normalize(v)


class ShopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    phone2: Optional[str] = None
    phone3: Optional[str] = None
    ninea: Optional[str] = None
    rc: Optional[str] = None
    status: str


class ShopUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    phone2: Optional[str] = None
    phone3: Optional[str] = None
    ninea: Optional[str] = None
    rc: Optional[str] = None


class MeOut(BaseModel):
    user: UserOut
    shop: Optional[ShopOut] = None
