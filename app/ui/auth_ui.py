
import os

import streamlit as st

from app.db.session import SessionLocal
from app.services.auth_service import authenticate_user, create_user
from app.services.session_service import create_user_session


SESSION_COOKIE_NAME = "memorynest_session"


def cookie_secure_enabled() -> bool:
    """Return whether browser cookies must require HTTPS."""
    value = os.getenv("MEMORYNEST_COOKIE_SECURE", "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def render_auth_brand() -> None:
    """Render authentication branding."""
    st.markdown("# 🧠 MemoryNest")
    st.caption("Your personal memory and knowledge system")


def login_page(cookies) -> None:
    """Render login and create a persistent session on success."""
    render_auth_brand()
    st.divider()
    st.subheader("Welcome back 👋")
    st.caption("Sign in to continue to your personal workspace.")
    st.write("")

    username_or_email = st.text_input(
        "Username or Email",
        placeholder="Enter your username or email",
        key="login_identifier",
    )
    password = st.text_input(
        "Password",
        placeholder="Enter your password",
        type="password",
        key="login_password",
    )

    st.write("")
    login_clicked = st.button(
        "🔐  Sign In",
        use_container_width=True,
        type="primary",
        key="login_submit",
    )

    if not login_clicked:
        return

    if not username_or_email.strip():
        st.error("Please enter your username or email.")
        return

    if not password:
        st.error("Please enter your password.")
        return

    db = SessionLocal()

    try:
        user = authenticate_user(
            db=db,
            username_or_email=username_or_email.strip(),
            password=password,
        )

        if user is None:
            st.error("Invalid username/email or password.")
            return

        token, expires_at = create_user_session(db, user.id)

        cookies.set(
            cookie=SESSION_COOKIE_NAME,
            val=token,
            key="memorynest_session_write",
            expires_at=expires_at,
            path="/",
            secure=cookie_secure_enabled(),
            same_site="strict",
        )

        st.session_state["user_id"] = user.id
        st.session_state["username"] = user.username
        st.session_state["session_token"] = token

        st.success(f"Welcome back, {user.username}! 👋")

    except Exception:
        st.error(
            "Something went wrong while signing in. "
            "Please check the application terminal."
        )
    finally:
        db.close()


def register_page() -> None:
    """Render account registration."""
    render_auth_brand()
    st.divider()
    st.subheader("Create your MemoryNest ✨")
    st.caption(
        "Create your personal workspace and start "
        "organizing your knowledge."
    )
    st.write("")

    username = st.text_input(
        "Username",
        placeholder="Choose a username",
        key="register_username",
    )
    email = st.text_input(
        "Email",
        placeholder="you@example.com",
        key="register_email",
    )
    password = st.text_input(
        "Password",
        placeholder="Minimum 8 characters",
        type="password",
        key="register_password",
    )
    confirm_password = st.text_input(
        "Confirm Password",
        placeholder="Re-enter your password",
        type="password",
        key="register_confirm_password",
    )

    st.write("")
    create_clicked = st.button(
        "✨  Create Account",
        use_container_width=True,
        type="primary",
        key="register_submit",
    )

    if not create_clicked:
        return

    username = username.strip()
    email = email.strip()

    if not username or not email or not password:
        st.error("Please fill in all fields.")
        return

    if len(username) < 3:
        st.error("Username must contain at least 3 characters.")
        return

    if "@" not in email:
        st.error("Please enter a valid email address.")
        return

    if len(password) < 8:
        st.error("Password must contain at least 8 characters.")
        return

    if password != confirm_password:
        st.error("Passwords do not match.")
        return

    db = SessionLocal()

    try:
        create_user(
            db=db,
            username=username,
            email=email,
            password=password,
        )
        st.success(
            "Account created successfully! "
            "Switch to Sign In to continue."
        )
    except ValueError as error:
        st.error(str(error))
    finally:
        db.close()


def authentication_page(cookies) -> None:
    """Render the sign-in and registration interface."""
    _, center, _ = st.columns([1, 2, 1])

    with center:
        login_tab, register_tab = st.tabs(
            ["🔐 Sign In", "✨ Create Account"]
        )

        with login_tab:
            login_page(cookies)

        with register_tab:
            register_page()
