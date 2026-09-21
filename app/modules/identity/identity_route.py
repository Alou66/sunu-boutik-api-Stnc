from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_owner, get_current_user
from app.core.email import send_password_reset_code_email, send_signup_pending_emails
from app.core.limiter import limiter
from app.db.session import get_db
from app.modules.identity.identity_dto import (
    ChangePasswordRequest,
    ForgotPasswordCheck,
    ForgotPasswordConfirm,
    ForgotPasswordRequest,
    LoginRequest,
    MeOut,
    MeUpdate,
    MessageResponse,
    RegisterResponse,
    ResetPasswordRequest,
    ShopOut,
    ShopUpdate,
    Token,
    UserOut,
)
from app.modules.identity.identity_mapper import to_me_out, to_shop_out, to_user_out
from app.modules.identity.identity_model import User
from app.modules.identity.identity_service import (
    AccountDisabledError,
    CurrentPasswordIncorrectError,
    EmailAlreadyUsedError,
    IdentityService,
    InvalidCredentialsError,
    InvalidResetCodeError,
    NewPasswordTooShortError,
    PASSWORD_RESET_CODE_TTL,
    ProfileValidationError,
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


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: MeUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        user = IdentityService(db).update_profile(current_user, payload.model_dump(exclude_unset=True))
    except ProfileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except EmailAlreadyUsedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_user_out(user)


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
    current_user: User = Depends(get_current_owner),
    db: Session = Depends(get_db),
):
    try:
        shop = IdentityService(db).update_shop(current_user, payload.model_dump(exclude_unset=True))
    except ShopNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_shop_out(shop)


# Réinitialisation du mot de passe par e-mail + code temporaire à usage unique.
# Remplace l'ancien flux par numéro de téléphone (routes /check et /reset
# ci-dessous, conservées mais désactivées) : connaître le numéro d'une boutique
# suffisait à changer le mot de passe de son premier utilisateur.

_FORGOT_PASSWORD_REQUEST_MESSAGE = (
    "Si un compte correspond à cette adresse e-mail, un code de vérification vient de lui être envoyé."
)


@router.post("/forgot-password/request", response_model=MessageResponse)
@limiter.limit("5/minute")
def forgot_password_request(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # Réponse identique que le compte existe ou non (pas d'énumération de comptes),
    # et le code n'est jamais retourné : il part uniquement par e-mail.
    issued = IdentityService(db).request_password_reset(payload.email)
    if issued:
        full_name, email, code = issued
        background_tasks.add_task(
            send_password_reset_code_email,
            full_name,
            email,
            code,
            int(PASSWORD_RESET_CODE_TTL.total_seconds() // 60),
        )
    return MessageResponse(message=_FORGOT_PASSWORD_REQUEST_MESSAGE)


@router.post("/forgot-password/confirm", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def forgot_password_confirm(payload: ForgotPasswordConfirm, request: Request, db: Session = Depends(get_db)):
    try:
        IdentityService(db).confirm_password_reset(payload.email, payload.code, payload.new_password)
    except ResetPasswordTooShortError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidResetCodeError as e:
        raise HTTPException(status_code=400, detail=str(e))


_PHONE_RESET_DISABLED_DETAIL = (
    "La réinitialisation par numéro de téléphone n'est plus disponible. "
    "Utilisez la réinitialisation par e-mail (/auth/forgot-password/request)."
)


@router.post("/forgot-password/check")
@limiter.limit("10/minute")
def forgot_password_check(payload: ForgotPasswordCheck, request: Request, db: Session = Depends(get_db)):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_PHONE_RESET_DISABLED_DETAIL)


@router.post("/forgot-password/reset", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def forgot_password_reset(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_PHONE_RESET_DISABLED_DETAIL)
