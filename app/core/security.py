from passlib.context import CryptContext


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """Convert a plain-text password into a secure hash."""
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """Check whether a password matches its stored hash."""
    return pwd_context.verify(
        plain_password,
        password_hash,
    )