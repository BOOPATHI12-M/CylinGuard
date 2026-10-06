"""Shared FastAPI dependencies.

`get_owned_cylinder` is the whole point of this module. Spec §34 requires every
cylinder route to prove the cylinder belongs to the caller, and a rule repeated by
hand in ten endpoints is a rule that will be forgotten in the eleventh. Declaring
it as a dependency makes the check structural: a route either depends on it and is
authorised, or it does not take a cylinder at all.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cylinder, User
from app.security.jwt import TokenError, decode_access_token

# auto_error=False so a missing header produces our own 401 with a WWW-Authenticate
# header, rather than FastAPI's bare 403.
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access_token from /api/auth/login")

UNAUTHORISED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise UNAUTHORISED
    try:
        user_id = decode_access_token(credentials.credentials)
    except TokenError:
        # Deliberately indistinguishable from a missing token: never reveal
        # whether a token was expired, forged or simply malformed.
        raise UNAUTHORISED

    user = db.get(User, user_id)
    if user is None:
        # A valid signature for a deleted account is still not a login.
        raise UNAUTHORISED
    return user


def get_owned_cylinder(
    cylinder_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Cylinder:
    """Resolve a cylinder the caller owns, or 404.

    404 rather than 403 on purpose: a 403 would confirm that the cylinder exists
    and belongs to someone else, which tells an attacker how many cylinders the
    system has and lets them probe for valid ids.
    """
    cylinder = db.execute(
        select(Cylinder).where(
            Cylinder.id == cylinder_id, Cylinder.user_id == user.id
        )
    ).scalar_one_or_none()
    if cylinder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cylinder not found"
        )
    return cylinder
