import streamlit as st


def apply_custom_css() -> None:
    """
    Apply global styling to native Streamlit components.

    Important:
    We only style Streamlit's existing UI elements.
    No visible custom HTML is used.
    """

    st.markdown(
        """
        <style>

        /* =====================================================
           GLOBAL APPLICATION
        ===================================================== */

        .stApp {
            background-color: #f7f8fc;
        }

        .main .block-container {
            max-width: 1450px;
            padding-top: 2rem;
            padding-bottom: 3rem;
            padding-left: 3rem;
            padding-right: 3rem;
        }

        /* =====================================================
           SIDEBAR
        ===================================================== */

        section[data-testid="stSidebar"] {
            background-color: #111827;
            border-right: 1px solid #1f2937;
        }

        section[data-testid="stSidebar"] > div {
            padding-top: 1.5rem;
        }

        section[data-testid="stSidebar"] * {
            color: #e5e7eb;
        }

        section[data-testid="stSidebar"] .stRadio label {
            border-radius: 10px;
            padding: 8px 10px;
            margin-bottom: 3px;
            transition: background-color 0.2s ease;
        }

        section[data-testid="stSidebar"]
        .stRadio label:hover {
            background-color: #1f2937;
        }

        /* =====================================================
           HEADINGS
        ===================================================== */

        h1 {
            color: #111827 !important;
            font-weight: 800 !important;
            letter-spacing: -1px;
        }

        h2,
        h3 {
            color: #111827 !important;
            font-weight: 750 !important;
        }

        /* =====================================================
           CARDS / CONTAINERS
        ===================================================== */

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 16px;
            border: 1px solid #e5e7eb;
            background-color: #ffffff;
            box-shadow:
                0 2px 8px rgba(15, 23, 42, 0.04);
        }

        /* =====================================================
           METRICS
        ===================================================== */

        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 18px;
            min-height: 125px;
            box-shadow:
                0 2px 8px rgba(15, 23, 42, 0.04);
        }

        div[data-testid="stMetricLabel"] {
            color: #64748b !important;
            font-size: 13px !important;
            font-weight: 600 !important;
        }

        div[data-testid="stMetricValue"] {
            color: #111827 !important;
            font-size: 28px !important;
            font-weight: 800 !important;
        }

        /* =====================================================
           BUTTONS
        ===================================================== */

        .stButton > button {
            border-radius: 10px;
            min-height: 42px;
            font-weight: 650;
            border: 1px solid #e2e8f0;
            transition:
                transform 0.15s ease,
                box-shadow 0.15s ease;
        }

        .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow:
                0 5px 15px rgba(15, 23, 42, 0.08);
        }

        /* Primary buttons */

        .stButton > button[kind="primary"] {
            border: none;
        }

        /* =====================================================
           INPUTS
        ===================================================== */

        div[data-baseweb="input"] {
            border-radius: 10px;
        }

        div[data-baseweb="select"] {
            border-radius: 10px;
        }

        /* =====================================================
           TABS
        ===================================================== */

        button[data-baseweb="tab"] {
            font-weight: 650;
        }

        /* =====================================================
           ALERTS
        ===================================================== */

        div[data-testid="stAlert"] {
            border-radius: 12px;
        }

        /* =====================================================
           DIVIDERS
        ===================================================== */

        hr {
            border-color: #e5e7eb;
        }

        /* =====================================================
           FILE UPLOADER
        ===================================================== */

        section[data-testid="stFileUploaderDropzone"] {
            border-radius: 14px;
            border: 1px dashed #cbd5e1;
            background-color: #ffffff;
        }

        /* =====================================================
           DATAFRAME
        ===================================================== */

        div[data-testid="stDataFrame"] {
            border-radius: 12px;
            overflow: hidden;
        }

        /* =====================================================
           CAPTIONS
        ===================================================== */

        .stCaption {
            color: #64748b;
        }

        /* =====================================================
           MOBILE / SMALL SCREEN
        ===================================================== */

        @media (max-width: 900px) {

            .main .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }

        }

        </style>
        """,
        unsafe_allow_html=True,
    )