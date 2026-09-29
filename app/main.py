import streamlit as st

from app.db.init_db import init_database
from app.db.session import SessionLocal
from app.services.auth_service import (
    authenticate_user,
    create_user,
)


st.set_page_config(
    page_title="MemoryNest",
    page_icon="🧠",
    layout="wide",
)


# Initialize database
init_database()


def login_page() -> None:
    st.title("🧠 MemoryNest")

    st.subheader("Login")

    username_or_email = st.text_input(
        "Username or Email",
    )

    password = st.text_input(
        "Password",
        type="password",
    )

    if st.button("Login", use_container_width=True):

        if not username_or_email or not password:
            st.error("Please enter both fields.")
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
                st.session_state["username"] = user.username

                st.success(
                    f"Welcome back, {user.username}!"
                )

                st.rerun()

            else:
                st.error(
                    "Invalid username/email or password."
                )

        finally:
            db.close()


def register_page() -> None:
    st.title("🧠 MemoryNest")

    st.subheader("Create Account")

    username = st.text_input(
        "Username",
        key="register_username",
    )

    email = st.text_input(
        "Email",
        key="register_email",
    )

    password = st.text_input(
        "Password",
        type="password",
        key="register_password",
    )

    confirm_password = st.text_input(
        "Confirm Password",
        type="password",
        key="register_confirm_password",
    )

    if st.button(
        "Create Account",
        use_container_width=True,
    ):

        if not username or not email or not password:
            st.error("Please fill in all fields.")
            return

        if password != confirm_password:
            st.error("Passwords do not match.")
            return

        if len(password) < 8:
            st.error(
                "Password must contain at least 8 characters."
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
                "Account created successfully. "
                "You can now log in."
            )

        except ValueError as error:
            st.error(str(error))

        finally:
            db.close()


def dashboard_page() -> None:
    username = st.session_state.get(
        "username",
        "User",
    )

    st.title("🧠 MemoryNest")

    st.success(
        f"Welcome to your MemoryNest, {username}!"
    )

    st.subheader("Your Personal Knowledge System")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Documents",
            "0",
        )

    with col2:
        st.metric(
            "Conversations",
            "0",
        )

    with col3:
        st.metric(
            "Memories",
            "0",
        )

    st.info(
        "Document upload and AI-powered search "
        "will be added in the next development phase."
    )

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()


def main() -> None:

    if "user_id" in st.session_state:
        dashboard_page()
        return

    login_tab, register_tab = st.tabs(
        [
            "Login",
            "Register",
        ]
    )

    with login_tab:
        login_page()

    with register_tab:
        register_page()


if __name__ == "__main__":
    main()