
import logging

import streamlit as st

from app.db.session import SessionLocal
from app.services.calendar_service import (
    build_ics_calendar,
    update_event_review,
)
from app.services.document_service import get_user_documents
from app.services.event_service import (
    get_user_events,
    scan_document_for_events,
)


logger = logging.getLogger(__name__)

EVENT_STATUSES = [
    "pending_review",
    "confirmed",
    "rejected",
]


def events_page() -> None:
    """Display, review, and export events from the user's documents."""

    user_id = st.session_state.get("user_id")

    if not user_id:
        st.warning("Please sign in to view your events.")
        return

    st.title("Events & Dates")
    st.caption(
        "Review deadlines, exams, meetings, and other dates detected "
        "in your documents."
    )

    # Display feedback saved before the previous page rerun.
    review_notice = st.session_state.pop(
        "event_review_notice",
        None,
    )

    if review_notice:
        st.success(review_notice)

    db = SessionLocal()

    try:
        documents = get_user_documents(db, user_id)

        eligible_documents = [
            document
            for document in documents
            if document.extraction_status == "completed"
            and document.extracted_text_path
        ]

        # ---------------------------------------------------------
        # Scan documents
        # ---------------------------------------------------------
        st.subheader("Scan Documents")

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
                format_func=lambda document_id: document_options[
                    document_id
                ],
                key="event_document_selection",
            )

            if st.button(
                "Detect Events",
                type="primary",
                disabled=not selected_ids,
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

                    except Exception:
                        logger.exception(
                            "Unexpected event scanning error for "
                            "document ID %s",
                            document_id,
                        )
                        failures.append(
                            f"Document ID {document_id}: "
                            "An unexpected error occurred. "
                            "Check the application logs."
                        )

                for failure in failures:
                    st.warning(failure)

                if not failures:
                    st.success(
                        f"Scan complete. Found {total} event candidate(s)."
                    )
                elif total:
                    st.info(
                        f"Found {total} event candidate(s) in the "
                        "documents scanned successfully."
                    )

                st.rerun()

        # ---------------------------------------------------------
        # Calendar export
        # ---------------------------------------------------------
        st.divider()
        st.subheader("Calendar Export")

        rows = get_user_events(db, user_id)

        confirmed_events = [
            event
            for event, _filename in rows
            if event.status == "confirmed"
            and event.event_date is not None
        ]

        if confirmed_events:
            st.caption(
                f"{len(confirmed_events)} confirmed event(s) with dates "
                "are available for export."
            )

            try:
                calendar_data = build_ics_calendar(confirmed_events)

                st.download_button(
                    label="Download Confirmed Events (.ics)",
                    data=calendar_data,
                    file_name="memorynest-events.ics",
                    mime="text/calendar",
                    key="download_memorynest_calendar",
                )

                with st.expander("How to import your calendar file"):
                    st.markdown(
                        """
                        Your calendar file contains your confirmed MemoryNest
                        events with valid dates. Download it, then follow the
                        instructions below to add these events to your calendar.

                        **Google Calendar**
                        1. Download the `.ics` file above.
                        2. Open Google Calendar in your browser.
                        3. Click the Settings gear and select **Settings**.
                        4. Open **Import & export**.
                        5. Under Import, select the downloaded `.ics` file.
                        6. Choose the destination calendar and click **Import**.

                        **Microsoft Outlook or another calendar app**

                        Look for the app's calendar import option and select
                        the downloaded `.ics` file. The exact steps depend on
                        your calendar application.

                        **Important to know**
                        - Only confirmed events with valid dates are exported.
                        - Importing adds events to your chosen calendar; it
                          does not connect that calendar to MemoryNest.
                        - If an event changes in MemoryNest, download and
                          import an updated file when needed. Avoid importing
                          the same events repeatedly, as this may create
                          duplicates.
                        """
                    )

            except ValueError as exc:
                st.warning(str(exc))

        else:
            st.info(
                "Confirm at least one event with a valid date to enable "
                "calendar export."
            )

        # ---------------------------------------------------------
        # Review detected events
        # ---------------------------------------------------------
        st.divider()
        st.subheader("Detected Events")

        if not rows:
            st.info(
                "No events have been detected yet. Select a document above "
                "and choose Detect Events."
            )
            return

        for event, filename in rows:
            with st.container(border=True):
                st.markdown(f"**{event.title}**")
                st.caption(f"Source document: {filename}")
                st.caption("Evidence from the document:")
                st.write(event.source_excerpt)

                if event.event_date:
                    st.write(
                        "**Current date:** "
                        f"{event.event_date.strftime('%d %B %Y')}"
                    )
                else:
                    st.warning(
                        "This event has no interpreted date. Review the "
                        "source evidence before confirming it."
                    )

                with st.form(key=f"review_event_{event.id}"):
                    edited_title = st.text_input(
                        "Event title",
                        value=event.title,
                        key=f"event_title_{event.id}",
                    )

                    edited_type = st.text_input(
                        "Category",
                        value=event.event_type,
                        key=f"event_type_{event.id}",
                    )

                    edited_start_date = st.text_input(
                        "Start date (YYYY-MM-DD)",
                        value=(
                            event.event_date.isoformat()
                            if event.event_date
                            else ""
                        ),
                        placeholder="2026-10-25",
                        key=f"event_start_{event.id}",
                    )

                    edited_end_date = st.text_input(
                        "End date (YYYY-MM-DD, optional)",
                        value=(
                            event.event_end_date.isoformat()
                            if event.event_end_date
                            else ""
                        ),
                        placeholder="2026-10-27",
                        key=f"event_end_{event.id}",
                    )

                    current_status = (
                        event.status
                        if event.status in EVENT_STATUSES
                        else "pending_review"
                    )

                    edited_status = st.selectbox(
                        "Review status",
                        options=EVENT_STATUSES,
                        index=EVENT_STATUSES.index(current_status),
                        format_func=lambda value: value.replace(
                            "_", " "
                        ).title(),
                        key=f"event_status_{event.id}",
                    )

                    submitted = st.form_submit_button(
                        "Save Event Review",
                        type="primary",
                    )

                if submitted:
                    try:
                        update_event_review(
                            db,
                            user_id,
                            event.id,
                            title=edited_title,
                            event_type=edited_type,
                            event_date_text=edited_start_date,
                            event_end_date_text=edited_end_date,
                            status=edited_status,
                            original_date_text=event.date_text,
                        )

                    except ValueError as exc:
                        st.error(str(exc))

                    except Exception:
                        logger.exception(
                            "Failed to save event review for event ID %s",
                            event.id,
                        )
                        st.error(
                            "The event could not be saved. "
                            "Check the application logs for details."
                        )

                    else:
                        event_title = edited_title.strip()

                        if edited_status == "confirmed":
                            notice = (
                                f"Event '{event_title}' confirmed successfully. "
                                "If it has a valid date, it can appear in "
                                "Calendar notifications and be included in "
                                "calendar synchronization when configured."
                            )
                        elif edited_status == "rejected":
                            notice = (
                                f"Event '{event_title}' rejected successfully."
                            )
                        else:
                            notice = (
                                f"Event '{event_title}' review saved. "
                                "It is still awaiting confirmation."
                            )

                        st.session_state["event_review_notice"] = notice
                        st.rerun()

    finally:
        db.close()
