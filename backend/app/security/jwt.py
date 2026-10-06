"""JWT issue and verify.

Access tokens only - no refresh tokens, which the spec does not ask for and which
would need a revocation story to be worth anything.

The subject is the user id as a string, because the JWT spec requires `sub` to be
a string and some libraries reject an integer.
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or not ours."""


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Return the user id carried by `token`, or raise TokenError.

    Every failure mode collapses to one exception on purpose: the caller turns it
    into a single 401 and never reports *why* a token was rejected, which would
    tell an attacker whether a token was expired, forged or simply malformed.
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise TokenError("could not validate credentials") from exc

    subject = payload.get("sub")
    if subject is None:
        raise TokenError("token has no subject")
    try:
        return int(subject)
    except (TypeError, ValueError) as exc:
        raise TokenError("token subject is not a user id") from exc
