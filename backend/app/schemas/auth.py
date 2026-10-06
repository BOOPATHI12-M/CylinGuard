"""Auth request/response models.

Email is validated by hand rather than with pydantic's `EmailStr`, because that
needs the `email-validator` package which is not in requirements.txt. The check
below is deliberately conservative: it rejects what is clearly not an address
without pretending to implement RFC 5322.
"""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security.passwords import MAX_PASSWORD_BYTES

# users.email is VARCHAR(190); keep the schema and the column in agreement.
EMAIL_MAX = 190
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=EMAIL_MAX)
    # 8 is a floor, not a policy. The 72-byte ceiling is bcrypt's: passwords.py
    # rejects anything longer rather than letting bcrypt truncate it silently.
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("not a valid email address")
        return value

    @field_validator("password")
    @classmethod
    def _check_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded"
            )
        return value


class LoginRequest(BaseModel):
    email: str = Field(max_length=EMAIL_MAX)
    password: str

    @field_validator("email")
    @classmethod
    def _normalise(cls, value: str) -> str:
        return value.strip().lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserResponse
