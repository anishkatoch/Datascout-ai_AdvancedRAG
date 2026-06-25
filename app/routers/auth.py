import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from app.services import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response schemas ────────────────────────────────────────────────

class SignUpRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class SignInRequest(BaseModel):
    email: EmailStr
    password: str

class GuestRequest(BaseModel):
    name: str
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    token: str

class ResendOtpRequest(BaseModel):
    email: EmailStr

class AuthResponse(BaseModel):
    token: str | None
    needs_otp: bool = False
    user: dict


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse)
async def signup(req: SignUpRequest):
    try:
        result = auth_service.signup(req.name, req.email, req.password)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"[AUTH] Signup error: {e}")
        raise HTTPException(500, "Sign up failed. Please try again.")


@router.post("/signin", response_model=AuthResponse)
async def signin(req: SignInRequest):
    try:
        result = auth_service.signin(req.email, req.password)
        return result
    except ValueError as e:
        raise HTTPException(401, str(e))
    except Exception as e:
        logger.error(f"[AUTH] Signin error: {e}")
        raise HTTPException(500, "Sign in failed. Please try again.")


@router.post("/guest", response_model=AuthResponse)
async def guest_signin(req: GuestRequest):
    token = auth_service.create_guest_token(req.name, req.email)
    logger.info(f"[AUTH] Guest signin: {req.email}")
    return {
        "token": token,
        "user": {
            "id":    f"guest-{req.email}",
            "email": req.email,
            "name":  req.name,
            "role":  "guest",
        },
    }


@router.post("/verify-otp", response_model=AuthResponse)
async def verify_otp(req: VerifyOtpRequest):
    try:
        result = auth_service.verify_otp(req.email, req.token)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"[AUTH] OTP verify error: {e}")
        raise HTTPException(500, "Verification failed. Please try again.")


@router.post("/resend-otp")
async def resend_otp(req: ResendOtpRequest):
    try:
        sb = auth_service._supabase()
        sb.auth.sign_in_with_otp({
            "email": req.email,
            "options": {"should_create_user": False},
        })
        logger.info(f"[AUTH] OTP resent: {req.email}")
    except Exception as e:
        logger.warning(f"[AUTH] Resend OTP failed: {e}")
    # Always return success to prevent email enumeration
    return {"message": "Code sent"}


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    try:
        auth_service.forgot_password(req.email)
        return {"message": "Password reset email sent. Check your inbox."}
    except Exception as e:
        logger.error(f"[AUTH] Forgot password error: {e}")
        # Always return success to avoid email enumeration
        return {"message": "Password reset email sent. Check your inbox."}


@router.get("/me")
async def me(request: Request):
    token = _extract_token(request)
    if not token:
        raise HTTPException(401, "Not authenticated")
    user = auth_service.verify_token(token)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user


# ── Helper ────────────────────────────────────────────────────────────────────

def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None
