from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select

from ..db import AuthSession, SessionLocal, UserAccount, utc_now


logger = logging.getLogger(__name__)


# ============================================================================
# VALIDATION / SECURITY CONSTANTS
# ============================================================================

_EMAIL = re.compile(
    r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
)

_USERNAME = re.compile(
    r"^[A-Za-z0-9_.-]{3,80}$"
)

_PASSWORD_UPPER = re.compile(
    r"[A-Z]"
)

_PASSWORD_LOWER = re.compile(
    r"[a-z]"
)

_PASSWORD_DIGIT = re.compile(
    r"\d"
)

_PASSWORD_SYMBOL = re.compile(
    r"[^A-Za-z0-9]"
)


_PBKDF2_ALGORITHM = "pbkdf2_sha256"
_PBKDF2_ROUNDS = 310_000
_PBKDF2_SALT_BYTES = 16

_SESSION_DAYS = 30
_SESSION_TOKEN_BYTES = 48

_MAX_EMAIL_LENGTH = 320
_MAX_USERNAME_LENGTH = 80
_MAX_DISPLAY_NAME_LENGTH = 160

_MIN_PASSWORD_LENGTH = 10
_MAX_PASSWORD_LENGTH = 1024

_MAX_ACTIVE_SESSIONS = 20


# ============================================================================
# RESULTS
# ============================================================================


@dataclass(
    frozen=True,
    slots=True,
)
class AuthResult:
    token: str
    user: dict[str, Any]
    expires_at: str


@dataclass(
    frozen=True,
    slots=True,
)
class SessionResult:
    user: dict[str, Any]
    expires_at: str | None
    last_seen_at: str | None


# ============================================================================
# ERRORS
# ============================================================================


class AuthError(ValueError):
    """
    Base PhoenixTrend authentication error.

    Messages are safe for presentation to the client.
    """

    code = "AUTH_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(
            message
        )

        self.code = (
            code
            or self.code
        )


class InvalidCredentialsError(
    AuthError
):
    code = "INVALID_CREDENTIALS"


class AccountDisabledError(
    AuthError
):
    code = "ACCOUNT_DISABLED"


class DuplicateAccountError(
    AuthError
):
    code = "ACCOUNT_EXISTS"


class DuplicateUsernameError(
    AuthError
):
    code = "USERNAME_EXISTS"


class InvalidSessionError(
    AuthError
):
    code = "INVALID_SESSION"


class ExpiredSessionError(
    AuthError
):
    code = "SESSION_EXPIRED"


# ============================================================================
# NORMALIZATION
# ============================================================================


def _normalize_email(
    value: str,
) -> str:
    email = (
        value
        or ""
    ).strip().lower()

    if (
        not email
        or len(
            email
        )
        > _MAX_EMAIL_LENGTH
        or not _EMAIL.fullmatch(
            email
        )
    ):
        raise AuthError(
            "Enter a valid email address.",
            code="INVALID_EMAIL",
        )

    return email


def _normalize_username(
    value: str,
    email: str,
) -> str:
    username = (
        value
        or ""
    ).strip()

    if not username:
        username = email.split(
            "@",
            1,
        )[0]

    username = username.lower()

    if (
        len(
            username
        )
        > _MAX_USERNAME_LENGTH
        or not _USERNAME.fullmatch(
            username
        )
    ):
        raise AuthError(
            (
                "Username must be 3-80 characters and use "
                "letters, numbers, '.', '_' or '-'."
            ),
            code="INVALID_USERNAME",
        )

    return username


def _normalize_display_name(
    value: str | None,
    fallback: str,
) -> str:
    name = (
        value
        or ""
    ).strip()

    if not name:
        name = fallback

    # Avoid storing control characters in profile data.
    name = "".join(
        character
        for character in name
        if (
            character.isprintable()
            and character
            not in {
                "\r",
                "\n",
                "\t",
            }
        )
    ).strip()

    if not name:
        name = fallback

    return name[
        :_MAX_DISPLAY_NAME_LENGTH
    ]


# ============================================================================
# PASSWORD VALIDATION
# ============================================================================


