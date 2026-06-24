"""
AIOS · Paperwork → Data — LlamaParse invoice demo.
Drop supplier invoices, watch them become a clean spreadsheet. Cited to nothing invented.
"""
import hashlib
import io

import pandas as pd
import streamlit as st

import invoice_extract as ix

st.set_page_config(page_title="AIOS · Paperwork to Data", page_icon="▦",
                   layout="centered", initial_sidebar_state="collapsed")

# Manual data-entry baseline used for the "time saved" counter (minutes per invoice).
MANUAL_MIN_PER_DOC = 4

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap');
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; background: #02040e !important; color: #c8d8f8; }
.stApp { background: #02040e !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; max-width: 880px !important; }
.stApp::before {
    content: ''; position: fixed; inset: 0;
    background-image: linear-gradient(rgba(37,99,235,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(37,99,235,0.035) 1px, transparent 1px);
    background-size: 52px 52px; pointer-events: none; z-index: 0;
}
.hdr { padding: 56px 0 30px; text-align: center; }
.hdr-mono { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 5px; text-transform: uppercase; color: #1d4ed8; margin-bottom: 20px; }
.hdr-title { font-size: 46px; font-weight: 700; color: #f0f6ff; letter-spacing: -2px; line-height: 1.08; margin-bottom: 14px; }
.hdr-title .g { background: linear-gradient(100deg, #3b82f6 0%, #818cf8 60%, #c084fc 100%); -webkit-background-clip: text; background-clip: text; color: transparent; }
.hdr-sub { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #1e3a6e; letter-spacing: 1.5px; }
.hdr-line { width: 1px; height: 34px; background: linear-gradient(to bottom, transparent, #1d4ed8, transparent); margin: 26px auto 30px; }

.stFileUploader label { font-family: 'JetBrains Mono', monospace !important; font-size: 9px !important; letter-spacing: 3px !important; text-transform: uppercase !important; color: #1e3a6e !important; }
.stFileUploader > div { background: #030712 !important; border: 1px dashed #1d4ed8 !important; border-radius: 4px !important; }
.stButton > button, .stDownloadButton > button {
    background: linear-gradient(135deg, #1d4ed8 0%, #4f46e5 100%) !important; border: none !important; border-radius: 3px !important;
    color: #e0eaff !important; font-family: 'JetBrains Mono', monospace !important; font-size: 11px !important; letter-spacing: 4px !important;
    text-transform: uppercase !important; padding: 14px 0 !important; width: 100%; box-shadow: 0 0 32px rgba(29,78,216,0.25);
}
.stButton > button:hover, .stDownloadButton > button:hover { box-shadow: 0 0 48px rgba(29,78,216,0.4) !important; }

.metrics { display: flex; gap: 14px; margin: 30px 0 8px; }
.metric { flex: 1; background: #030712; border: 1px solid #0d1e42; border-top: 1px solid #1d4ed8; border-radius: 3px; padding: 20px 18px; text-align: center; }
.metric .v { font-size: 30px; font-weight: 700; color: #f0f6ff; letter-spacing: -1px; }
.metric .l { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 2.5px; text-transform: uppercase; color: #3b82f6; margin-top: 6px; }
.metric .s { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #1e3a6e; margin-top: 3px; }

.tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 4px; text-transform: uppercase; color: #3b82f6; margin: 30px 0 12px; }
.idle { text-align: center; padding: 60px 0; }
.idle-sym { font-family: 'JetBrains Mono', monospace; font-size: 22px; letter-spacing: 12px; color: #0a1428; margin-bottom: 18px; }
.idle-hint { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 2.5px; color: #0d1e3a; text-transform: uppercase; }

/* dataframe dark theme */
[data-testid="stDataFrame"] { background: #030712 !important; border: 1px solid #0d1e42 !important; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hdr">
  <div class="hdr-mono">▦ &nbsp; A I O S &nbsp; · &nbsp; P a p e r w o r k &nbsp; t o &nbsp; D a t a</div>
  <div class="hdr-title">Drop your invoices.<br><span class="g">Get a spreadsheet.</span></div>
  <p class="hdr-sub">reads any invoice &nbsp;·&nbsp; every line item &nbsp;·&nbsp; nothing invented</p>
</div>
<div class="hdr-line"></div>
""", unsafe_allow_html=True)


# ── Pre-warm: build the reader once, reuse it ────────────────────────────────
@st.cache_resource(show_spinner=False)
def reader():
    return ix.get_agent()


# Cache by file content so a second read of the same invoice is instant (camera-ready).
@st.cache_data(show_spinner=False)
def read_invoice_cached(file_hash: str, file_bytes: bytes, filename: str) -> dict:
    return ix.extract_invoice(reader(), file_bytes, filename)


uploaded = st.file_uploader("Drop invoices here (PDF)", type=["pdf"],
                            accept_multiple_files=True, label_visibility="visible")

go = st.button("READ INVOICES", use_container_width=True, disabled=not uploaded)

if go and uploaded:
    all_rows, total_value, n_done = [], 0.0, 0
    prog = st.progress(0.0, text="Reading your documents…")
    for i, f in enumerate(uploaded):
        data_bytes = f.getvalue()
        fh = hashlib.md5(data_bytes).hexdigest()
        prog.progress((i + 0.3) / len(uploaded), text=f"Reading {f.name}…")
        data = read_invoice_cached(fh, data_bytes, f.name)
        all_rows.extend(ix.to_rows(data, f.name))
        total_value += ix.money_to_float(data.get("total"))
        n_done += 1
        prog.progress((i + 1) / len(uploaded), text=f"Read {f.name}")
    prog.empty()

    df = pd.DataFrame(all_rows)

    saved_min = n_done * MANUAL_MIN_PER_DOC
    st.markdown(f"""
<div class="metrics">
  <div class="metric"><div class="v">{n_done}</div><div class="l">invoices read</div><div class="s">{len(df)} line items</div></div>
  <div class="metric"><div class="v">R&nbsp;{total_value:,.0f}</div><div class="l">total captured</div><div class="s">across all invoices</div></div>
  <div class="metric"><div class="v">~{saved_min} min</div><div class="l">time saved</div><div class="s">vs typing by hand</div></div>
</div>
""", unsafe_allow_html=True)

    st.markdown('<div class="tag">extracted data</div>', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Blank cells (e.g. a missing invoice number) stay blank — the trust beat.
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("DOWNLOAD SPREADSHEET", data=csv, file_name="invoices.csv",
                       mime="text/csv", use_container_width=True)
else:
    st.markdown("""
<div class="idle">
  <div class="idle-sym">▦ &nbsp; ▦ &nbsp; ▦</div>
  <div class="idle-hint">drop invoices &nbsp;·&nbsp; read &nbsp;·&nbsp; download the spreadsheet</div>
</div>
""", unsafe_allow_html=True)
