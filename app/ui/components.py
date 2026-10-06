import streamlit as st


def render_brand() -> None:
    """Render MemoryNest sidebar branding."""

    st.markdown("# 🧠 MemoryNest")

    st.caption(
        "Your personal knowledge system"
    )


def render_metric_card(
    icon: str,
    label: str,
    value: str,
    delta: str | None = None,
) -> None:
    """Render a dashboard metric."""

    if delta:

        st.metric(
            label=f"{icon} {label}",
            value=value,
            delta=delta,
        )

    else:

        st.metric(
            label=f"{icon} {label}",
            value=value,
        )


def render_feature_card(
    icon: str,
    title: str,
    description: str,
    button_text: str,
    button_key: str,
) -> bool:
    """
    Render a professional feature card.

    Returns True when the action button is clicked.
    """

    with st.container(border=True):

        st.subheader(
            f"{icon} {title}"
        )

        st.caption(description)

        st.write("")

        clicked = st.button(
            button_text,
            key=button_key,
            use_container_width=True,
        )

    return clicked


def render_empty_state(
    icon: str,
    title: str,
    description: str,
) -> None:
    """Render an empty-state message."""

    with st.container(border=True):

        st.markdown(
            f"### {icon} {title}"
        )

        st.caption(description)


def render_section_header(
    title: str,
    description: str | None = None,
) -> None:
    """Render a dashboard section heading."""

    st.subheader(title)

    if description:
        st.caption(description)


def render_status_card(
    icon: str,
    title: str,
    description: str,
    status: str,
) -> None:
    """Render a system status card."""

    with st.container(border=True):

        st.markdown(
            f"### {icon} {title}"
        )

        st.caption(description)

        if status == "success":

            st.success("Operational")

        elif status == "warning":

            st.warning("Coming Soon")

        elif status == "info":

            st.info("Active")

        else:

            st.error("Unavailable")


def render_footer() -> None:
    """Render application footer."""

    st.divider()