def _validate_password(
    password: str,
) -> None:
    if not isinstance(
        password,
        str,
    ):
        raise AuthError(
            "Password is required.",
            code="INVALID_PASSWORD",
        )

    if len(
        password
    ) < _MIN_PASSWORD_LENGTH:
        raise AuthError(
            (
                f"Password must contain at least "
                f"{_MIN_PASSWORD_LENGTH} characters."
            ),
            code="WEAK_PASSWORD",
        )

    if len(
        password
    ) > _MAX_PASSWORD_LENGTH:
        raise AuthError(
            "Password is too long.",
            code="INVALID_PASSWORD",
        )

    if not _PASSWORD_UPPER.search(
        password
    ):
        raise AuthError(
            "Password must include an uppercase letter.",
            code="WEAK_PASSWORD",
        )

    if not _PASSWORD_LOWER.search(
        password
    ):
        raise AuthError(
            "Password must include a lowercase letter.",
            code="WEAK_PASSWORD",
        )

    if not _PASSWORD_DIGIT.search(
        password
    ):
        raise AuthError(
            "Password must include a number.",
            code="WEAK_PASSWORD",
        )


# ============================================================================
# PASSWORD HASHING
# ============================================================================


def _password_hash(
    password: str,
) -> str:
    """
    Hash a password with PBKDF2-HMAC-SHA256.

    Passwords are never persisted or logged in plaintext.
    """

    _validate_password(
        password
    )

    salt = os.urandom(
        _PBKDF2_SALT_BYTES
    )

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(
            "utf-8"
        ),
        salt,
        _PBKDF2_ROUNDS,
    )

    return (
        f"{_PBKDF2_ALGORITHM}"
        f"${_PBKDF2_ROUNDS}"
        f"${salt.hex()}"
        f"${digest.hex()}"
    )


def _verify_password(
    password: str,
    encoded: str,
) -> bool:
    """
    Constant-time password verification.

    Malformed stored hashes fail closed.
    """

    if (
        not isinstance(
            password,
            str,
        )
        or not isinstance(
            encoded,
            str,
        )
    ):
        return False

    try:
        (
            algorithm,
            rounds_text,
            salt_hex,
            digest_hex,
        ) = encoded.split(
            "$",
            3,
        )

        if (
            algorithm
            != _PBKDF2_ALGORITHM
        ):
            return False

        rounds = int(
            rounds_text
        )

        if rounds <= 0:
            return False

        salt = bytes.fromhex(
            salt_hex
        )

        expected = bytes.fromhex(
            digest_hex
        )

        if (
            not salt
            or not expected
        ):
            return False

        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(
                "utf-8"
            ),
            salt,
            rounds,
            dklen=len(
                expected
            ),
        )

        return hmac.compare_digest(
            candidate,
            expected,
        )

    except (
        AttributeError,
        TypeError,
        ValueError,
        OverflowError,
    ):
        return False


def _password_needs_rehash(
    encoded: str,
) -> bool:
    """
    Allow existing accounts to migrate forward when PBKDF2 parameters
    increase without requiring a forced password reset.
    """

    try:
        (
            algorithm,
            rounds_text,
            _salt_hex,
            _digest_hex,
        ) = encoded.split(
            "$",
            3,
        )

        if (
            algorithm
            != _PBKDF2_ALGORITHM
        ):
            return True

        rounds = int(
            rounds_text
        )

        return (
            rounds
            < _PBKDF2_ROUNDS
        )

    except (
        AttributeError,
        TypeError,
        ValueError,
    ):
        return True


# ============================================================================
# SESSION TOKEN HELPERS
# ============================================================================


def _generate_token() -> str:
    return secrets.token_urlsafe(
        _SESSION_TOKEN_BYTES
    )


def _token_hash(
    token: str,
) -> str:
    return hashlib.sha256(
        token.encode(
            "utf-8"
        )
    ).hexdigest()


def _normalize_token(
    token: str | None,
) -> str | None:
    if not token:
        return None

    normalized = str(
        token
    ).strip()

    if not normalized:
        return None

    return normalized


# ============================================================================
# DATETIME HELPERS
# ============================================================================


