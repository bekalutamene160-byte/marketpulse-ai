"""Authentication endpoints (Phase 2): register, login, logout, me, switch-org.

Session mechanics (blueprint 15.1, ADR-0025):

- ``mp_session``: HttpOnly, SameSite=Lax, Path=/, Secure outside local/test. The
  value is an opaque token; the server stores only its SHA-256 digest.
- ``mp_csrf``: readable so the SPA can echo it in ``X-CSRF-Token``; bound to the
  session row by digest. Every authenticated state change (logout, org switch)
  requires it — the service verifies the presented token against the stored digest.
- Login/register are rate limited per client IP (blueprint 14.2). All handlers are
  sync ``def`` (threadpool; ADR-0021).

Transaction boundaries here are EXPLICIT and ordered (the reason: a session row
references its user by FK, and a row inserted in one transaction is invisible to the
foreign-key check of another transaction until it commits):

1. ``register``: BEGIN(privileged) account creation -> COMMIT, then BEGIN(plain)
   session row -> COMMIT. If the account commit fails, no session is ever created.
2. ``login`` / ``logout`` / ``switch-organization``: single plain transaction.
3. ``me``: the normal tenant-scoped request transaction (``get_db_session``), whose
   context now comes from the session resolver instead of a dev header.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Request, Response, status

from marketpulse.api.deps import (
    ClockDep,
    MembershipRepositoryDep,
    OrganizationRepositoryDep,
    PlainSessionDep,
    PrivSessionDep,
    RateLimiterDep,
    SettingsDep,
    TenantContextDep,
    UserRepositoryDep,
    build_auth_service,
    build_signup_service,
)
from marketpulse.api.v1.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    OrganizationBrief,
    RegisterRequest,
    RegisterResponse,
    SwitchOrganizationRequest,
    SwitchOrganizationResponse,
    UserResponse,
    membership_briefs,
)
from marketpulse.application.services.auth import SessionTokens
from marketpulse.config import Settings
from marketpulse.core.clock import Clock
from marketpulse.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.ratelimit import FixedWindowRateLimiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest,
    response: Response,
    request: Request,
    settings: SettingsDep,
    clock: ClockDep,
    limiter: RateLimiterDep,
    priv: PrivSessionDep,
    plain: PlainSessionDep,
) -> RegisterResponse:
    _enforce_rate_limit(limiter, request, clock, "register")
    # 1) The account (organization + user + owner membership + workspace) commits
    #    FIRST, on the privileged connection, so the session row's FK can resolve.
    with priv.begin():
        org, user = build_signup_service(priv, clock).register(
            email=body.email, password=body.password, organization_name=body.organization_name
        )
    # 2) The login session on the plain application-role connection.
    with plain.begin():
        tokens = build_auth_service(plain, settings, clock).start_session(
            user_id=user.id, organization_id=org.id
        )
    _set_session_cookies(response, tokens, settings)
    return RegisterResponse(
        user=UserResponse.model_validate(user), organization=OrganizationBrief.model_validate(org)
    )


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    response: Response,
    request: Request,
    settings: SettingsDep,
    clock: ClockDep,
    limiter: RateLimiterDep,
    plain: PlainSessionDep,
) -> LoginResponse:
    _enforce_rate_limit(limiter, request, clock, "login")
    with plain.begin():
        outcome = build_auth_service(plain, settings, clock).login(
            email=body.email, password=body.password
        )
    _set_session_cookies(response, outcome.tokens, settings)
    return LoginResponse(
        user=UserResponse.model_validate(outcome.user),
        organization_id=outcome.tokens.session.organization_id,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    settings: SettingsDep,
    clock: ClockDep,
    plain: PlainSessionDep,
) -> None:
    with plain.begin():
        build_auth_service(plain, settings, clock).logout(
            session_token=request.cookies.get(SESSION_COOKIE, ""),
            csrf_token=request.headers.get(CSRF_HEADER),
        )
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/me", response_model=MeResponse)
def me(
    ctx: TenantContextDep,
    users: UserRepositoryDep,
    memberships: MembershipRepositoryDep,
    organizations: OrganizationRepositoryDep,
) -> MeResponse:
    if ctx.user_id is None:
        # A tenant context without a user identity cannot have a session: fail closed.
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            "Authentication is required to access this resource.",
            status_code=401,
            diagnostic="tenant context resolved without a user id for /auth/me",
        )
    user = users.get(ctx.user_id)
    if user is None:
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            "Authentication is required to access this resource.",
            status_code=401,
            diagnostic=f"user {ctx.user_id} not visible for /auth/me",
        )
    membership_rows = memberships.list_for_user(ctx.user_id)
    orgs = organizations.list_by_ids([m.organization_id for m in membership_rows])
    active = organizations.get(ctx.organization_id)
    return MeResponse(
        user=UserResponse.model_validate(user),
        active_organization=OrganizationBrief.model_validate(active) if active else None,
        memberships=membership_briefs(membership_rows, {o.id: o for o in orgs}),
    )


@router.post("/switch-organization", response_model=SwitchOrganizationResponse)
def switch_organization(
    body: SwitchOrganizationRequest,
    request: Request,
    settings: SettingsDep,
    clock: ClockDep,
    plain: PlainSessionDep,
) -> SwitchOrganizationResponse:
    with plain.begin():
        org = build_auth_service(plain, settings, clock).switch_organization(
            session_token=request.cookies.get(SESSION_COOKIE, ""),
            csrf_token=request.headers.get(CSRF_HEADER),
            organization_id=body.organization_id,
        )
    return SwitchOrganizationResponse(organization=OrganizationBrief.model_validate(org))


def _enforce_rate_limit(
    limiter: FixedWindowRateLimiter, request: Request, clock: Clock, action: str
) -> None:
    client = request.client
    ip = client.host if client is not None else "unknown"
    if not limiter.hit(f"{action}:{ip}", now=clock.utcnow().timestamp()):
        raise AppError(
            ErrorCode.RATE_LIMITED,
            "Too many attempts. Please wait a moment and try again.",
            status_code=429,
            diagnostic=f"rate limit exceeded for {action} from {ip}",
        )


def _set_session_cookies(response: Response, tokens: SessionTokens, settings: Settings) -> None:
    """Set the session + CSRF cookies with the production-safe flag set."""
    max_age = int(timedelta(hours=settings.session_lifetime_hours).total_seconds())
    secure = settings.environment in ("staging", "production")
    response.set_cookie(
        SESSION_COOKIE,
        tokens.session_token,
        max_age=max_age,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf_token,
        max_age=max_age,
        path="/",
        httponly=False,  # the SPA must read it to echo the X-CSRF-Token header
        samesite="lax",
        secure=secure,
    )
