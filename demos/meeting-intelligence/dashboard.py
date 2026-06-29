"""
AIOS · Meeting Intelligence — Deepgram demo (two-tab end-to-end).

Tab 1 — Capture & Log:  upload audio OR a transcript -> transcript + summary + action items
                        -> click the client to log it to the CRM (everything dated).
Tab 2 — Ask the AI:     ask anything across logged meetings (all clients, or filter to one);
                        date / person / topic questions, full reviews.

Same visual language as the Drive (8502) and Invoice (8503) demos. Runs on port 8504.
"""
import hashlib
from datetime import date

import streamlit as st

import ask
import store
import transcribe as tx

st.set_page_config(
    page_title="AIOS · Meeting Intelligence",
    page_icon="◎",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Audio -> Deepgram; text -> read directly. Both can be logged to the CRM.
UPLOAD_TYPES = ["mp3", "wav", "m4a", "mp4", "ogg", "webm", "txt", "md", "vtt", "srt", "docx", "pdf"]

store.ensure_db()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap');
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; background: #02040e !important; color: #c8d8f8; }
.stApp { background: #02040e !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; max-width: 940px !important; }
.stApp::before {
    content: ''; position: fixed; inset: 0;
    background-image: linear-gradient(rgba(37,99,235,0.035) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(37,99,235,0.035) 1px, transparent 1px);
    background-size: 52px 52px; pointer-events: none; z-index: 0;
}
.hdr { padding: 48px 0 22px; text-align: center; }
.hdr-mono { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 5px; text-transform: uppercase; color: #1d4ed8; margin-bottom: 18px; }
.hdr-title { font-size: 42px; font-weight: 700; color: #f0f6ff; letter-spacing: -2px; line-height: 1.08; margin-bottom: 12px; }
.hdr-title .g { background: linear-gradient(100deg, #3b82f6 0%, #818cf8 60%, #c084fc 100%); -webkit-background-clip: text; background-clip: text; color: transparent; }
.hdr-sub { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #1e3a6e; letter-spacing: 1.5px; }
.hdr-line { width: 1px; height: 28px; background: linear-gradient(to bottom, transparent, #1d4ed8, transparent); margin: 20px auto 8px; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 8px; justify-content: center; border-bottom: 1px solid #0d1e42; }
.stTabs [data-baseweb="tab"] { font-family: 'JetBrains Mono', monospace !important; font-size: 11px !important; letter-spacing: 3px !important; text-transform: uppercase; color: #1e3a6e !important; }
.stTabs [aria-selected="true"] { color: #3b82f6 !important; }

.stFileUploader label, .stDateInput label, .stTextInput label, .stTextArea label, .stSelectbox label, .stRadio label { font-family: 'JetBrains Mono', monospace !important; font-size: 9px !important; letter-spacing: 3px !important; text-transform: uppercase !important; color: #1e3a6e !important; }
.stFileUploader > div { background: #030712 !important; border: 1px dashed #1d4ed8 !important; border-radius: 4px !important; }
.stTextInput > div > div > input, .stTextArea textarea { background: #030712 !important; border: 1px solid #0f2050 !important; color: #c8d8f8 !important; }

.stButton > button {
    background: linear-gradient(135deg, #1d4ed8 0%, #4f46e5 100%) !important; border: none !important; border-radius: 3px !important;
    color: #e0eaff !important; font-family: 'JetBrains Mono', monospace !important; font-size: 11px !important; letter-spacing: 4px !important;
    text-transform: uppercase !important; padding: 13px 0 !important; width: 100%; box-shadow: 0 0 32px rgba(29,78,216,0.25);
}
.stButton > button:hover { box-shadow: 0 0 48px rgba(29,78,216,0.4) !important; }
.stButton > button:disabled { opacity: 0.25 !important; box-shadow: none !important; }

.metrics { display: flex; gap: 12px; margin: 24px 0 20px; }
.metric { flex: 1; background: #030712; border: 1px solid #0d1e42; border-top: 2px solid #1d4ed8; border-radius: 3px; padding: 16px; text-align: center; }
.metric .v { font-size: 24px; font-weight: 700; color: #f0f6ff; letter-spacing: -1px; }
.metric .l { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 2.5px; text-transform: uppercase; color: #3b82f6; margin-top: 5px; }

.tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 4px; text-transform: uppercase; color: #3b82f6; margin: 0 0 10px; }
.transcript-box { background: #030712; border: 1px solid #0d1e42; border-top: 2px solid #1d4ed8; border-radius: 3px; padding: 18px 20px; height: 340px; overflow-y: auto; font-size: 13px; line-height: 1.85; color: #7090c8; }
.transcript-box > div { margin-bottom: 11px; }
.spk { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #3b82f6; text-transform: uppercase; display: block; margin-bottom: 2px; }
.summary-card { background: #030712; border: 1px solid #0d1e42; border-top: 2px solid #1d4ed8; border-radius: 3px; padding: 18px 20px; font-size: 13px; line-height: 1.85; color: #9fb4dc; }
.actions-card { background: #030712; border: 1px solid #0d1e42; border-top: 2px solid #4f46e5; border-radius: 3px; padding: 18px 20px; }
.action-item { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px; font-size: 13px; color: #9fb4dc; line-height: 1.5; }
.action-item:last-child { margin-bottom: 0; }
.action-dot { font-size: 9px; color: #818cf8; margin-top: 4px; flex-shrink: 0; }
.muted { color: #1e3a6e; font-size: 12px; font-family: 'JetBrains Mono', monospace; }

/* Logged-meeting rows */
.mrow { display: flex; gap: 12px; align-items: baseline; padding: 9px 14px; background: #030712; border: 1px solid #0d1e42; border-left: 2px solid #1d4ed8; border-radius: 3px; margin-bottom: 7px; }
.mrow .date { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #3b82f6; letter-spacing: 1px; flex-shrink: 0; }
.mrow .who { color: #c8d8f8; font-size: 13px; font-weight: 600; }
.mrow .what { color: #5a7099; font-size: 12px; }

.idle { text-align: center; padding: 48px 0; }
.idle-sym { font-family: 'JetBrains Mono', monospace; font-size: 22px; letter-spacing: 12px; color: #0a1428; margin-bottom: 16px; }
.idle-hint { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 2.5px; color: #0d1e3a; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hdr">
  <div class="hdr-mono">◎ &nbsp; A I O S &nbsp; · &nbsp; M e e t i n g &nbsp; I n t e l l i g e n c e</div>
  <div class="hdr-title">Every conversation,<br><span class="g">filed and searchable.</span></div>
  <p class="hdr-sub">capture &nbsp;·&nbsp; log to the right client &nbsp;·&nbsp; ask anything later</p>
</div>
<div class="hdr-line"></div>
""", unsafe_allow_html=True)


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@st.cache_data(show_spinner=False)
def process(file_hash: str, file_bytes: bytes, filename: str):
    """Audio -> Deepgram transcript; text file -> read directly. Then summarise both."""
    if tx.is_audio(filename):
        tr = tx.transcribe(file_bytes)
        transcript_text = tr.plain_text
        meta = {
            "source": "audio",
            "duration_seconds": tr.duration_seconds,
            "duration_minutes": max(1, round(tr.duration_seconds / 60)) if tr.duration_seconds else None,
            "speaker_count": tr.speaker_count,
            "word_count": tr.word_count,
            "turns": [(u.speaker, u.text) for u in tr.utterances],
        }
    else:
        transcript_text = tx.extract_transcript_text(file_bytes, filename)
        meta = {
            "source": "transcript",
            "duration_seconds": None, "duration_minutes": None, "speaker_count": None,
            "word_count": len(transcript_text.split()),
            "turns": None,
        }
    summary = tx.summarise(transcript_text)
    return transcript_text, summary, meta


tab_capture, tab_ask = st.tabs(["Capture & Log", "Ask the AI"])

# ════════════════════════════ TAB 1 — CAPTURE & LOG ════════════════════════════
with tab_capture:
    uploaded = st.file_uploader(
        "Drop a recording or transcript (audio, txt, vtt, srt, docx, pdf)",
        type=UPLOAD_TYPES, label_visibility="visible",
    )
    fhash = hashlib.md5(uploaded.getvalue()).hexdigest() if uploaded else None

    if st.button("PROCESS", use_container_width=True, disabled=not uploaded):
        st.session_state["processed_hash"] = fhash

    ready = uploaded and st.session_state.get("processed_hash") == fhash
    if ready:
        try:
            with st.spinner("Reading the conversation…"):
                transcript_text, summary, meta = process(fhash, uploaded.getvalue(), uploaded.name)
        except Exception as e:
            st.error(f"Could not process this file: {e}")
            st.stop()

        # Metrics
        cells = []
        if meta["source"] == "audio":
            mins, secs = divmod(int(meta["duration_seconds"] or 0), 60)
            cells.append((f"{mins}:{secs:02d}", "duration"))
            cells.append((str(meta["speaker_count"] or 0), "speakers"))
        cells.append((f'{meta["word_count"]:,}', "words"))
        cells.append(("Transcript" if meta["source"] == "transcript" else "Audio", "source"))
        st.markdown(
            '<div class="metrics">'
            + "".join(f'<div class="metric"><div class="v">{v}</div><div class="l">{l}</div></div>' for v, l in cells)
            + "</div>", unsafe_allow_html=True,
        )

        col_l, col_r = st.columns([6, 4], gap="medium")
        with col_l:
            st.markdown('<div class="tag">transcript</div>', unsafe_allow_html=True)
            if meta["turns"]:
                body = "".join(f'<div><span class="spk">{esc(s)}</span>{esc(t)}</div>' for s, t in meta["turns"])
            else:
                body = "".join(f"<div>{esc(line)}</div>" for line in transcript_text.splitlines() if line.strip()) \
                    or '<div class="muted">No readable text.</div>'
            st.markdown(f'<div class="transcript-box">{body}</div>', unsafe_allow_html=True)
        with col_r:
            st.markdown('<div class="tag">summary</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="summary-card">{esc(summary.summary)}</div>', unsafe_allow_html=True)
            st.markdown('<div class="tag" style="margin-top:16px">action items</div>', unsafe_allow_html=True)
            if summary.action_items:
                items = "".join(
                    f'<div class="action-item"><span class="action-dot">&#9673;</span><span>{esc(a)}</span></div>'
                    for a in summary.action_items
                )
            else:
                items = '<div class="muted">No action items detected.</div>'
            st.markdown(f'<div class="actions-card">{items}</div>', unsafe_allow_html=True)

        # ── Log to CRM ───────────────────────────────────────────────────────
        st.markdown('<div class="tag" style="margin-top:26px">log to crm</div>', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 1], gap="medium")
        with c1:
            meeting_date = st.date_input("Meeting date", value=date.today())
        with c2:
            default_title = uploaded.name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
            title = st.text_input("Title", value=default_title)

        roster = store.list_clients()
        NEW = "➕ New client"
        pick = st.radio("Save it for…", roster + [NEW], horizontal=True)
        client_name = pick
        if pick == NEW:
            client_name = st.text_input("New client name", placeholder="e.g. Hartley Retail Group")

        if st.button("LOG TO CRM", use_container_width=True, key="log"):
            if not (client_name or "").strip():
                st.warning("Pick a client or type a new client name first.")
            else:
                rec = store.log_meeting(
                    client=client_name,
                    transcript_text=transcript_text,
                    meeting_date=str(meeting_date),
                    title=title,
                    summary=summary.summary,
                    action_items=summary.action_items,
                    source=meta["source"],
                    duration_minutes=meta["duration_minutes"],
                    speaker_count=meta["speaker_count"],
                )
                st.success(
                    f"✓  Logged to {rec['client']} · meeting dated {rec['meeting_date']} · "
                    f"{len(summary.action_items)} action items. Ask about it in the “Ask the AI” tab."
                )
    else:
        st.markdown("""
<div class="idle">
  <div class="idle-sym">◎ &nbsp; ◎ &nbsp; ◎</div>
  <div class="idle-hint">drop a recording or transcript &nbsp;·&nbsp; process &nbsp;·&nbsp; log to a client</div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════ TAB 2 — ASK THE AI ════════════════════════════
with tab_ask:
    roster = store.list_clients()
    sel = st.selectbox("Filter by client (optional — leave on All to search everything)",
                       ["All clients"] + roster, index=0)
    client_filter = None if sel == "All clients" else sel

    question = st.text_area(
        "Ask anything",
        placeholder='e.g.  "What happened in the meeting with Osun? Give me a full review."\n'
                    'or    "What was recorded on ' + str(date.today()) + ', with who, and what was it about?"',
        height=90,
    )

    if st.button("ASK", use_container_width=True, disabled=not question.strip()):
        try:
            with st.spinner("Reading your meetings…"):
                res = ask.answer(question, client_filter)
        except Exception as e:
            st.error(f"Couldn't answer that: {e}")
            st.stop()
        st.markdown(
            f'<div class="tag" style="margin-top:6px">answer &nbsp;·&nbsp; '
            f'searched {res["meetings_searched"]} meeting(s) &nbsp;·&nbsp; {esc(str(res["scope"]))}</div>',
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            st.markdown(res["answer"])

    # Dated list of what's stored — proves the "everything is dated" promise.
    meetings = store.get_meetings(client_filter)
    st.markdown(f'<div class="tag" style="margin-top:26px">logged meetings &nbsp;·&nbsp; {len(meetings)}</div>',
                unsafe_allow_html=True)
    if meetings:
        rows = "".join(
            f'<div class="mrow"><span class="date">{esc(m["meeting_date"])}</span>'
            f'<span class="who">{esc(m["client"])}</span>'
            f'<span class="what">{esc(m.get("title") or "Meeting")}</span></div>'
            for m in meetings[:25]
        )
        st.markdown(rows, unsafe_allow_html=True)
    else:
        st.markdown('<div class="muted">No meetings logged yet — capture one in the first tab.</div>',
                    unsafe_allow_html=True)