def _aware_utc(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _datetime_le(
    left: datetime,
    right: datetime,
) -> bool:
    normalized_left = _aware_utc(
        left
    )

    normalized_right = _aware_utc(
        right
    )

    if (
        normalized_left is None
        or normalized_right is None
    ):
        return False

    return (
        normalized_left
        <= normalized_right
    )


def _iso(
    value: datetime | None,
) -> str | None:
    normalized = _aware_utc(
        value
    )

    return (
        normalized.isoformat()
        if normalized
        else None
    )


# ============================================================================
# PUBLIC USER VIEW
# ============================================================================


def _public_user(
    user: UserAccount,
) -> dict[str, Any]:
    """
    Return only fields safe for authenticated client consumption.

    password_hash is deliberately never exposed.
    """

    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": (
            user.display_name
        ),
        "is_active": bool(
            user.is_active
        ),
        "created_at": _iso(
            getattr(
                user,
                "created_at",
                None,
            )
        ),
        "updated_at": _iso(
            getattr(
                user,
                "updated_at",
                None,
            )
        ),
    }


# ============================================================================
# AUTH SERVICE
# ============================================================================


class AuthService:
    """
    PhoenixTrend account/session authentication service.

    Responsibilities:

        - account registration
        - normalized unique email/username handling
        - password validation
        - password hashing
        - password verification
        - secure opaque session creation
        - hashed session-token persistence
        - session restoration
        - session expiration enforcement
        - session revocation
        - password change
        - profile update
        - session cleanup

    The service never stores plaintext passwords or plaintext session
    tokens in the database.
    """

    # ========================================================================
    # REGISTER
    # ========================================================================

    def register(
        self,
        *,
        email: str,
        username: str = "",
        display_name: str = "",
        password: str,
    ) -> AuthResult:
        normalized_email = (
            _normalize_email(
                email
            )
        )

        normalized_username = (
            _normalize_username(
                username,
                normalized_email,
            )
        )

        _validate_password(
            password
        )

        normalized_name = (
            _normalize_display_name(
                display_name,
                normalized_username,
            )
        )

        password_hash = (
            _password_hash(
                password
            )
        )

        with SessionLocal() as db:
            existing_email = db.scalar(
                select(
                    UserAccount
                ).where(
                    UserAccount.email
                    == normalized_email
                )
            )

            if existing_email is not None:
                raise DuplicateAccountError(
                    (
                        "An account already exists "
                        "for this email address."
                    )
                )

            existing_username = db.scalar(
                select(
                    UserAccount
                ).where(
                    UserAccount.username
                    == normalized_username
                )
            )

            if existing_username is not None:
                raise DuplicateUsernameError(
                    "That username is already in use."
                )

            user = UserAccount(
                email=normalized_email,
                username=normalized_username,
                display_name=normalized_name,
                password_hash=password_hash,
                is_active=True,
            )

            try:
                db.add(
                    user
                )

                db.flush()

                result = self._create_session(
                    db,
                    user,
                    commit=False,
                )

                db.commit()

                db.refresh(
                    user
                )

                return AuthResult(
                    token=result.token,
                    user=_public_user(
                        user
                    ),
                    expires_at=(
                        result.expires_at
                    ),
                )

            except AuthError:
                db.rollback()
                raise

            except Exception:
                db.rollback()

                logger.exception(
                    "Failed to register account"
                )

                raise AuthError(
                    "Unable to create the account.",
                    code="REGISTRATION_FAILED",
                )

    # ========================================================================
    # LOGIN
    # ========================================================================

    def login(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthResult:
        normalized_email = (
            _normalize_email(
                email
            )
        )

        supplied_password = (
            password
            if isinstance(
                password,
                str,
            )
            else ""
        )

        with SessionLocal() as db:
            user = db.scalar(
                select(
                    UserAccount
                ).where(
                    UserAccount.email
                    == normalized_email
                )
            )

            # Deliberately use the same client-facing error for an unknown
            # account and an incorrect password.
            if user is None:
                raise InvalidCredentialsError(
                    "Invalid email address or password."
                )

            if not _verify_password(
                supplied_password,
                user.password_hash,
            ):
                raise InvalidCredentialsError(
                    "Invalid email address or password."
                )

            if not bool(
                user.is_active
            ):
                raise AccountDisabledError(
                    "This account is disabled."
                )

            try:
                if _password_needs_rehash(
                    user.password_hash
                ):
                    user.password_hash = (
                        _password_hash(
                            supplied_password
                        )
                    )

                result = self._create_session(
                    db,
                    user,
                    commit=False,
                )

                db.commit()

                return AuthResult(
                    token=result.token,
                    user=_public_user(
                        user
                    ),
                    expires_at=(
                        result.expires_at
                    ),
                )

            except AuthError:
                db.rollback()
                raise

            except Exception:
                db.rollback()

                logger.exception(
                    "Failed to create login session"
                )

                raise AuthError(
                    "Unable to complete login.",
                    code="LOGIN_FAILED",
                )

    # ========================================================================
    # CREATE SESSION
    # ========================================================================

    def _create_session(
        self,
        db: Any,
        user: UserAccount,
        *,
        commit: bool = True,
    ) -> AuthResult:
        if not bool(
            user.is_active
        ):
            raise AccountDisabledError(
                "This account is disabled."
            )

        token = _generate_token()

        token_digest = (
            _token_hash(
                token
            )
        )

        now = utc_now()

        expires = (
            now
            + timedelta(
                days=_SESSION_DAYS
            )
        )

        session = AuthSession(
            user_id=user.id,
            token_hash=token_digest,
            expires_at=expires,
        )

        if hasattr(
            session,
            "last_seen_at",
        ):
            session.last_seen_at = now

        db.add(
            session
        )

        db.flush()

        self._limit_active_sessions(
            db,
            user.id,
            keep_session=session,
        )

        if commit:
            db.commit()

        return AuthResult(
            token=token,
            user=_public_user(
                user
            ),
            expires_at=(
                _iso(
                    expires
                )
                or expires.isoformat()
            ),
        )

    # ========================================================================
    # AUTHENTICATE
    # ========================================================================

    def authenticate(
        self,
        token: str | None,
    ) -> dict[str, Any] | None:
        normalized_token = (
            _normalize_token(
                token
            )
        )

        if normalized_token is None:
            return None

        token_digest = (
            _token_hash(
                normalized_token
            )
        )

        now = utc_now()

        with SessionLocal() as db:
            session = db.scalar(
                select(
                    AuthSession
                ).where(
                    AuthSession.token_hash
                    == token_digest
                )
            )

            if session is None:
                return None

            if bool(
                getattr(
                    session,
                    "revoked",
                    False,
                )
            ):
                return None

            expires_at = getattr(
                session,
                "expires_at",
                None,
            )

            if (
                expires_at is None
                or _datetime_le(
                    expires_at,
                    now,
                )
            ):
                if hasattr(
                    session,
                    "revoked",
                ):
                    session.revoked = True

                    try:
                        db.commit()
                    except Exception:
                        db.rollback()

                return None

            user = db.get(
                UserAccount,
                session.user_id,
            )

            if (
                user is None
                or not bool(
                    user.is_active
                )
            ):
                if hasattr(
                    session,
                    "revoked",
                ):
                    session.revoked = True

                    try:
                        db.commit()
                    except Exception:
                        db.rollback()

                return None

            if hasattr(
                session,
                "last_seen_at",
            ):
                session.last_seen_at = now

                try:
                    db.commit()
                except Exception:
                    db.rollback()

                    logger.exception(
                        (
                            "Failed to update authentication "
                            "session last_seen_at"
                        )
                    )

            return _public_user(
                user
            )

    # ========================================================================
    # AUTHENTICATE WITH SESSION METADATA
    # ========================================================================

    def session(
        self,
        token: str | None,
    ) -> SessionResult | None:
        normalized_token = (
            _normalize_token(
                token
            )
        )

        if normalized_token is None:
            return None

        token_digest = (
            _token_hash(
                normalized_token
            )
        )

        now = utc_now()

        with SessionLocal() as db:
            auth_session = db.scalar(
                select(
                    AuthSession
                ).where(
                    AuthSession.token_hash
                    == token_digest
                )
            )

            if auth_session is None:
                return None

            if bool(
                getattr(
                    auth_session,
                    "revoked",
                    False,
                )
            ):
                return None

            expires_at = getattr(
                auth_session,
                "expires_at",
                None,
            )

            if (
                expires_at is None
                or _datetime_le(
                    expires_at,
                    now,
                )
            ):
                return None

            user = db.get(
                UserAccount,
                auth_session.user_id,
            )

            if (
                user is None
                or not bool(
                    user.is_active
                )
            ):
                return None

            if hasattr(
                auth_session,
                "last_seen_at",
            ):
                auth_session.last_seen_at = now

                try:
                    db.commit()
                except Exception:
                    db.rollback()

            return SessionResult(
                user=_public_user(
                    user
                ),
                expires_at=_iso(
                    expires_at
                ),
                last_seen_at=_iso(
                    getattr(
                        auth_session,
                        "last_seen_at",
                        None,
                    )
                ),
            )

    # ========================================================================
    # REQUIRE AUTHENTICATION
    # ========================================================================

    def require(
        self,
        token: str | None,
    ) -> dict[str, Any]:
        user = self.authenticate(
            token
        )

        if user is None:
            raise InvalidSessionError(
                "Authentication is required."
            )

        return user

    # ========================================================================
    # CURRENT USER
    # ========================================================================

    def current_user(
        self,
        token: str | None,
    ) -> dict[str, Any] | None:
        return self.authenticate(
            token
        )

    # ========================================================================
    # LOGOUT CURRENT SESSION
    # ========================================================================

    def logout(
        self,
        token: str | None,
    ) -> bool:
        normalized_token = (
            _normalize_token(
                token
            )
        )

        if normalized_token is None:
            return False

        token_digest = (
            _token_hash(
                normalized_token
            )
        )

        with SessionLocal() as db:
            session = db.scalar(
                select(
                    AuthSession
                ).where(
                    AuthSession.token_hash
                    == token_digest
                )
            )

            if session is None:
                return False

            if bool(
                getattr(
                    session,
                    "revoked",
                    False,
                )
            ):
                return True

            session.revoked = True

            try:
                db.commit()
                return True

            except Exception:
                db.rollback()

                logger.exception(
                    "Failed to revoke authentication session"
                )

                return False

    # ========================================================================
    # LOGOUT ALL SESSIONS
    # ========================================================================

    def logout_all(
        self,
        token: str | None,
    ) -> int:
        """
        Revoke all sessions belonging to the currently authenticated user.
        """

        normalized_token = (
            _normalize_token(
                token
            )
        )

        if normalized_token is None:
            return 0

        token_digest = (
            _token_hash(
                normalized_token
            )
        )

        with SessionLocal() as db:
            current = db.scalar(
                select(
                    AuthSession
                ).where(
                    AuthSession.token_hash
                    == token_digest
                )
            )

            if (
                current is None
                or bool(
                    getattr(
                        current,
                        "revoked",
                        False,
                    )
                )
            ):
                return 0

            now = utc_now()

            expires_at = getattr(
                current,
                "expires_at",
                None,
            )

            if (
                expires_at is None
                or _datetime_le(
                    expires_at,
                    now,
                )
            ):
                return 0

            sessions = list(
                db.scalars(
                    select(
                        AuthSession
                    ).where(
                        AuthSession.user_id
                        == current.user_id
                    )
                ).all()
            )

            count = 0

            for session in sessions:
                if not bool(
                    getattr(
                        session,
                        "revoked",
                        False,
                    )
                ):
                    session.revoked = True
                    count += 1

            try:
                db.commit()
                return count

            except Exception:
                db.rollback()

                logger.exception(
                    "Failed to revoke all authentication sessions"
                )

                return 0

    # ========================================================================
    # CHANGE PASSWORD
    # ========================================================================

    def change_password(
        self,
        *,
        token: str,
        current_password: str,
        new_password: str,
        revoke_other_sessions: bool = True,
    ) -> bool:
        normalized_token = (
            _normalize_token(
                token
            )
        )

        if normalized_token is None:
            raise InvalidSessionError(
                "Authentication is required."
            )

        _validate_password(
            new_password
        )

        token_digest = (
            _token_hash(
                normalized_token
            )
        )

        now = utc_now()

        with SessionLocal() as db:
            current_session = db.scalar(
                select(
                    AuthSession
                ).where(
                    AuthSession.token_hash
                    == token_digest
                )
            )

            if (
                current_session is None
                or bool(
                    getattr(
                        current_session,
                        "revoked",
                        False,
                    )
                )
            ):
                raise InvalidSessionError(
                    "Authentication is required."
                )

            expires_at = getattr(
                current_session,
                "expires_at",
                None,
            )

            if (
                expires_at is None
                or _datetime_le(
                    expires_at,
                    now,
                )
            ):
                raise ExpiredSessionError(
                    "The authentication session has expired."
                )

            user = db.get(
                UserAccount,
                current_session.user_id,
            )

            if (
                user is None
                or not bool(
                    user.is_active
                )
            ):
                raise InvalidSessionError(
                    "Authentication is required."
                )

            if not _verify_password(
                current_password
                or "",
                user.password_hash,
            ):
                raise InvalidCredentialsError(
                    "Current password is incorrect."
                )

            if _verify_password(
                new_password,
                user.password_hash,
            ):
                raise AuthError(
                    (
                        "New password must be different "
                        "from the current password."
                    ),
                    code="PASSWORD_UNCHANGED",
                )

            user.password_hash = (
                _password_hash(
                    new_password
                )
            )

            if revoke_other_sessions:
                sessions = list(
                    db.scalars(
                        select(
                            AuthSession
                        ).where(
                            AuthSession.user_id
                            == user.id
                        )
                    ).all()
                )

                for session in sessions:
                    if (
                        session.id
                        != current_session.id
                    ):
                        session.revoked = True

            try:
                db.commit()
                return True

            except Exception:
                db.rollback()

                logger.exception(
                    "Failed to change account password"
                )

                raise AuthError(
                    "Unable to update the password.",
                    code="PASSWORD_UPDATE_FAILED",
                )

    # ========================================================================
    # UPDATE PROFILE
    # ========================================================================

    def update_profile(
        self,
        *,
        token: str,
        username: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        normalized_token = (
            _normalize_token(
                token
            )
        )

        if normalized_token is None:
            raise InvalidSessionError(
                "Authentication is required."
            )

        token_digest = (
            _token_hash(
                normalized_token
            )
        )

        now = utc_now()

        with SessionLocal() as db:
            session = db.scalar(
                select(
                    AuthSession
                ).where(
                    AuthSession.token_hash
                    == token_digest
                )
            )

            if (
                session is None
                or bool(
                    getattr(
                        session,
                        "revoked",
                        False,
                    )
                )
            ):
                raise InvalidSessionError(
                    "Authentication is required."
                )

            expires_at = getattr(
                session,
                "expires_at",
                None,
            )

            if (
                expires_at is None
                or _datetime_le(
                    expires_at,
                    now,
                )
            ):
                raise ExpiredSessionError(
                    "The authentication session has expired."
                )

            user = db.get(
                UserAccount,
                session.user_id,
            )

            if (
                user is None
                or not bool(
                    user.is_active
                )
            ):
                raise InvalidSessionError(
                    "Authentication is required."
                )

            if username is not None:
                normalized_username = (
                    _normalize_username(
                        username,
                        user.email,
                    )
                )

                if (
                    normalized_username
                    != user.username
                ):
                    existing = db.scalar(
                        select(
                            UserAccount
                        ).where(
                            UserAccount.username
                            == normalized_username
                        )
                    )

                    if (
                        existing is not None
                        and existing.id
                        != user.id
                    ):
                        raise DuplicateUsernameError(
                            (
                                "That username is "
                                "already in use."
                            )
                        )

                    user.username = (
                        normalized_username
                    )

            if display_name is not None:
                user.display_name = (
                    _normalize_display_name(
                        display_name,
                        user.username,
                    )
                )

            try:
                db.commit()
                db.refresh(
                    user
                )

                return _public_user(
                    user
                )

            except AuthError:
                db.rollback()
                raise

            except Exception:
                db.rollback()

                logger.exception(
                    "Failed to update account profile"
                )

                raise AuthError(
                    "Unable to update the profile.",
                    code="PROFILE_UPDATE_FAILED",
                )

    # ========================================================================
    # SESSION VALIDITY
    # ========================================================================

    def is_authenticated(
        self,
        token: str | None,
    ) -> bool:
        return (
            self.authenticate(
                token
            )
            is not None
        )

    # ========================================================================
    # CLEAN EXPIRED SESSIONS
    # ========================================================================

    def cleanup_expired_sessions(
        self,
        *,
        delete_rows: bool = False,
    ) -> int:
        """
        Clean expired sessions.

        By default expired sessions are revoked for audit/history safety.

        delete_rows=True physically deletes expired rows.
        """

        now = utc_now()

        with SessionLocal() as db:
            try:
                sessions = list(
                    db.scalars(
                        select(
                            AuthSession
                        )
                    ).all()
                )

                expired = [
                    session
                    for session
                    in sessions
                    if (
                        getattr(
                            session,
                            "expires_at",
                            None,
                        )
                        is not None
                        and _datetime_le(
                            session.expires_at,
                            now,
                        )
                    )
                ]

                if not expired:
                    return 0

                if delete_rows:
                    ids = [
                        session.id
                        for session
                        in expired
                        if getattr(
                            session,
                            "id",
                            None,
                        )
                        is not None
                    ]

                    if ids:
                        db.execute(
                            delete(
                                AuthSession
                            ).where(
                                AuthSession.id.in_(
                                    ids
                                )
                            )
                        )

                else:
                    for session in expired:
                        if hasattr(
                            session,
                            "revoked",
                        ):
                            session.revoked = True

                db.commit()

                return len(
                    expired
                )

            except Exception:
                db.rollback()

                logger.exception(
                    "Failed to clean expired authentication sessions"
                )

                return 0

    # ========================================================================
    # ACTIVE SESSION LIMIT
    # ========================================================================

    def _limit_active_sessions(
        self,
        db: Any,
        user_id: Any,
        *,
        keep_session: AuthSession,
    ) -> None:
        """
        Prevent unbounded session accumulation.

        The newest/current session is never revoked here.
        """

        sessions = list(
            db.scalars(
                select(
                    AuthSession
                ).where(
                    AuthSession.user_id
                    == user_id
                )
            ).all()
        )

        active = [
            session
            for session
            in sessions
            if (
                not bool(
                    getattr(
                        session,
                        "revoked",
                        False,
                    )
                )
                and getattr(
                    session,
                    "id",
                    None,
                )
                != getattr(
                    keep_session,
                    "id",
                    None,
                )
            )
        ]

        if len(
            active
        ) < _MAX_ACTIVE_SESSIONS:
            return

        def session_sort_key(
            session: AuthSession,
        ) -> tuple[
            datetime,
            int,
        ]:
            created_at = _aware_utc(
                getattr(
                    session,
                    "created_at",
                    None,
                )
            )

            if created_at is None:
                created_at = (
                    datetime.min.replace(
                        tzinfo=timezone.utc
                    )
                )

            session_id = getattr(
                session,
                "id",
                0,
            )

            try:
                numeric_id = int(
                    session_id
                    or 0
                )
            except (
                TypeError,
                ValueError,
            ):
                numeric_id = 0

            return (
                created_at,
                numeric_id,
            )

        active.sort(
            key=session_sort_key
        )

        excess = (
            len(
                active
            )
            - _MAX_ACTIVE_SESSIONS
            + 1
        )

        for session in active[
            :excess
        ]:
            session.revoked = True


auth_service = AuthService()


__all__ = [
    "AuthError",
    "InvalidCredentialsError",
    "AccountDisabledError",
    "DuplicateAccountError",
    "DuplicateUsernameError",
    "InvalidSessionError",
    "ExpiredSessionError",
    "AuthResult",
    "SessionResult",
    "AuthService",
    "auth_service",
]