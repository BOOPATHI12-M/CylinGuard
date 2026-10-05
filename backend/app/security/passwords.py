"""Password hashing.

Uses bcrypt directly rather than passlib: passlib 1.7.4 probes
``bcrypt.__about__``, which modern bcrypt releases removed, producing a noisy
spurious warning on every call.

Plaintext passwords are never stored or logged.
"""

import bcrypt

# bcrypt silently truncates anything past 72 bytes. Reject instead of
# truncating, so two different long passwords can never collide.
MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    pass


def hash_password(plain: str) -> str:
    encoded = plain.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded."
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    encoded = plain.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("utf-8"))
    except ValueError:
        # Malformed or truncated hash in the database - treat as a failed login
        # rather than a 500.
        return False
