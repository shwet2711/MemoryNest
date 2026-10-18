
import streamlit as st

from app.db.session import SessionLocal
from app.services.document_service import get_user_documents
from app.services.event_service import (
    get_user_events,
    scan_document_for_events,
)


def events_page() -> None:
    """Display and scan date-related events in the user's documents."""

    user_id = st.session_state.get("user_id")

    if not user_id:
        st.warning("Please sign in to view your events.")
        return

    st.title("Events & Dates")
    st.caption(
        "Find deadlines, exams, meetings, and other dates in your documents."
    )

    db = SessionLocal()

    try:
        documents = get_user_documents(db, user_id)

        eligible_documents = [
            document
            for document in documents
            if document.extraction_status == "completed"
            and document.extracted_text_path
        ]

        if not eligible_documents:
            st.info(
                "Upload a document and wait for text extraction to complete "
                "before detecting events."
            )
        else:
            document_options = {
                document.id: (
                    f"{document.original_filename} "
                    f"(ID: {document.id})"
                )
                for document in eligible_documents
            }

            selected_ids = st.multiselect(
                "Choose documents to scan",
                options=list(document_options),
                format_func=lambda document_id: document_options[document_id],
                key="event_document_selection",
            )

            if st.button(
                "Detect Events",
                type="primary",
                disabled=not selected_ids,
                use_container_width=False,
            ):
                total = 0
                failures = []

                for document_id in selected_ids:
                    try:
                        detected = scan_document_for_events(
                            db,
                            user_id,
                            document_id,
                        )
                        total += len(detected)
                    except (ValueError, OSError) as exc:
                        failures.append(
                            f"Document ID {document_id}: {exc}"
                        )

                if failures:
                    for failure in failures:
                        st.warning(failure)

                if not failures:
                    st.success(
                        f"Scan complete. Found {total} event candidate(s)."
                    )
                elif total:
                    st.info(f"Found {total} event candidate(s) in scanned documents.")

                st.rerun()

        st.divider()
        st.subheader("Detected Events")

        rows = get_user_events(db, user_id)

        if not rows:
            st.info(
                "No events have been detected yet. Select a document above "
                "and choose Detect Events."
            )
            return

        for event, filename in rows:
            with st.container(border=True):
                st.markdown(f"**{event.title}**")

                if " to " in event.date_text.casefold() and event.event_date:
                    date_label = event.date_text
                elif event.event_date:
                    date_label = event.event_date.strftime("%d %B %Y")
                else:
                    date_label = f"Needs date review: {event.date_text}"

                st.write(f"**Date:** {date_label}")
                st.write(f"**Category:** {event.event_type.title()}")
                st.write(f"**Status:** {event.status.replace('_', ' ').title()}")
                st.caption(f"Source document: {filename}")
                st.caption("Evidence from the document:")
                st.write(event.source_excerpt)

                if not event.event_date:
                    st.warning(
                        "The date could not be interpreted safely. "
                        "It has not been converted into a calendar date."
                    )

    finally:
        db.close()
