import streamlit as st

from app.db.session import SessionLocal
from app.services.auth_service import (
    authenticate_user,
    create_user,
)


def render_auth_brand() -> None:
    """Render authentication branding."""

    st.markdown(
        "# 🧠 MemoryNest"
    )

    st.caption(
        "Your personal memory and knowledge system"
    )


def login_page() -> None:
    """Render login page."""

    render_auth_brand()

    st.divider()

    st.subheader(
        "Welcome back 👋"
    )

    st.caption(
        "Sign in to continue to your personal workspace."
    )

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
    )

    if not login_clicked:
        return

    if not username_or_email.strip():

        st.error(
            "Please enter your username or email."
        )

        return

    if not password:

        st.error(
            "Please enter your password."
        )

        return

    db = SessionLocal()

    try:

        user = authenticate_user(
            db=db,
            username_or_email=username_or_email,
            password=password,
        )

        if user:

            st.session_state["user_id"] = user.id

            st.session_state["username"] = (
                user.username
            )

            st.success(
                f"Welcome back, {user.username}! 👋"
            )

            st.rerun()

        else:

            st.error(
                "Invalid username/email or password."
            )

    finally:

        db.close()


def register_page() -> None:
    """Render registration page."""

    render_auth_brand()

    st.divider()

    st.subheader(
        "Create your MemoryNest ✨"
    )

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
    )

    if not create_clicked:
        return

    username = username.strip()
    email = email.strip()

    if not username or not email or not password:

        st.error(
            "Please fill in all fields."
        )

        return

    if len(username) < 3:

        st.error(
            "Username must contain at least 3 characters."
        )

        return

    if "@" not in email:

        st.error(
            "Please enter a valid email address."
        )

        return

    if len(password) < 8:

        st.error(
            "Password must contain at least 8 characters."
        )

        return

    if password != confirm_password:

        st.error(
            "Passwords do not match."
        )

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


def authentication_page() -> None:
    """Render complete authentication interface."""

    left, center, right = st.columns(
        [1, 2, 1]
    )

    with center:

        login_tab, register_tab = st.tabs(
            [
                "🔐 Sign In",
                "✨ Create Account",
            ]
        )

        with login_tab:

            login_page()

        with register_tab:

            register_page()