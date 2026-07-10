import os
import re

import requests
import psycopg2
import psycopg2.extras

import pandas as pd
import streamlit as st
import altair as alt

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

BASE_URL = "https://api.sensorpush.com/api/v1"

# ---------------------------------------------------------------------------
# Lab limits
# ---------------------------------------------------------------------------
TEMP_MIN, TEMP_MAX = 18.0, 28.0
HUMIDITY_MIN, HUMIDITY_MAX = 20.0, 60.0

TEMP_SCALE = (15.0, 30.0)
HUMIDITY_SCALE = (10.0, 70.0)
PRESSURE_SCALE = (960.0, 1000.0)

st.set_page_config(page_title="SensorPush Style Dashboard", layout="wide")

# CSS styling to imitate SensorPush Cloud page
st.markdown(
    """
    <style>
    .stApp { background-color: #ffffff; color: #060b3f; }

    /* Increased left and right padding to give more spacing on the edges */
    .block-container {
        padding-top: 0rem; padding-left: 2.5rem;
        padding-right: 2.5rem; padding-bottom: 0rem; max-width: 100%;
    }

    .top-bar {
        display: flex; justify-content: space-between; align-items: center;
        border-bottom: 1px solid #bfc2cc; padding: 4px 4px 8px 4px; margin-bottom: 0px;
    }
    .logo-text { font-size: 24px; font-weight: 700; font-style: italic; color: #060b3f; white-space: nowrap; }
    .logo-icon {
        display: inline-block; width: 26px; height: 26px;
        background-color: #52b83f; border-radius: 50%; margin-right: 12px;
    }

    .header-divider {
        border-bottom: 1px solid #bfc2cc;
        margin-top: 2px;
        margin-bottom: 0px;
    }

    .utility-row {
        display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
    }
    .legend { display: flex; gap: 24px; align-items: center; font-size: 12px; color: #252b5a; margin-top: 0px; min-height:34px; }
    .legend-item { display: flex; align-items: center; gap: 8px; }
    .legend-box-green { width: 24px; height: 24px; background-color: #52b83f; border-radius: 5px; }
    .legend-box-red { width: 24px; height: 24px; background-color: #ff4438; border-radius: 5px; }
    .legend-box-gray { width: 24px; height: 24px; background-color: #c6c8cf; border-radius: 5px; }

    .section-title {
        font-size: 22px; font-weight: 700; color: #060b3f;
        margin-top: 0px; margin-bottom: 8px;
    }
    
    /* Make Streamlit text input look exactly like the filter box */
    div[data-testid="stTextInput"] { width: 250px; margin-bottom: 8px; }
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important;
        border: 1px solid #e2e2e5 !important; border-radius: 5px !important; color: #060b3f !important;
        padding: 9px 16px !important; font-size: 15px !important;
    }
    div[data-testid="stTextInput"] input::placeholder { color: #9a9aa0 !important; }

    .gateway-card {
        border: 1px solid #e2e2e5; border-radius: 8px; padding: 14px 18px;
        width: 500px; margin-bottom: 4px; display: flex; align-items: center; gap: 15px;
    }
    .gateway-icon { width: 30px; height: 30px; background-color: #52b83f; border-radius: 7px; }
    .gateway-name { font-size: 16px; font-weight: 700; color: #060b3f; }
    .gateway-time { font-size: 11px; color: #20285c; }

    .sensor-card {
        border: 1px solid #e2e2e5; border-radius: 8px; padding: 14px 18px;
        min-height: 300px; background-color: #ffffff;
    }
    .sensor-card-header {
        display: flex; justify-content: space-between; align-items: flex-start;
        border-bottom: 1px solid #e2e2e5; padding-bottom: 12px; margin-bottom: 4px;
    }
    .sensor-left-header { display: flex; gap: 14px; align-items: flex-start; }
    .sensor-square { width: 44px; height: 44px; border-radius: 9px; background-color: #52b83f; }
    .sensor-square-red { width: 44px; height: 44px; border-radius: 9px; background-color: #ff4438; }
    .sensor-name { font-size: 19px; font-weight: 700; color: #060b3f; }
    .sensor-time { font-size: 12px; color: #20285c; margin-top: -5px; }
    .battery-row { display: flex; align-items: center; gap: 6px; justify-content: flex-end; color: #20285c; font-size: 13px; }
    .signal-bars { display: inline-flex; align-items: flex-end; gap: 2px; height: 14px; }
    .signal-bars span { width: 3px; background-color: #060b3f; border-radius: 1px; }
    .signal-bars span:nth-child(1) { height: 5px; }
    .signal-bars span:nth-child(2) { height: 8px; }
    .signal-bars span:nth-child(3) { height: 11px; }
    .signal-bars span:nth-child(4) { height: 14px; }
    .sensor-type { color: #20285c; font-size: 12px; text-align: right; margin-top: 4px; }
    .battery-row > span:first-of-type { display: inline-block; transform: translateY(2px); }

    .metric-row { display: grid; grid-template-columns: 1fr 1.15fr; align-items: center; margin: 12px 0; gap: 18px; }
    .metric-label { font-size: 11px; color: #20285c; font-weight: 600; letter-spacing: 0.4px; }
    .metric-value { font-size: 40px; color: #30355e; font-weight: 300; line-height: 0.95; }

    .bar-track { height: 40px; background-color: #e7e8ee; position: relative; overflow: hidden; }
    .bar-line { position: absolute; top: 19px; left: 0; right: 0; height: 2px; background-color: #060b3f; }
    .bar-dot { position: absolute; top: 14px; width: 12px; height: 12px; background-color: #060b3f; border-radius: 50%; }
    .bar-dot-red { position: absolute; top: 14px; width: 12px; height: 12px; background-color: #ff4438; border-radius: 50%; }
    .hatched {
        background: repeating-linear-gradient(-45deg, #e7e8ee, #e7e8ee 4px, #cdd0da 4px, #cdd0da 6px);
    }

    /* Navigation tabs - scoped only to the STATUS / GRAPH radio */
    .st-key-main_nav {
        height: 34px !important;
        min-height: 34px !important;
        display: flex !important;
        align-items: center !important;
        margin: 0 !important;
    }
    .st-key-main_nav div[role="radiogroup"] { 
        gap: 10px !important;
        padding: 0px 4px !important;
        margin: 0px !important;
        align-items: center !important;
        justify-content: flex-start !important;
        min-height: 34px !important;
        height: 34px !important;
        display: flex !important;
    }
    .st-key-main_nav div[role="radiogroup"] label > div:first-child { display: none !important; }
    .st-key-main_nav div[role="radiogroup"] label {
        cursor: pointer;
        opacity: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 34px !important;
        margin: 0 !important;
    }
    .st-key-main_nav div[role="radiogroup"] label p {
        font-weight: 700 !important;
        font-size: 11px !important;
        letter-spacing: 0.5px;
        color: #060b3f !important;
        margin: 0 !important;
        padding: 0px 16px !important;
        border-radius: 14px !important;
        height: 24px !important;
        min-width: 72px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        line-height: 24px !important;
    }
    .st-key-main_nav div[role="radiogroup"] label:has(input:checked) p {
        background-color: #e5e5e8 !important;
    }

    div.stDownloadButton { margin-top: 0px !important; margin-bottom: 0px !important; display:flex !important; align-items:center !important; min-height:34px !important; }
    /* Fine-tune ↓ EXPORT DATA horizontal position.
       Increase this value to move it right; decrease it to move it left. */
    .st-key-export_status {
        padding-left: 0px !important;
        margin-left: 0px !important;
        transform: translateX(16px) !important;
    }
    /* Hide the tiny autorefresh component so it does not create blank space. */
    iframe[title*="streamlit_autorefresh"],
    iframe[src*="streamlit_autorefresh"] {
        display: none !important;
        height: 0px !important;
        min-height: 0px !important;
    }
    div[data-testid="stIFrame"]:has(iframe[title*="streamlit_autorefresh"]) {
        display: none !important;
        height: 0px !important;
        min-height: 0px !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .st-key-export_status div.stDownloadButton {
        padding-left: 0px !important;
        margin-left: 0px !important;
    }
    .st-key-export_status button,
    .st-key-export_status div.stDownloadButton > button {
        margin-left: 0px !important;
    }
    div.stDownloadButton > button { background: transparent !important; border: none !important; box-shadow: none !important; color: #060b3f !important; font-weight: 800 !important; letter-spacing: 1px !important; font-size: 11px !important; padding: 0 !important; min-height: 0 !important; }
    div.stDownloadButton > button:hover { color: #52b83f !important; background: transparent !important; }
    div.stDownloadButton > button p { font-weight: 800 !important; letter-spacing: 1px !important; font-size: 11px !important; margin:0 !important; }

    /* Compress generic vertical spacing */
    div[data-testid="stVerticalBlock"] { gap: 0.1rem; }
    div[data-testid="stElementContainer"] { margin: 0 !important; }
    div[data-testid="stMarkdownContainer"] { margin: 0 !important; }
    div[data-testid="stMainBlockContainer"] { padding-top: 0.5rem !important; }

    /* Settings gear - compact */
    .st-key-btn_settings button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #060b3f !important;
        padding: 0 !important;
        margin: 0 !important;
        min-height: 0 !important;
        height: 30px !important;
        width: 30px !important;
        line-height: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .st-key-btn_settings button p {
        font-size: 25px !important;
        line-height: 1 !important;
        margin: 0 !important;
        padding: 0 !important;
        color: #060b3f !important;
    }
    .st-key-btn_settings button:hover { color: #52b83f !important; background: transparent !important; }
    .st-key-btn_settings button:hover p { color: #52b83f !important; }

    /* Light / dark switch - one real Streamlit button.
       The selected half, sun, and moon are drawn separately so nothing wraps or overlaps. */
    .st-key-theme_toggle_btn {
        display: flex !important;
        justify-content: flex-end !important;
        align-items: center !important;
        height: 26px !important;
        min-height: 26px !important;
        margin-right: 28px !important;
    }
    .st-key-theme_toggle_btn button {
        position: relative !important;
        box-sizing: border-box !important;
        width: 112px !important;
        height: 28px !important;
        min-height: 28px !important;
        padding: 0 !important;
        margin: 0 !important;
        border: 1.5px solid #060b3f !important;
        border-radius: 999px !important;
        box-shadow: none !important;
        background: #ffffff !important;
        overflow: hidden !important;
    }
    /* selected side of the pill */
    .st-key-theme_toggle_btn button::before {
        content: "";
        position: absolute;
        z-index: 1;
        top: 1.9px;
        left: 8px;
        width: 48px;
        height: 22px;
        border-radius: 999px;
        background: #060b3f;
        transition: left 0.15s ease;
        pointer-events: none;
    }
    /* hide real button text, but keep this <p> as a positioning layer */
    .st-key-theme_toggle_btn button p {
        position: absolute !important;
        inset: 0 !important;
        display: block !important;
        width: 100% !important;
        height: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        font-size: 0 !important;
        line-height: 0 !important;
        color: transparent !important;
        visibility: visible !important;
        pointer-events: none !important;
        z-index: 2 !important;
    }
    .st-key-theme_toggle_btn button p::before {
        content: "☀";
        position: absolute;
        left: 27px;
        top: 50%;
        transform: translate(-50%, -50%);
        font-size: 17px;
        line-height: 1;
        color: #ffffff;
        z-index: 3;
    }
    .st-key-theme_toggle_btn button p::after {
        content: "☾";
        position: absolute;
        left: 75px;
        top: 50%;
        transform: translate(-50%, -50%);
        font-size: 18px;
        line-height: 1;
        color: #060b3f;
        z-index: 3;
    }
    .st-key-theme_toggle_btn button:hover {
        border-color: #060b3f !important;
        background: #ffffff !important;
    }
    .st-key-theme_toggle_btn button:focus,
    .st-key-theme_toggle_btn button:active {
        outline: none !important;
        box-shadow: none !important;
        border-color: #060b3f !important;
    }

    /* Settings page */
    .settings-title { font-size: 25px; font-weight: 500; color: #060b3f; margin: 12px 0 34px 0; }
    .settings-sub { font-size: 20px; font-weight: 500; color: #060b3f; margin: 0 0 24px 0; }
    .settings-row-label { font-size: 15px; font-weight: 700; color: #060b3f; padding: 0; line-height: 1; }
    .settings-divider { border-top: 1px solid #e2e2e5; height: 0; margin: 0; padding: 0; }

    .st-key-settings_temp_row,
    .st-key-settings_pressure_row {
        height: 54px !important;
        min-height: 54px !important;
        display: flex !important;
        align-items: center !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .st-key-settings_temp_row > div,
    .st-key-settings_pressure_row > div {
        width: 100% !important;
        height: 54px !important;
        display: flex !important;
        align-items: center !important;
    }
    .st-key-settings_temp_row div[data-testid="stHorizontalBlock"],
    .st-key-settings_pressure_row div[data-testid="stHorizontalBlock"] {
        align-items: center !important;
        height: 54px !important;
    }
    .st-key-temp_unit_radio,
    .st-key-pressure_unit_radio {
        display: flex !important;
        align-items: center !important;
        justify-content: flex-end !important;
        height: 54px !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    .settings-x-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 26px; }
    .st-key-close_settings_x button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #060b3f !important;
        min-height: 0 !important;
        height: 34px !important;
        width: 34px !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    .st-key-close_settings_x button p {
        color: #060b3f !important;
        font-size: 34px !important;
        line-height: 1 !important;
        margin: 0 !important;
        font-weight: 300 !important;
    }
    .st-key-close_settings_x button:hover { background: transparent !important; }
    .st-key-close_settings_x button:hover p { color: #52b83f !important; }

    /* Pill unit selectors in settings */
    /* Hide the actual Streamlit radio widget labels; keep only the °F/°C and mb/in choices */
    .st-key-temp_unit_radio [data-testid="stWidgetLabel"],
    .st-key-pressure_unit_radio [data-testid="stWidgetLabel"] {
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    .st-key-temp_unit_radio div[role="radiogroup"],
    .st-key-pressure_unit_radio div[role="radiogroup"] {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 0 !important;
        width: 122px !important;
        height: 34px !important;
        min-height: 34px !important;
        padding: 1px !important;
        margin: 0 !important;
        border: 1.5px solid #060b3f !important;
        border-radius: 999px !important;
        overflow: hidden !important;
        background: #ffffff !important;
    }
    .st-key-temp_unit_radio label,
    .st-key-pressure_unit_radio label {
        flex: 1 1 50% !important;
        height: 30px !important;
        min-height: 30px !important;
        margin: 0 !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border-radius: 999px !important;
        cursor: pointer !important;
        opacity: 1 !important;
    }
    .st-key-temp_unit_radio label > div:first-child,
    .st-key-pressure_unit_radio label > div:first-child { display: none !important; }
    .st-key-temp_unit_radio label p,
    .st-key-pressure_unit_radio label p {
        color: #060b3f !important;
        font-size: 15px !important;
        line-height: 30px !important;
        font-weight: 700 !important;
        margin: 0 !important;
        padding: 0 !important;
        width: 100% !important;
        text-align: center !important;
    }
    .st-key-temp_unit_radio label:has(input:checked),
    .st-key-pressure_unit_radio label:has(input:checked) {
        background: #060b3f !important;
    }
    .st-key-temp_unit_radio label:has(input:checked) p,
    .st-key-pressure_unit_radio label:has(input:checked) p {
        color: #ffffff !important;
    }



    /* Graph page SensorPush-style layout */
    .graph-page-wrap { margin-top: 0px; }
    .graph-filter input { width: 100% !important; }
    .graph-sensor-mini {
        border-bottom: 1px solid #e2e2e5;
        padding: 12px 0 12px 0;
        color: #060b3f;
    }
    .graph-sensor-head {
        display: grid;
        grid-template-columns: 34px 1fr;
        column-gap: 10px;
        align-items: center;
        margin-bottom: 8px;
    }
    .graph-sensor-square { width: 30px; height: 30px; background:#52b83f; border-radius: 7px; }
    .graph-sensor-name { font-size: 16px; font-weight: 700; color:#060b3f; }
    .graph-sensor-time { font-size: 10px; color:#20285c; margin-top: 2px; }
    .graph-mini-row {
        display: grid;
        grid-template-columns: 1fr 1.35fr;
        column-gap: 10px;
        align-items: center;
        margin: 8px 0;
    }
    .graph-mini-label { font-size: 10px; font-weight: 700; letter-spacing: 0.4px; color:#20285c; }
    .graph-mini-value { font-size: 24px; font-weight: 300; line-height: 1; color:#30355e; text-align:left; }
    .graph-mini-bar { height: 24px; background:#e7e8ee; position:relative; overflow:hidden; }
    .graph-mini-line { position:absolute; left:0; right:0; top:11px; height:2px; background:#060b3f; }
    .graph-mini-dot { position:absolute; top:7px; width:9px; height:9px; border-radius:50%; background:#060b3f; }
    .graph-legend { display:flex; gap:34px; align-items:center; margin:10px 0 8px 0; margin-left:46px; font-size:12px; font-weight:700; color:#060b3f; }
    .graph-legend-item { display:flex; gap:9px; align-items:center; text-transform:uppercase; }
    .graph-legend-dot { width:12px; height:12px; border-radius:50%; display:inline-block; }
    .graph-section-title { font-size: 12px; font-weight:800; letter-spacing:0.4px; color:#060b3f; margin: 10px 0 4px 0; }
    .graph-date-row { display:flex; justify-content:flex-end; align-items:center; gap:14px; color:#777b88; font-size:13px; margin-top:2px; }
    .graph-range-pill { font-weight:800; color:#060b3f; margin-left:6px; }
    .graph-scroll-note { font-size:10px; color:#9a9aa0; margin-top:4px; }



    /* Refined SensorPush-style graph page */
    .st-key-graph_sensor_filter {
        margin-top: 36px !important;
        margin-bottom: 8px !important;
    }
    .st-key-graph_sensor_filter input {
        height: 38px !important;
        font-size: 14px !important;
        border-radius: 4px !important;
    }
    .graph-sensor-mini {
        padding: 12px 0 14px 0 !important;
        border-bottom: 1px solid #edf0f4 !important;
        position: relative !important;
    }
    .graph-sensor-head {
        grid-template-columns: 34px 1fr !important;
        margin-bottom: 8px !important;
    }
    .graph-sensor-square {
        width: 32px !important;
        height: 32px !important;
        border-radius: 7px !important;
    }
    .graph-sensor-name {
        font-size: 16px !important;
        line-height: 1.1 !important;
    }
    .graph-sensor-time {
        font-size: 10px !important;
        margin-top: 3px !important;
    }
    .graph-mini-row {
        grid-template-columns: 1fr 1.15fr !important;
        column-gap: 12px !important;
        margin: 7px 0 !important;
    }
    .graph-mini-label {
        font-size: 9px !important;
        line-height: 1.25 !important;
        text-align: left !important;
    }
    .graph-mini-value {
        font-size: 24px !important;
        line-height: 0.95 !important;
        text-align: left !important;
    }
    .graph-mini-bar {
        height: 22px !important;
    }
    .graph-mini-line { top: 10px !important; }
    .graph-mini-dot { top: 6px !important; }


    /* Push the graph-page sensor search bar down from the divider. */
    .st-key-graph_sensor_filter {
        margin-top: 0px !important;
        margin-bottom: 14px !important;
    }
    .st-key-graph_sensor_filter div[data-testid="stTextInput"] {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }

    /* Custom SensorPush-style graph sensor toggle buttons.
       OFF = light gray track + white knob on the left.
       ON  = light gray track + green knob on the right.
       These are now placed in the top-right header area of each mini card, not pulled with a large transform. */
    div[class*="st-key-graph_toggle_btn_"] {
        display:flex !important;
        justify-content:flex-end !important;
        align-items:center !important;
        height:32px !important;
        min-height:32px !important;
        margin:0 !important;
        padding:0 !important;
        overflow:visible !important;
        position: relative !important;
        left: 0px !important;
        width: 100% !important;
    }
    div[class*="st-key-graph_toggle_btn_"] button {
        position:relative !important;
        width:46px !important;
        height:24px !important;
        min-height:24px !important;
        padding:0 !important;
        margin:0 !important;
        border:0 !important;
        border-radius:999px !important;
        background:#e8e8e8 !important;
        box-shadow:none !important;
        overflow:hidden !important;
    }
    div[class*="st-key-graph_toggle_btn_"] button p { display:none !important; }
    div[class*="st-key-graph_toggle_btn_"] button::after {
        content:"";
        position:absolute;
        top:2px;
        left:2px;
        width:20px;
        height:20px;
        border-radius:50%;
        background:#ffffff;
        box-shadow:0 1px 2px rgba(0,0,0,0.12);
    }
    div[class*="st-key-graph_toggle_btn_"] button:hover {
        background:#e8e8e8 !important;
        border:0 !important;
        box-shadow:none !important;
    }

    /* Streamlit wrappers used to build the mini graph sensor cards */
    div[class*="st-key-graph_card_wrap_"] {
        border-bottom: 1px solid #edf0f4 !important;
        padding: 12px 0 14px 0 !important;
        margin: 0 !important;
    }
    div[class*="st-key-graph_card_wrap_"] div[data-testid="stHorizontalBlock"] {
        align-items: center !important;
        gap: 0.5rem !important;
    }

    .graph-top-controls {
        display:flex;
        justify-content:flex-end;
        align-items:center;
        gap:10px;
        min-height:28px;
        color:#8e9097;
        font-size:13px;
        margin:0 0 2px 0;
        white-space:nowrap;
    }
    .graph-control-strip {
        display:flex;
        justify-content:flex-end;
        align-items:center;
        gap:13px;
        min-height:30px;
        color:#8e9097;
        font-size:13px;
        white-space:nowrap;
    }
    .graph-control-strip .calendar-icon {
        color:#060b3f;
        font-size:18px;
        font-weight:700;
        margin-left:10px;
    }
    .graph-range-control-row {
        display:flex !important;
        justify-content:flex-end !important;
        align-items:center !important;
        gap:4px !important;
        min-height:28px !important;
    }
    .graph-top-controls .calendar-icon,
    .graph-top-controls .refresh-icon {
        color:#060b3f;
        font-size:18px;
        font-weight:700;
    }

    /* H / D / W / M / Y range buttons as plain SensorPush-style text */
    div[class*="st-key-graph_range_btn_"] {
        display:flex !important;
        align-items:center !important;
        justify-content:center !important;
        min-height:24px !important;
        width:14px !important;
        max-width:14px !important;
        flex:0 0 14px !important;
    }
    div[class*="st-key-graph_range_btn_"] button {
        background:transparent !important;
        border:0 !important;
        box-shadow:none !important;
        padding:0 !important;
        margin:0 !important;
        min-height:0 !important;
        height:18px !important;
        width:14px !important;
        min-width:14px !important;
        color:#060b3f !important;
    }
    div[class*="st-key-graph_range_btn_"] button p {
        font-size:12px !important;
        font-weight:800 !important;
        line-height:1 !important;
        margin:0 !important;
        padding:0 !important;
        color:inherit !important;
    }
    div[class*="st-key-graph_range_btn_"] button:hover {
        background:transparent !important;
        color:#52b83f !important;
    }

    .graph-legend {
        margin: 4px 0 12px 22px !important;
        gap: 42px !important;
        font-size: 12px !important;
    }
    .graph-section-title {
        margin: 7px 0 3px 0 !important;
        font-size: 12px !important;
    }
    .vega-actions { display:none !important; }

    .graph-date-range-footer {
        display:flex;
        justify-content:space-between;
        font-size:11px;
        font-weight:800;
        color:#060b3f;
        margin-top:4px;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True
)

if "theme" not in st.session_state:
    st.session_state["theme"] = "light"
if "temp_unit" not in st.session_state:
    st.session_state["temp_unit"] = "\u00b0C"
if "pressure_unit" not in st.session_state:
    st.session_state["pressure_unit"] = "mb"
if "show_settings" not in st.session_state:
    st.session_state["show_settings"] = False
if "graph_range" not in st.session_state:
    st.session_state["graph_range"] = "D"

if st.session_state["theme"] == "dark":
    st.markdown(
        """
        <style>
        .stApp { background-color: #050609 !important; color: #f4f6ff !important; }
        .stApp p, .stApp label, .stApp span, .stMarkdown, .stMarkdown p { color: #f4f6ff !important; }
        .logo-text, .section-title, .sensor-name, .gateway-name { color: #f4f6ff !important; }
        .sensor-card, .gateway-card { background-color: #0b0d14 !important; border: 1.4px solid #3a425c !important; }
        .sensor-card-header { border-color: #3a425c !important; }
        .metric-value { color: #f4f6ff !important; }
        .metric-label, .sensor-time, .gateway-time, .sensor-type, .battery-row { color: #f4f6ff !important; }
        div[data-testid="stTextInput"] input { background-color: #0b0d14 !important; border: 1.4px solid #3a425c !important; color: #f4f6ff !important; }
        div[data-testid="stTextInput"] input::placeholder { color: #b9bed6 !important; }
        div[data-testid="stTextInput"] input:focus {
            border-color: #58637f !important;
            box-shadow: 0 0 0 1px #58637f !important;
        }
        .bar-track { background-color: #191c2a !important; }
        .bar-line { background-color: #f4f6ff !important; }
        .bar-dot { background-color: #f4f6ff !important; }
        .signal-bars span { background-color: #f4f6ff !important; }
        .top-bar { border-color: #252a3a !important; }
        .legend, .legend-item { color: #f4f6ff !important; }
        .st-key-main_nav div[role="radiogroup"] label p { color: #f4f6ff !important; }
        .st-key-main_nav div[role="radiogroup"] label:has(input:checked) p { background-color: #30375e !important; }
        div.stDownloadButton > button, div.stDownloadButton > button p { color: #f4f6ff !important; }
        div.stDownloadButton > button:hover { color: #6fd65a !important; }
        .st-key-btn_settings button { color: #f4f6ff !important; }
        .st-key-btn_settings button p { color: #f4f6ff !important; }
        .st-key-btn_settings button:hover { color: #6fd65a !important; }
        .st-key-btn_settings button:hover p { color: #6fd65a !important; }
        .st-key-theme_toggle_btn button { border-color: #f4f6ff !important; color: #f4f6ff !important; }
        .st-key-theme_toggle_btn button:hover { border-color: #f4f6ff !important; color: #f4f6ff !important; }
        .header-divider { border-color: #252a3a !important; }
        .settings-title, .settings-sub, .settings-row-label { color: #f4f6ff !important; }
        .settings-card-html { background: #0b0d14 !important; border-color: #252a3a !important; }
        .st-key-close_settings_x button p { color: #e8eaf3 !important; }
        .st-key-close_settings_x button:hover p { color: #6fd65a !important; }
        .st-key-temp_unit_radio div[role="radiogroup"],
        .st-key-pressure_unit_radio div[role="radiogroup"] {
            background: #0c1230 !important;
            border-color: #e8eaf3 !important;
        }
        .st-key-temp_unit_radio label p,
        .st-key-pressure_unit_radio label p { color: #e8eaf3 !important; }
        .st-key-temp_unit_radio label:has(input:checked),
        .st-key-pressure_unit_radio label:has(input:checked) { background: #e8eaf3 !important; }
        .st-key-temp_unit_radio label:has(input:checked) p,
        .st-key-pressure_unit_radio label:has(input:checked) p { color: #060b3f !important; }
        .stApp p, .stApp label, .stApp span { color: #f4f6ff !important; }
        </style>
        """, unsafe_allow_html=True
    )

# Active half of the light/dark pill. Icons are drawn with CSS pseudo-elements to avoid wrapping.
if st.session_state.get("theme", "light") == "light":
    st.markdown(
        """
        <style>
        .st-key-theme_toggle_btn button::before { left: 3px !important; background: #060b3f !important; }
        .st-key-theme_toggle_btn button p::before { color: #ffffff !important; }
        .st-key-theme_toggle_btn button p::after { color: #060b3f !important; }
        </style>
        """, unsafe_allow_html=True
    )
else:
    st.markdown(
        """
        <style>
        .st-key-theme_toggle_btn button { background: #050609 !important; border-color: #f4f6ff !important; }
        .st-key-theme_toggle_btn button::before { left: 49px !important; background: #e8eaf3 !important; }
        .st-key-theme_toggle_btn button p::before { color: #f4f6ff !important; opacity: 1 !important; text-shadow: 0 0 3px rgba(244,246,255,0.65) !important; }
        .st-key-theme_toggle_btn button p::after { color: #060b3f !important; }
        .st-key-theme_toggle_btn button:hover { background: #050609 !important; border-color: #f4f6ff !important; }
        </style>
        """, unsafe_allow_html=True
    )

def get_config_value(name, default=None):
    """Read config from Streamlit Secrets first, then environment variables."""
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except Exception:
        return os.environ.get(name, default)


LOCAL_TIMEZONE = get_config_value("LOCAL_TIMEZONE", "America/Toronto")
SENSORPUSH_EMAIL = get_config_value("SENSORPUSH_EMAIL")
SENSORPUSH_PASSWORD = get_config_value("SENSORPUSH_PASSWORD")
DATABASE_URL = get_config_value("DATABASE_URL")
SENSORPUSH_POLL_LIMIT = int(get_config_value("SENSORPUSH_POLL_LIMIT", "200"))


def fahrenheit_to_celsius(temp_f):
    return (temp_f - 32) * 5 / 9


def normalize_database_url(url):
    if not url:
        raise RuntimeError(
            "Missing DATABASE_URL. Add the Supabase Postgres connection string "
            "in Streamlit Cloud Secrets."
        )
    url = str(url).strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if "sslmode=" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode=require"
    return url


def db_connect():
    return psycopg2.connect(normalize_database_url(DATABASE_URL))


@st.cache_resource(show_spinner=False)
def setup_cloud_database():
    """Create the Supabase/Postgres readings table and indexes if needed."""
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id BIGSERIAL PRIMARY KEY,
                observed_at TIMESTAMPTZ NOT NULL,
                sensor_id TEXT NOT NULL,
                sensor_name TEXT NOT NULL,
                temperature_c DOUBLE PRECISION,
                humidity DOUBLE PRECISION,
                barometric_pressure_inhg DOUBLE PRECISION,
                voltage DOUBLE PRECISION,
                source TEXT DEFAULT 'sensorpush_api',
                stored_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (sensor_id, observed_at)
            )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_observed_at ON readings (observed_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_sensor_observed ON readings (sensor_id, observed_at)")
        conn.commit()
    return True


def get_access_token():
    if not SENSORPUSH_EMAIL or not SENSORPUSH_PASSWORD:
        raise RuntimeError(
            "Missing SensorPush credentials. Add SENSORPUSH_EMAIL and "
            "SENSORPUSH_PASSWORD in Streamlit Cloud Secrets."
        )

    authorize_response = requests.post(
        f"{BASE_URL}/oauth/authorize",
        headers={"accept": "application/json", "Content-Type": "application/json"},
        json={"email": SENSORPUSH_EMAIL, "password": SENSORPUSH_PASSWORD},
        timeout=30,
    )
    authorize_response.raise_for_status()
    authorization = authorize_response.json()["authorization"]

    access_response = requests.post(
        f"{BASE_URL}/oauth/accesstoken",
        headers={"accept": "application/json", "Content-Type": "application/json"},
        json={"authorization": authorization},
        timeout=30,
    )
    access_response.raise_for_status()
    return access_response.json()["accesstoken"]


def get_sensors(access_token):
    response = requests.post(
        f"{BASE_URL}/devices/sensors",
        headers={
            "accept": "application/json",
            "Authorization": access_token,
            "Content-Type": "application/json",
        },
        json={},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_samples(access_token, limit):
    response = requests.post(
        f"{BASE_URL}/samples",
        headers={
            "accept": "application/json",
            "Authorization": access_token,
            "Content-Type": "application/json",
        },
        json={"limit": int(limit)},
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def samples_to_rows(sensors, samples):
    rows = []
    for sensor_id, readings in samples.get("sensors", {}).items():
        sensor_name = sensors.get(sensor_id, {}).get("name", sensor_id)
        for reading in readings or []:
            observed_time = reading.get("observed")
            temperature_f = reading.get("temperature")
            humidity = reading.get("humidity")
            pressure = reading.get("barometric_pressure")
            voltage = reading.get("voltage")

            if observed_time is None or temperature_f is None or humidity is None:
                continue

            rows.append((
                observed_time,
                sensor_id,
                sensor_name,
                fahrenheit_to_celsius(float(temperature_f)),
                float(humidity) if humidity is not None else None,
                float(pressure) if pressure is not None else None,
                float(voltage) if voltage is not None else None,
                "sensorpush_api_cloud",
            ))
    return rows


def insert_rows(rows):
    if not rows:
        return 0
    setup_cloud_database()
    with db_connect() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO readings (
                    observed_at, sensor_id, sensor_name,
                    temperature_c, humidity, barometric_pressure_inhg,
                    voltage, source
                ) VALUES %s
                ON CONFLICT (sensor_id, observed_at) DO UPDATE SET
                    sensor_name = EXCLUDED.sensor_name,
                    temperature_c = EXCLUDED.temperature_c,
                    humidity = EXCLUDED.humidity,
                    barometric_pressure_inhg = EXCLUDED.barometric_pressure_inhg,
                    voltage = EXCLUDED.voltage,
                    source = EXCLUDED.source
                """,
                rows,
                page_size=1000,
            )
            inserted_or_updated = cur.rowcount
        conn.commit()
    return inserted_or_updated


@st.cache_data(ttl=55, show_spinner=False)
def sync_latest_to_database():
    """Fetch only recent SensorPush samples, then store new rows in Supabase.

    This is the key difference from the direct cloud version: the app does NOT ask
    SensorPush for all historical data every refresh. Historical graph data comes
    from Supabase.
    """
    setup_cloud_database()
    access_token = get_access_token()
    sensors = get_sensors(access_token)
    samples = get_samples(access_token, SENSORPUSH_POLL_LIMIT)
    rows = samples_to_rows(sensors, samples)
    changed = insert_rows(rows)
    return {"returned": len(rows), "inserted_or_updated": changed}


def timedelta_for_range(range_label):
    if range_label == "H":
        return pd.Timedelta(hours=1)
    if range_label == "D":
        return pd.Timedelta(days=1)
    if range_label == "W":
        return pd.Timedelta(days=7)
    if range_label == "M":
        return pd.Timedelta(days=30)
    if range_label == "Y":
        return pd.Timedelta(days=365)
    return pd.Timedelta(days=1)


def prepare_dataframe(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return df
    df["timestamp"] = df["timestamp"].dt.tz_convert(LOCAL_TIMEZONE)
    df["timestamp_display"] = df["timestamp"].dt.strftime("%m/%d %I:%M %p")
    df["pressure_mb"] = df["barometric_pressure_inhg"] * 33.8639
    return df.sort_values("timestamp").reset_index(drop=True)


@st.cache_data(ttl=55, show_spinner=False)
def load_data(range_label="D"):
    """Load only the selected range from Supabase plus the latest row per sensor.

    The background GitHub Actions collector now writes new readings into Supabase,
    so the dashboard only reads the database. This keeps page loads fast and
    avoids asking SensorPush directly every time someone opens or refreshes the app.
    """
    setup_cloud_database()

    with db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT MAX(observed_at) AS max_time FROM readings")
            max_row = cur.fetchone()
            max_time = max_row["max_time"] if max_row else None

            if max_time is None:
                return pd.DataFrame()

            start_time = max_time - timedelta_for_range(range_label)
            cur.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (sensor_id)
                        observed_at AS timestamp,
                        sensor_id,
                        sensor_name,
                        temperature_c,
                        humidity,
                        barometric_pressure_inhg,
                        voltage,
                        source
                    FROM readings
                    ORDER BY sensor_id, observed_at DESC
                ),
                range_rows AS (
                    SELECT
                        observed_at AS timestamp,
                        sensor_id,
                        sensor_name,
                        temperature_c,
                        humidity,
                        barometric_pressure_inhg,
                        voltage,
                        source
                    FROM readings
                    WHERE observed_at >= %s AND observed_at <= %s
                )
                SELECT DISTINCT * FROM (
                    SELECT * FROM range_rows
                    UNION ALL
                    SELECT * FROM latest
                ) AS combined
                ORDER BY timestamp
                """,
                (start_time, max_time),
            )
            rows = cur.fetchall()

    return prepare_dataframe(rows)

def is_normal(temp, humidity):
    return (TEMP_MIN <= temp <= TEMP_MAX) and (HUMIDITY_MIN <= humidity <= HUMIDITY_MAX)

def scale_position(value, low, high):
    if pd.isna(value):
        return 50
    position = (value - low) / (high - low) * 100
    return max(5, min(95, position))

def render_sensor_card(row):
    sensor_name = row["sensor_name"]
    temp = row["temperature_c"]
    humidity = row["humidity"]
    pressure_mb = row["pressure_mb"]
    timestamp = row["timestamp_display"]

    voltage = f"{row['voltage']:.2f}" if "voltage" in row and pd.notna(row.get("voltage")) else "3.14"

    temp_unit = st.session_state.get("temp_unit", "\u00b0C")
    pressure_unit = st.session_state.get("pressure_unit", "mb")

    if temp_unit == "\u00b0F":
        temp_display = temp * 9 / 5 + 32
        temp_str = f"{temp_display:.1f}&deg;F"
    else:
        temp_str = f"{temp:.1f}&deg;C"

    if pressure_unit == "in":
        pressure_display = pressure_mb / 33.8639
        pressure_str = f"{pressure_display:.2f}in"
    else:
        pressure_str = f"{pressure_mb:.1f}mb"

    normal = is_normal(temp, humidity)

    temp_pos = scale_position(temp, *TEMP_SCALE)
    humidity_pos = scale_position(humidity, *HUMIDITY_SCALE)
    pressure_pos = scale_position(pressure_mb, *PRESSURE_SCALE)

    square_class = "sensor-square" if normal else "sensor-square-red"

    temp_ok = TEMP_MIN <= temp <= TEMP_MAX
    hum_ok = HUMIDITY_MIN <= humidity <= HUMIDITY_MAX
    
    temp_dot = "bar-dot" if temp_ok else "bar-dot-red"
    hum_dot = "bar-dot" if hum_ok else "bar-dot-red"
    temp_track = "bar-track" if temp_ok else "bar-track hatched"

    return f"""
<div class="sensor-card">
    <div class="sensor-card-header">
        <div class="sensor-left-header">
            <div class="{square_class}"></div>
            <div>
                <div class="sensor-name">{sensor_name}</div>
                <div class="sensor-time">LAST READING: {timestamp}</div>
            </div>
        </div>
        <div>
            <div class="battery-row">
                <svg width="24" height="12" viewBox="0 0 24 12" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-right:2px; vertical-align:middle;">
                    <rect x="1.5" y="1.5" width="18" height="9" rx="1.5" />
                    <path d="M22.5 4V8" stroke-linecap="round" />
                </svg>
                <span>{voltage}V</span>
                <span class="signal-bars" style="margin-left:4px;"><span></span><span></span><span></span><span></span></span>
            </div>
            <div class="sensor-type">HTP.xw</div>
        </div>
    </div>

    <div class="metric-row">
        <div>
            <div class="metric-label">TEMPERATURE</div>
            <div class="metric-value">{temp_str}</div>
        </div>
        <div class="{temp_track}">
            <div class="bar-line"></div>
            <div class="{temp_dot}" style="left: {temp_pos}%;"></div>
        </div>
    </div>

    <div class="metric-row">
        <div>
            <div class="metric-label">RELATIVE HUMIDITY</div>
            <div class="metric-value">{humidity:.1f}%</div>
        </div>
        <div class="bar-track">
            <div class="bar-line"></div>
            <div class="{hum_dot}" style="left: {humidity_pos}%;"></div>
        </div>
    </div>

    <div class="metric-row">
        <div>
            <div class="metric-label">BAROMETRIC PRESSURE</div>
            <div class="metric-value">{pressure_str}</div>
        </div>
        <div class="bar-track">
            <div class="bar-line"></div>
            <div class="bar-dot" style="left: {pressure_pos}%;"></div>
        </div>
    </div>
</div>
"""


def safe_key(text):
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(text)).strip("_")


def render_graph_sensor_card(row):
    sensor_name = row["sensor_name"]
    temp = row["temperature_c"]
    humidity = row["humidity"]
    pressure_mb = row["pressure_mb"]
    timestamp = row["timestamp_display"]

    temp_unit = st.session_state.get("temp_unit", "°C")
    pressure_unit = st.session_state.get("pressure_unit", "mb")

    if temp_unit == "°F":
        temp_value = temp * 9 / 5 + 32
        temp_str = f"{temp_value:.1f}&deg;F"
    else:
        temp_str = f"{temp:.1f}&deg;C"

    if pressure_unit == "in":
        pressure_value = pressure_mb / 33.8639
        pressure_str = f"{pressure_value:.2f}in"
    else:
        pressure_str = f"{pressure_mb:.1f}mb"

    temp_pos = scale_position(temp, *TEMP_SCALE)
    humidity_pos = scale_position(humidity, *HUMIDITY_SCALE)
    pressure_pos = scale_position(pressure_mb, *PRESSURE_SCALE)

    return f"""
<div class="graph-sensor-mini">
    <div class="graph-sensor-head">
        <div class="graph-sensor-square"></div>
        <div>
            <div class="graph-sensor-name">{sensor_name}</div>
            <div class="graph-sensor-time">LAST READING: {timestamp}</div>
        </div>
    </div>
    <div class="graph-mini-row">
        <div><div class="graph-mini-label">TEMPERATURE</div><div class="graph-mini-value">{temp_str}</div></div>
        <div class="graph-mini-bar"><div class="graph-mini-line"></div><div class="graph-mini-dot" style="left:{temp_pos}%;"></div></div>
    </div>
    <div class="graph-mini-row">
        <div><div class="graph-mini-label">RELATIVE HUMIDITY</div><div class="graph-mini-value">{humidity:.1f}%</div></div>
        <div class="graph-mini-bar"><div class="graph-mini-line"></div><div class="graph-mini-dot" style="left:{humidity_pos}%;"></div></div>
    </div>
    <div class="graph-mini-row">
        <div><div class="graph-mini-label">BAROMETRIC PRESSURE</div><div class="graph-mini-value">{pressure_str}</div></div>
        <div class="graph-mini-bar"><div class="graph-mini-line"></div><div class="graph-mini-dot" style="left:{pressure_pos}%;"></div></div>
    </div>
</div>
"""

def render_graph_sensor_metrics(row):
    sensor_name = row["sensor_name"]
    temp = row["temperature_c"]
    humidity = row["humidity"]
    pressure_mb = row["pressure_mb"]
    timestamp = row["timestamp_display"]

    temp_unit = st.session_state.get("temp_unit", "°C")
    pressure_unit = st.session_state.get("pressure_unit", "mb")

    if temp_unit == "°F":
        temp_value = temp * 9 / 5 + 32
        temp_str = f"{temp_value:.1f}&deg;F"
    else:
        temp_str = f"{temp:.1f}&deg;C"

    if pressure_unit == "in":
        pressure_value = pressure_mb / 33.8639
        pressure_str = f"{pressure_value:.2f}in"
    else:
        pressure_str = f"{pressure_mb:.1f}mb"

    temp_pos = scale_position(temp, *TEMP_SCALE)
    humidity_pos = scale_position(humidity, *HUMIDITY_SCALE)
    pressure_pos = scale_position(pressure_mb, *PRESSURE_SCALE)

    return f"""
    <div class="graph-mini-row">
        <div><div class="graph-mini-label">TEMPERATURE</div><div class="graph-mini-value">{temp_str}</div></div>
        <div class="graph-mini-bar"><div class="graph-mini-line"></div><div class="graph-mini-dot" style="left:{temp_pos}%;"></div></div>
    </div>
    <div class="graph-mini-row">
        <div><div class="graph-mini-label">RELATIVE HUMIDITY</div><div class="graph-mini-value">{humidity:.1f}%</div></div>
        <div class="graph-mini-bar"><div class="graph-mini-line"></div><div class="graph-mini-dot" style="left:{humidity_pos}%;"></div></div>
    </div>
    <div class="graph-mini-row">
        <div><div class="graph-mini-label">BAROMETRIC PRESSURE</div><div class="graph-mini-value">{pressure_str}</div></div>
        <div class="graph-mini-bar"><div class="graph-mini-line"></div><div class="graph-mini-dot" style="left:{pressure_pos}%;"></div></div>
    </div>
    """

def render_graph_sensor_header(row):
    sensor_name = row["sensor_name"]
    timestamp = row["timestamp_display"]
    return f"""
    <div class="graph-sensor-head" style="margin-bottom:8px;">
        <div class="graph-sensor-square"></div>
        <div>
            <div class="graph-sensor-name">{sensor_name}</div>
            <div class="graph-sensor-time">LAST READING: {timestamp}</div>
        </div>
    </div>
    """

def graph_window_bounds(max_timestamp, range_label, min_timestamp=None):
    """Return fixed SensorPush-style graph window start/end for H/D/W/M/Y.

    The x-axis window stays fixed for each selected range, even if the app has
    less fetched data than the full range. This means:
      H = exactly last 1 hour to now
      D = exactly last 1 day to now
      W = exactly last 7 days to now
      M = exactly last 30 days to now
      Y = exactly last 365 days to now

    If there is not enough data to fill the window, the available data appears
    only in the correct position near the right side of the chart instead of
    stretching to fill the whole graph.
    """
    end = max_timestamp

    if range_label == "H":
        start = end - pd.Timedelta(hours=1)
    elif range_label == "D":
        start = end - pd.Timedelta(days=1)
    elif range_label == "W":
        start = end - pd.Timedelta(days=7)
    elif range_label == "M":
        start = end - pd.Timedelta(days=30)
    elif range_label == "Y":
        start = end - pd.Timedelta(days=365)
    else:
        start = end - pd.Timedelta(days=1)

    return start, end

def graph_axis_format(range_label):
    """Match official SensorPush axis labels: times for H/D, dates for W/M, month/year for Y."""
    if range_label in ["H", "D"]:
        return "%I:%M %p", 5
    if range_label == "W":
        return "%m/%d/%Y", 7
    if range_label == "M":
        return "%m/%d", 6
    return "%b %Y", 6

def downsample_for_plot(view, range_label):
    """Reduce only the number of points sent to Altair/Vega.

    Supabase still stores all raw historical readings. This function only thins the
    dataframe used for browser plotting/hover so W/M/Y do not try to render tens of
    thousands of points. H and D stay high-resolution.
    """
    if view.empty:
        return view

    # H/D are small enough to keep detailed. Larger windows are averaged by time.
    freq_by_range = {
        "H": None,
        "D": None,
        "W": "10min",
        "M": "30min",
        "Y": "6h",
    }
    freq = freq_by_range.get(range_label)

    # Safety cap even for H/D, in case the database becomes denser later.
    max_points_per_sensor = {
        "H": 900,
        "D": 1200,
        "W": 1000,
        "M": 1000,
        "Y": 800,
    }.get(range_label, 1000)

    parts = []
    numeric_cols = [c for c in view.columns if c not in {
        "timestamp", "timestamp_display", "sensor_id", "sensor_name", "source",
        "_hover_label", "_hover_anchor"
    } and pd.api.types.is_numeric_dtype(view[c])]

    for sensor_name, g in view.sort_values("timestamp").groupby("sensor_name", sort=False):
        g = g.dropna(subset=["timestamp"]).copy()
        if g.empty:
            continue

        if freq is not None:
            resampled = (
                g.set_index("timestamp")[numeric_cols]
                .resample(freq)
                .mean()
                .dropna(how="all")
                .reset_index()
            )
            resampled["sensor_name"] = sensor_name
            if "sensor_id" in g.columns:
                resampled["sensor_id"] = g["sensor_id"].iloc[0]
            if "source" in g.columns:
                resampled["source"] = g["source"].iloc[0]
            g = resampled

        # Hard cap by evenly selecting rows, preserving first/last.
        if len(g) > max_points_per_sensor:
            import numpy as np
            idx = np.linspace(0, len(g) - 1, max_points_per_sensor).round().astype(int)
            idx = sorted(set(idx))
            g = g.iloc[idx].copy()

        parts.append(g)

    if not parts:
        return view.iloc[0:0].copy()

    out = pd.concat(parts, ignore_index=True).sort_values("timestamp")
    out["timestamp_display"] = out["timestamp"].dt.strftime("%m/%d %I:%M %p")
    return out.reset_index(drop=True)


def make_sensorpush_chart(view, metric_col, title, unit_suffix="", height=160, range_label="D", x_start=None, x_end=None, capture_param=None, union_filter=None, show_x_axis=True, y_domain_override=None, label_metric_col=None, display_title=True):
    if view.empty:
        return None

    view = view.copy()

    # Build a SensorPush-style hover label for every visible row.
    # metric_col is what gets plotted. label_metric_col is what gets displayed.
    # For pressure, this lets us draw a smoothed/hidden-precision-style line while
    # still showing the real rounded API reading in labels.
    if label_metric_col is None:
        label_metric_col = metric_col

    time_text = view["timestamp"].dt.strftime("%m/%d %I:%M %p").str.replace(" 0", " ", regex=False).str.lower()
    if unit_suffix == "in":
        value_text = view[label_metric_col].map(lambda v: f"{v:.2f}{unit_suffix}")
    else:
        value_text = view[label_metric_col].map(lambda v: f"{v:.1f}{unit_suffix}")
    view["_hover_label"] = time_text + ", " + value_text

    # Send a much smaller dataframe to Altair for plotting and hover. The full
    # dataframe is still used above/below for scale and mean calculations.
    plot_view = downsample_for_plot(view, range_label)
    if not plot_view.empty:
        plot_time_text = plot_view["timestamp"].dt.strftime("%m/%d %I:%M %p").str.replace(" 0", " ", regex=False).str.lower()
        if unit_suffix == "in":
            plot_value_text = plot_view[label_metric_col].map(lambda v: f"{v:.2f}{unit_suffix}")
        else:
            plot_value_text = plot_view[label_metric_col].map(lambda v: f"{v:.1f}{unit_suffix}")
        plot_view["_hover_label"] = plot_time_text + ", " + plot_value_text
    else:
        plot_view = view

    # Fixed chart height, dynamic y-scale from the currently visible data.
    # The plotted data should use almost the full gray graph area while still leaving
    # a small amount of headroom and footroom. Do NOT force a large minimum span for
    # pressure here; otherwise small real changes look too flat and fail to fill the chart.
    if y_domain_override is not None:
        y_domain = y_domain_override
    else:
        y_min = float(view[metric_col].min())
        y_max = float(view[metric_col].max())
        raw_span = y_max - y_min

        if raw_span <= 0:
            # A perfectly flat series has no vertical range to scale. Use a small window
            # around the value so the line stays visible and centered.
            if title == "BAROMETRIC PRESSURE":
                base_window = 0.12 if unit_suffix == "in" else 0.35
            elif title == "RELATIVE HUMIDITY":
                base_window = 0.40
            else:
                base_window = 0.30
            y_mid = (y_min + y_max) / 2
            y_domain = [y_mid - base_window / 2, y_mid + base_window / 2]
        else:
            # 18% padding means the data occupies about 73% of the graph height:
            # enough to clearly fill the chart, but not so tight that it touches edges.
            padding = raw_span * 0.18
            y_domain = [y_min - padding, y_max + padding]

    axis_format, tick_count = graph_axis_format(range_label)

    # IMPORTANT: create a real left-side time gutter inside the same Altair chart.
    # The visible data domain begins at x_start, but the chart's scale begins earlier.
    # The gray rectangle, dotted mean line, and data all start at x_start, leaving a
    # white gutter for the mean label to the left. This avoids hconcat/Streamlit sizing
    # issues where the gutter can be ignored.
    if x_start is not None and x_end is not None:
        x_span = x_end - x_start
        gutter_start = x_start - (x_span * 0.075)
        x_scale = alt.Scale(domain=[gutter_start, x_end])
    else:
        gutter_start = view["timestamp"].min()
        x_scale = alt.Scale()

    if show_x_axis:
        x_axis = alt.Axis(
            format=axis_format,
            tickCount=tick_count,
            labelColor="#505670",
            labelFontSize=11,
            tickColor="#bfc2cc",
            tickSize=5,
            domainColor="#bfc2cc",
            domainWidth=1,
            grid=False,
            title=None,
        )
    else:
        x_axis = alt.Axis(labels=False, ticks=False, domain=False, grid=False, title=None)

    y_axis_hidden = alt.Axis(labels=False, ticks=False, domain=False, grid=False)
    y_scale = alt.Scale(domain=y_domain, zero=False)
    color_scale = alt.Scale(range=["#52b83f", "#4267bd", "#35a6b9", "#ff9f1c", "#8e44ad"])

    plot_bg = alt.Chart(pd.DataFrame({"x": [x_start], "x2": [x_end], "y": [y_domain[0]], "y2": [y_domain[1]]})).mark_rect(
        color="#e7e8ee"
    ).encode(
        x=alt.X("x:T", scale=x_scale, axis=x_axis),
        x2="x2:T",
        y=alt.Y("y:Q", scale=y_scale, axis=y_axis_hidden, title=None),
        y2="y2:Q",
    )

    line = alt.Chart(plot_view).mark_line(strokeWidth=1.8, clip=True).encode(
        x=alt.X("timestamp:T", title=None, scale=x_scale, axis=x_axis),
        y=alt.Y(f"{metric_col}:Q", title=None, scale=y_scale, axis=y_axis_hidden),
        color=alt.Color("sensor_name:N", title=None, scale=color_scale, legend=None),
    )

    mean_value = float(view[label_metric_col].mean())
    mean_line = alt.Chart(pd.DataFrame({"x": [x_start], "x2": [x_end], "y": [mean_value]})).mark_rule(
        strokeDash=[2, 5], strokeWidth=2, color="#aeb4c6"
    ).encode(
        x=alt.X("x:T", scale=x_scale),
        x2="x2:T",
        y=alt.Y("y:Q", scale=y_scale),
    )

    # Left-side reference numbers. The old chart only labeled the dotted mean line,
    # which made it hard to judge the scale. Add top/middle/bottom labels in the
    # white gutter just left of the gray plot area, while keeping the dotted mean
    # line as the middle reference.
    y_span_for_refs = max(float(y_domain[1] - y_domain[0]), 1e-9)
    y_ref_top = float(y_domain[1] - y_span_for_refs * 0.08)
    y_ref_mid = float(mean_value)
    y_ref_bottom = float(y_domain[0] + y_span_for_refs * 0.08)

    if unit_suffix == "in":
        ref_label_fn = lambda v: f"{v:.2f}{unit_suffix}"
    else:
        ref_label_fn = lambda v: f"{v:.1f}{unit_suffix}"

    ref_labels_df = pd.DataFrame({
        "x": [x_start, x_start, x_start],
        "y": [y_ref_top, y_ref_mid, y_ref_bottom],
        "label": [ref_label_fn(y_ref_top), ref_label_fn(y_ref_mid), ref_label_fn(y_ref_bottom)],
    })
    ref_labels = alt.Chart(ref_labels_df).mark_text(
        align="right", baseline="middle", dx=-10, fontSize=11, color="#30355e", clip=False
    ).encode(
        x=alt.X("x:T", scale=x_scale),
        y=alt.Y("y:Q", scale=y_scale),
        text="label:N",
    )

    # Smooth hover: SensorPush Cloud moves the marker continuously along the drawn
    # line instead of jumping only at recorded sample timestamps. Vega-Lite selections
    # normally snap to real data rows, so create a dense, interpolated hover-only table.
    # The visible line still uses the real recorded samples; the hover dots/labels use
    # linear interpolation between those samples so the popup follows the line smoothly.
    # Lightweight smooth hover. The previous version used very dense hover anchors
    # such as 5 seconds for H and 30 seconds for D, which made Vega/Altair laggy
    # because every chart had to render many invisible selector points and labels.
    # These intervals keep the hover visually smooth, but reduce the number of
    # generated hover rows enough for Streamlit to stay responsive.
    hover_freq = hover_freq_for_range(range_label)

    if x_start is not None and x_end is not None:
        hover_index = pd.date_range(start=x_start, end=x_end, freq=hover_freq)
        if len(hover_index) == 0:
            hover_index = pd.DatetimeIndex(sorted(view["timestamp"].dropna().unique()))
    else:
        hover_index = pd.DatetimeIndex(sorted(plot_view["timestamp"].dropna().unique()))

    anchor_times = pd.DataFrame({"_hover_anchor": hover_index})

    hover_parts = []
    numeric_cols = [metric_col]
    if label_metric_col != metric_col:
        numeric_cols.append(label_metric_col)

    for sensor_name, sensor_rows in plot_view.sort_values("timestamp").groupby("sensor_name", sort=False):
        sensor_numeric = (
            sensor_rows.set_index("timestamp")[numeric_cols]
            .groupby(level=0).mean()
            .sort_index()
        )

        # Reindex to both actual reading times and dense hover times, then interpolate
        # based on time. Reindex back to hover times only so every sensor has a value at
        # the same smoothly moving anchor positions. Edge NaNs are dropped below so the
        # hover does not invent data before the first reading or after the last reading.
        combined_index = sensor_numeric.index.union(hover_index).sort_values()
        interpolated = (
            sensor_numeric.reindex(combined_index)
            .interpolate(method="time")
            .reindex(hover_index)
        )
        interpolated["sensor_name"] = sensor_name
        interpolated["_hover_anchor"] = interpolated.index
        hover_parts.append(interpolated.reset_index(drop=True))

    hover_view = pd.concat(hover_parts, ignore_index=True) if hover_parts else plot_view.copy()
    hover_view = hover_view.dropna(subset=[metric_col, "sensor_name", "_hover_anchor"])

    anchor_time_text = hover_view["_hover_anchor"].dt.strftime("%m/%d %I:%M %p").str.replace(" 0", " ", regex=False).str.lower()
    if unit_suffix == "in":
        anchor_value_text = hover_view[label_metric_col].map(lambda v: f"{v:.2f}{unit_suffix}")
    else:
        anchor_value_text = hover_view[label_metric_col].map(lambda v: f"{v:.1f}{unit_suffix}")
    hover_view["_hover_label"] = anchor_time_text + ", " + anchor_value_text

    if capture_param is None:
        capture_param = alt.selection_point(
            name="sp_hover_0", nearest=True, on="pointerover",
            fields=["_hover_anchor"], empty=False, clear="pointerout",
        )
    if union_filter is None:
        union_filter = (
            f'(length(data("{capture_param.name}_store")) > 0) && '
            f'(toNumber(datum._hover_anchor) == toNumber(data("{capture_param.name}_store")[0].values[0]))'
        )

    selectors = alt.Chart(anchor_times).mark_point(opacity=0, size=180).encode(
        x=alt.X("_hover_anchor:T", scale=x_scale),
        tooltip=alt.value(None),
    ).add_params(capture_param)

    points = alt.Chart(hover_view).mark_point(filled=True, size=85, clip=True).encode(
        x=alt.X("_hover_anchor:T", scale=x_scale),
        y=alt.Y(f"{metric_col}:Q", title=None, scale=y_scale, axis=y_axis_hidden),
        color=alt.Color("sensor_name:N", title=None, scale=color_scale, legend=None),
        opacity=alt.condition(union_filter, alt.value(1), alt.value(0)),
        tooltip=alt.value(None),
    )

    rule = alt.Chart(anchor_times).mark_rule(color="#060b3f", strokeDash=[2, 3], strokeWidth=1, opacity=0.9, clip=True).encode(
        x=alt.X("_hover_anchor:T", scale=x_scale),
        tooltip=alt.value(None),
    ).transform_filter(union_filter)

    x_start_ms = pd.Timestamp(x_start).value // 10**6 if x_start is not None else int(view["timestamp"].min().value // 10**6)
    x_end_ms = pd.Timestamp(x_end).value // 10**6 if x_end is not None else int(view["timestamp"].max().value // 10**6)
    span_ms = max(x_end_ms - x_start_ms, 1)
    flip_expr = f"(toNumber(datum._hover_anchor) - {x_start_ms}) / {span_ms} > 0.55"

    yq = alt.Y(f"{metric_col}:Q", scale=y_scale)
    xt = alt.X("_hover_anchor:T", scale=x_scale)
    col = alt.Color("sensor_name:N", title=None, scale=color_scale, legend=None)
    hover_base = alt.Chart(hover_view).transform_filter(union_filter).transform_calculate(_flip=flip_expr)

    PILL_W = 158
    PILL_H = 20
    bg_right = hover_base.transform_filter("datum._flip == false").mark_rect(
        width=PILL_W, height=PILL_H, cornerRadius=3, opacity=0.92, xOffset=(10 + PILL_W / 2), clip=True,
    ).encode(x=xt, y=yq, color=col, tooltip=alt.value(None))
    text_right = hover_base.transform_filter("datum._flip == false").mark_text(
        align="left", baseline="middle", dx=16, fontSize=11, color="#ffffff", clip=True,
    ).encode(x=xt, y=yq, text="_hover_label:N", tooltip=alt.value(None))

    bg_left = hover_base.transform_filter("datum._flip == true").mark_rect(
        width=PILL_W, height=PILL_H, cornerRadius=3, opacity=0.92, xOffset=-(10 + PILL_W / 2), clip=True,
    ).encode(x=xt, y=yq, color=col, tooltip=alt.value(None))
    text_left = hover_base.transform_filter("datum._flip == true").mark_text(
        align="right", baseline="middle", dx=-16, fontSize=11, color="#ffffff", clip=True,
    ).encode(x=xt, y=yq, text="_hover_label:N", tooltip=alt.value(None))

    layered = alt.layer(
        plot_bg, mean_line, line, ref_labels, selectors, rule, points,
        bg_right, text_right, bg_left, text_left
    ).properties(
        height=height,
        width="container",
    )

    if display_title:
        chart_title = alt.TitleParams(
            text=title,
            anchor="start",
            align="left",
            dx=22,
            fontSize=12,
            fontWeight="bold",
            color="#060b3f",
            offset=6,
        )
        layered = layered.properties(title=chart_title)

    return layered


def hover_freq_for_range(range_label):
    # Coarser hover anchors greatly reduce browser-side Vega work.
    if range_label == "H":
        return "30s"
    if range_label == "D":
        return "5min"
    if range_label == "W":
        return "30min"
    if range_label == "M":
        return "3h"
    return "1D"


def make_title_hover_band(title, range_label="D", x_start=None, x_end=None, capture_param=None, band_height=28):
    """Draw a section-title row that also captures hover across the entire gap.

    The earlier versions used invisible points. That only catches the mouse near
    those points, so the white rows between charts can feel dead. This version
    builds transparent rectangular cells that cover the whole title/gap band from
    left to right, including the title text area.
    """
    if x_start is not None and x_end is not None:
        x_span = x_end - x_start
        gutter_start = x_start - (x_span * 0.075)
        x_scale = alt.Scale(domain=[gutter_start, x_end])
        hover_index = pd.date_range(start=x_start, end=x_end, freq=hover_freq_for_range(range_label))
        if len(hover_index) == 0:
            hover_index = pd.DatetimeIndex([x_start, x_end])
        # Make sure the row has endpoints so rectangular hit areas cover everything.
        hover_index = hover_index.union(pd.DatetimeIndex([x_start, x_end])).sort_values()
    else:
        now = pd.Timestamp.now()
        x_start = now
        x_end = now + pd.Timedelta(minutes=1)
        gutter_start = now
        x_scale = alt.Scale()
        hover_index = pd.DatetimeIndex([x_start, x_end])

    if capture_param is None:
        capture_param = alt.selection_point(
            name="sp_hover_title", nearest=True, on="pointerover",
            fields=["_hover_anchor"], empty=False, clear="pointerout",
        )

    # Build full-height transparent hover rectangles. Each rectangle maps to one
    # hover anchor time; moving horizontally across the title/gap row updates the
    # same shared hover selection used by the charts.
    anchors = list(pd.DatetimeIndex(hover_index))
    rows = []
    for i, anchor in enumerate(anchors):
        if i == 0:
            x0 = gutter_start
        else:
            x0 = anchors[i - 1] + (anchor - anchors[i - 1]) / 2
        if i == len(anchors) - 1:
            x1 = x_end
        else:
            x1 = anchor + (anchors[i + 1] - anchor) / 2
        # Keep all intervals within the visual chart domain.
        if x0 < gutter_start:
            x0 = gutter_start
        if x1 > x_end:
            x1 = x_end
        rows.append({"x0": x0, "x1": x1, "y0": 0, "y1": 1, "_hover_anchor": anchor})

    hit_df = pd.DataFrame(rows)

    title_df = pd.DataFrame({
        "x": [gutter_start],
        "y": [0.5],
        "label": [title],
    })

    title_mark = alt.Chart(title_df).mark_text(
        align="left", baseline="middle", dx=22,
        fontSize=12, fontWeight="bold", color="#060b3f"
    ).encode(
        x=alt.X("x:T", scale=x_scale, axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False, title=None)),
        y=alt.Y("y:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False, title=None)),
        text="label:N",
        tooltip=alt.value(None),
    )

    # opacity is tiny but non-zero so Vega receives pointer events reliably.
    hover_rects = alt.Chart(hit_df).mark_rect(color="#ffffff", opacity=0.001).encode(
        x=alt.X("x0:T", scale=x_scale, axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False, title=None)),
        x2="x1:T",
        y=alt.Y("y0:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False, title=None)),
        y2="y1:Q",
        tooltip=alt.value(None),
    ).add_params(capture_param)

    # Put the hit rectangles on top of the text, so even hovering directly over
    # the words triggers the same hover behavior as the blank gap area.
    return alt.layer(title_mark, hover_rects).properties(height=band_height, width="container")

try:
    df = load_data(st.session_state.get("graph_range", "D"))
except Exception as e:
    st.error("Could not load SensorPush data.")
    st.exception(e)
    st.stop()

if df.empty:
    st.warning("No readings returned from SensorPush yet.")
    st.stop()

newest = df.iloc[-1]

# Pushed settings and toggle extremely far right
head_left, head_spacer, head_toggle, head_settings = st.columns([5.5, 7.0, 1.15, 0.35], vertical_alignment="center")

with head_left:
    st.markdown(
        '<div style="display:flex;align-items:center;height:100%;">'
        '<span class="logo-text">NMSL Environment Monitor</span></div>',
        unsafe_allow_html=True,
    )

with head_toggle:
    if st.button("theme", key="theme_toggle_btn", help="Toggle light/dark mode"):
        st.session_state["theme"] = "dark" if st.session_state.get("theme", "light") == "light" else "light"
        st.rerun()

with head_settings:
    if st.button("\u2699", key="btn_settings", help="Settings"):
        st.session_state["show_settings"] = not st.session_state["show_settings"]
        st.rerun()


st.markdown('<div class="header-divider" style="margin-top:8px;margin-bottom:0px;"></div>', unsafe_allow_html=True)

def render_settings_panel():
    # Full settings screen styled like the reference page.
    top_left, top_right = st.columns([12, 1], vertical_alignment="center")
    with top_left:
        st.markdown('<div class="settings-title">Settings</div>', unsafe_allow_html=True)
    with top_right:
        if st.button("×", key="close_settings_x", help="Close settings"):
            st.session_state["show_settings"] = False
            st.rerun()

    left_gap, center, right_gap = st.columns([1.6, 6.8, 1.6])
    with center:
        st.markdown('<div class="settings-sub">Configuration</div>', unsafe_allow_html=True)

        st.markdown('<div class="settings-divider"></div>', unsafe_allow_html=True)

        with st.container(key="settings_temp_row"):
            row1_label, row1_control = st.columns([4, 1.15], vertical_alignment="center")
            with row1_label:
                st.markdown('<div class="settings-row-label">Temperature unit</div>', unsafe_allow_html=True)
            with row1_control:
                new_temp = st.radio(
                    "",
                    ["°F", "°C"],
                    index=["°F", "°C"].index(st.session_state["temp_unit"]),
                    horizontal=True,
                    label_visibility="collapsed",
                    key="temp_unit_radio",
                )
                if new_temp != st.session_state["temp_unit"]:
                    st.session_state["temp_unit"] = new_temp
                    st.rerun()

        st.markdown('<div class="settings-divider"></div>', unsafe_allow_html=True)

        with st.container(key="settings_pressure_row"):
            row2_label, row2_control = st.columns([4, 1.15], vertical_alignment="center")
            with row2_label:
                st.markdown('<div class="settings-row-label">Barometric pressure unit</div>', unsafe_allow_html=True)
            with row2_control:
                new_pres = st.radio(
                    "",
                    ["mb", "in"],
                    index=["mb", "in"].index(st.session_state["pressure_unit"]),
                    horizontal=True,
                    label_visibility="collapsed",
                    key="pressure_unit_radio",
                )
                if new_pres != st.session_state["pressure_unit"]:
                    st.session_state["pressure_unit"] = new_pres
                    st.rerun()

        st.markdown('<div class="settings-divider"></div>', unsafe_allow_html=True)

if st.session_state["show_settings"]:
    render_settings_panel()
    st.stop()

tab = st.radio("nav", ["STATUS", "GRAPH"], horizontal=True, label_visibility="collapsed", key="main_nav")
st.markdown('<div class="header-divider" style="margin-top:0px;margin-bottom:0px;"></div>', unsafe_allow_html=True)

# ===========================================================================
# STATUS VIEW
# ===========================================================================
if tab == "STATUS":
    if st_autorefresh is not None:
        st_autorefresh(interval=60 * 1000, key="sensorpush_data_refresh")
    latest = df.groupby("sensor_name").tail(1).sort_values("sensor_name")

    util_left, util_right = st.columns([1, 2], vertical_alignment="center")
    with util_left:
        full_csv = df.drop(columns=["timestamp_display"]).to_csv(index=False).encode("utf-8")
        st.download_button("\u2193 EXPORT DATA", data=full_csv, file_name="sensorpush_all_readings.csv", mime="text/csv", key="export_status")
    with util_right:
        st.markdown(
            """<div class="legend" style="justify-content:flex-end;">
                <div class="legend-item"><span class="legend-box-green"></span> NORMAL</div>
                <div class="legend-item"><span class="legend-box-red"></span> OVER/UNDER LIMIT</div>
                <div class="legend-item"><span class="legend-box-gray"></span> NOT REPORTING</div>
            </div>""", unsafe_allow_html=True
        )
        
    # Full width horizontal divider below the export / legend row
    st.markdown('<div class="header-divider" style="margin-top: 0px; margin-bottom: 12px;"></div>', unsafe_allow_html=True)

    # Gateways
    st.markdown('<div class="section-title">Gateways</div>', unsafe_allow_html=True)
    gw_filter = st.text_input("Filter gateways", key="gw_filter", placeholder="Filter gateways", label_visibility="collapsed")
    
    if not gw_filter or gw_filter.lower() in "gateway 1":
        st.markdown(
            f"""<div class="gateway-card">
                <div class="gateway-icon"></div>
                <div><div class="gateway-name">Gateway 1</div><div class="gateway-time">LAST SEEN: {newest["timestamp"].strftime("%m/%d %I:%M %p")}</div></div>
            </div>""", unsafe_allow_html=True
        )

    # Sensors
    st.markdown('<div class="section-title">Sensors</div>', unsafe_allow_html=True)
    sensor_filter = st.text_input("Filter sensors", key="sensor_filter", placeholder="Filter sensors", label_visibility="collapsed")
    
    if sensor_filter:
        latest = latest[latest["sensor_name"].str.contains(sensor_filter, case=False, na=False)]

    cols = st.columns(3)
    for index, (_, row) in enumerate(latest.iterrows()):
        with cols[index % 3]:
            st.html(render_sensor_card(row))

# ===========================================================================
# GRAPH VIEW (SensorPush-style historical layout)
# ===========================================================================
else:
    if st_autorefresh is not None:
        st_autorefresh(interval=5 * 60 * 1000, key="sensorpush_graph_refresh")

    latest = df.groupby("sensor_name").tail(1).sort_values("sensor_name")
    sensor_options = sorted(df["sensor_name"].unique().tolist())

    if "graph_range" not in st.session_state:
        st.session_state["graph_range"] = "D"

    for sensor in sensor_options:
        key = f"graph_show_{sensor}"
        if key not in st.session_state:
            st.session_state[key] = True

    left_panel, right_panel = st.columns([1.0, 3.15], gap="small")

    with left_panel:
        st.markdown('<div style="height: 18px;"></div>', unsafe_allow_html=True)
        graph_filter = st.text_input(
            "Filter sensors",
            key="graph_sensor_filter",
            placeholder="Filter sensors",
            label_visibility="collapsed",
        )

        shown_latest = latest.copy()
        if graph_filter:
            shown_latest = shown_latest[shown_latest["sensor_name"].str.contains(graph_filter, case=False, na=False)]

        for _, row in shown_latest.iterrows():
            name = row["sensor_name"]
            safe = safe_key(name)
            is_on = st.session_state.get(f"graph_show_{name}", True)

            with st.container(key=f"graph_card_wrap_{safe}"):
                head_cols = st.columns([0.76, 0.24], vertical_alignment="center")
                with head_cols[0]:
                    st.markdown(render_graph_sensor_header(row), unsafe_allow_html=True)
                with head_cols[1]:
                    btn_key = f"graph_toggle_btn_{safe}"
                    if st.button("", key=btn_key, help=f"Show/hide {name}"):
                        st.session_state[f"graph_show_{name}"] = not is_on
                        st.rerun()
                st.markdown(render_graph_sensor_metrics(row), unsafe_allow_html=True)

            if is_on:
                st.markdown(
                    f"""
                    <style>
                    .st-key-graph_toggle_btn_{safe} button::after {{
                        left:24px !important;
                        background:#52b83f !important;
                    }}
                    </style>
                    """,
                    unsafe_allow_html=True,
                )

    chosen = [sensor for sensor in sensor_options if st.session_state.get(f"graph_show_{sensor}", True)]

    with right_panel:
        # One compact control line: Start date → End date, calendar, then H/D/W/M/Y.
        control_cols = st.columns([2.85, 0.52, 0.14, 0.52, 0.20, 0.13, 0.13, 0.13, 0.13, 0.13], vertical_alignment="center", gap="small")
        with control_cols[1]:
            st.markdown('<div class="graph-top-controls">Start date</div>', unsafe_allow_html=True)
        with control_cols[2]:
            st.markdown('<div class="graph-top-controls">→</div>', unsafe_allow_html=True)
        with control_cols[3]:
            st.markdown('<div class="graph-top-controls">End date</div>', unsafe_allow_html=True)
        with control_cols[4]:
            st.markdown('<div class="graph-top-controls"><span class="calendar-icon">▣</span></div>', unsafe_allow_html=True)

        range_label = st.session_state.get("graph_range", "D")
        for i, range_option in enumerate(["H", "D", "W", "M", "Y"], start=5):
            with control_cols[i]:
                if st.button(range_option, key=f"graph_range_btn_{range_option}"):
                    st.session_state["graph_range"] = range_option
                    st.rerun()

        # Keep the selected range visibly green. The extra selectors handle Streamlit's
        # nested markdown/button markup, which can otherwise override the color.
        range_label = st.session_state.get("graph_range", "D")
        st.markdown(
            f"""
            <style>
            .st-key-graph_range_btn_{range_label} button,
            .st-key-graph_range_btn_{range_label} button *,
            .st-key-graph_range_btn_{range_label} [data-testid="stMarkdownContainer"],
            .st-key-graph_range_btn_{range_label} [data-testid="stMarkdownContainer"] *,
            .st-key-graph_range_btn_{range_label} p {{
                color:#52b83f !important;
                font-weight:900 !important;
                opacity:1 !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

        graph_start, graph_end = graph_window_bounds(df["timestamp"].max(), range_label, df["timestamp"].min())

        view = df[df["sensor_name"].isin(chosen)].copy()
        if not view.empty:
            view = view[(view["timestamp"] >= graph_start) & (view["timestamp"] <= graph_end)]

        if not chosen:
            st.info("Turn on at least one sensor from the left panel to display graph data.")
        elif view.empty:
            st.info("No data in the selected range. Try a wider time range or wait for the collector to log more readings.")
        else:
            legend_html = '<div class="graph-legend">'
            palette = ["#52b83f", "#4267bd", "#35a6b9", "#ff9f1c", "#8e44ad"]
            for i, sensor in enumerate(chosen):
                legend_html += f'<div class="graph-legend-item"><span class="graph-legend-dot" style="background:{palette[i % len(palette)]};"></span>{sensor}</div>'
            legend_html += '</div>'
            st.markdown(legend_html, unsafe_allow_html=True)

            temp_view = view.copy()
            temp_unit = st.session_state.get("temp_unit", "°C")
            if temp_unit == "°F":
                temp_view["temperature_display"] = temp_view["temperature_c"] * 9 / 5 + 32
                temp_suffix = "°F"
            else:
                temp_view["temperature_display"] = temp_view["temperature_c"]
                temp_suffix = "°C"

            pressure_view = view.copy()
            pressure_unit = st.session_state.get("pressure_unit", "mb")
            if pressure_unit == "in":
                pressure_view["pressure_display"] = pressure_view["pressure_mb"] / 33.8639
                pressure_suffix = "in"
            else:
                pressure_view["pressure_display"] = pressure_view["pressure_mb"]
                pressure_suffix = "mb"

            # SensorPush Cloud appears to draw pressure from higher precision than the
            # one-decimal label it displays. The public API often returns pressure rounded
            # to 0.01 inHg, which is about 0.34 mb. Drawing those rounded values directly
            # makes the pressure graph look stepped/spiky. This smoothed plot column keeps
            # the displayed readings unchanged, but draws pressure more like the official
            # graph by reducing quantization artifacts.
            pressure_view = pressure_view.sort_values(["sensor_name", "timestamp"])
            pressure_view["pressure_display_plot"] = (
                pressure_view.groupby("sensor_name", group_keys=False)["pressure_display"]
                .apply(lambda s: s.ewm(span=5, adjust=False, min_periods=1).mean())
            )

            # Each chart captures the pointer with its own param storing the hovered timestamp.
            # The filter matches EVERY sensor row whose timestamp equals the hovered timestamp
            # from ANY chart, so hovering one plot shows all sensors' values on all three.
            hover_params = [
                alt.selection_point(
                    name=f"sp_hover_{i}", nearest=True, on="pointerover",
                    fields=["_hover_anchor"], empty=False, clear="pointerout",
                )
                for i in range(3)
            ]
            union_filter = " || ".join(
                f'((length(data("{p.name}_store")) > 0) && '
                f'(toNumber(datum._hover_anchor) == toNumber(data("{p.name}_store")[0].values[0])))'
                for p in hover_params
            )

            # Fixed chart height, dynamic y-scale from the currently visible sensors.
            # The charts are downsampled internally for plotting, while the database keeps
            # all raw historical rows. Removing the separate invisible title-hover bands
            # also cuts a large amount of browser-side work.
            temp_chart = make_sensorpush_chart(temp_view, "temperature_display", "TEMPERATURE", temp_suffix, height=155, range_label=range_label, x_start=graph_start, x_end=graph_end, capture_param=hover_params[0], union_filter=union_filter, show_x_axis=False, display_title=True)
            humidity_chart = make_sensorpush_chart(view, "humidity", "RELATIVE HUMIDITY", "%", height=155, range_label=range_label, x_start=graph_start, x_end=graph_end, capture_param=hover_params[1], union_filter=union_filter, show_x_axis=False, display_title=True)
            pressure_chart = make_sensorpush_chart(pressure_view, "pressure_display_plot", "BAROMETRIC PRESSURE", pressure_suffix, height=155, range_label=range_label, x_start=graph_start, x_end=graph_end, capture_param=hover_params[2], union_filter=union_filter, show_x_axis=True, label_metric_col="pressure_display", display_title=True)

            combined_chart = alt.vconcat(
                temp_chart,
                humidity_chart,
                pressure_chart,
                spacing=22,
            ).resolve_scale(x="shared", color="shared").properties(
                # The mean-label gutter is handled by the x-scale domain inside
                # make_sensorpush_chart; keep outer padding small to avoid shifting
                # the whole chart column.
                padding={"left": 4, "right": 4, "top": 4, "bottom": 0},
                background="transparent",
                autosize={"type": "fit-x", "contains": "padding"},
            ).configure_view(strokeWidth=0).configure_mark(tooltip=None)

            st.altair_chart(combined_chart, use_container_width=True)
