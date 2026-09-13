from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.email import send_signup_pending_emails
from app.core.limiter import limiter
from app.db.session import get_db
from app.modules.identity.identity_dto import (
    ChangePasswordRequest,
    ForgotPasswordCheck,
    LoginRequest,
    MeOut,
    RegisterResponse,
    ResetPasswordRequest,
    ShopOut,
    ShopUpdate,
    Token,
)
from app.modules.identity.identity_mapper import to_me_out, to_shop_out
from app.modules.identity.identity_model import User
from app.modules.identity.identity_service import (
    AccountDisabledError,
    AccountNotFoundByPhoneError,
    CurrentPasswordIncorrectError,
    EmailAlreadyUsedError,
    IdentityService,
    InvalidCredentialsError,
    NewPasswordTooShortError,
    PhoneNotFoundError,
    ResetPasswordTooShortError,
    ShopNotFoundError,
    ShopPendingError,
    ShopRejectedError,
    ShopSuspendedError,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    background_tasks: BackgroundTasks,
    shop_name: str = Form(...),
    shop_address: str | None = Form(None),
    shop_phone: str | None = Form(None),
    shop_phone2: str | None = Form(None),
    shop_phone3: str | None = Form(None),
    shop_ninea: str | None = Form(None),
    shop_rc: str | None = Form(None),
    full_name: str = Form(...),
    email: str = Form(...),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    try:
        shop, user = await IdentityService(db).register(
            shop_name, shop_address, shop_phone, shop_phone2, shop_phone3, shop_ninea, shop_rc,
            full_name, email, logo,
        )
    except EmailAlreadyUsedError as e:
        raise HTTPException(status_code=400, detail=str(e))

    origin = request.headers.get("origin")
    background_tasks.add_task(
        send_signup_pending_emails, shop.name, user.full_name, user.email, origin
    )

    return RegisterResponse(
        message="Votre demande a été enregistrée. Elle est en cours de traitement par notre équipe."
    )


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        token = IdentityService(db).login(payload.email, payload.password)
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except (ShopPendingError, ShopRejectedError, ShopSuspendedError, AccountDisabledError) as e:
        raise HTTPException(status_code=403, detail=str(e))
    return Token(access_token=token)


@router.get("/me", response_model=MeOut)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = IdentityService(db).get_shop_for_user(current_user)
    return to_me_out(current_user, shop)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        IdentityService(db).change_password(current_user, payload.current_password, payload.new_password)
    except CurrentPasswordIncorrectError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except NewPasswordTooShortError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/shop", response_model=ShopOut)
def update_shop(
    payload: ShopUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        shop = IdentityService(db).update_shop(current_user, payload.model_dump(exclude_unset=True))
    except ShopNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_shop_out(shop)


@router.post("/forgot-password/check")
@limiter.limit("10/minute")
def forgot_password_check(payload: ForgotPasswordCheck, request: Request, db: Session = Depends(get_db)):
    try:
        shop = IdentityService(db).forgot_password_check(payload.phone)
    except AccountNotFoundByPhoneError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "Numéro vérifié", "shop_name": shop.name}


@router.post("/forgot-password/reset", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def forgot_password_reset(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    try:
        IdentityService(db).forgot_password_reset(payload.phone, payload.new_password)
    except ResetPasswordTooShortError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PhoneNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
