"""
AIOS Data Pool — LinkedIn Video Demo.
Direct pipeline: Google Drive → text extraction → Claude API.
No Voyage AI or vector DB needed.
"""
import sys
import os
from pathlib import Path

import streamlit as st

MODULE_SCRIPTS = Path(__file__).resolve().parents[2] / \
    "module-installs" / "AIOS-data-pooling-v2" / "AIOS Data Pooling" / "scripts"
sys.path.insert(0, str(MODULE_SCRIPTS))

# Load env so ANTHROPIC_API_KEY is available
try:
    import pool_config as _pc  # side-effect: loads .env
    ANTHROPIC_API_KEY = _pc.ANTHROPIC_API_KEY
except Exception:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

st.set_page_config(
    page_title="AIOS · Drive Intelligence",
    page_icon="◈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: 'Space Grotesk', sans-serif;
    background: #02040e !important;
    color: #c8d8f8;
}
.stApp { background: #02040e !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; max-width: 760px !important; }

.stApp::before {
    content: '';
    position: fixed; inset: 0;
    background-image:
        linear-gradient(rgba(37,99,235,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(37,99,235,0.035) 1px, transparent 1px);
    background-size: 52px 52px;
    pointer-events: none; z-index: 0;
}

.hdr { padding: 64px 0 52px; text-align: center; }
.hdr-mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; letter-spacing: 5px;
    text-transform: uppercase; color: #1d4ed8;
    margin-bottom: 22px;
}
.hdr-title {
    font-size: 48px; font-weight: 700;
    color: #f0f6ff; letter-spacing: -2px;
    line-height: 1.08; margin-bottom: 14px;
}
.hdr-title .g {
    background: linear-gradient(100deg, #3b82f6 0%, #818cf8 60%, #c084fc 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
}
.hdr-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: #1e3a6e; letter-spacing: 1.5px;
}
.hdr-line {
    width: 1px; height: 40px;
    background: linear-gradient(to bottom, transparent, #1d4ed8, transparent);
    margin: 0 auto 40px;
}

.stSelectbox label, .stTextInput label {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 9px !important; letter-spacing: 3px !important;
    text-transform: uppercase !important; color: #1e3a6e !important;
    margin-bottom: 6px !important;
}
.stSelectbox > div > div {
    background: #030712 !important;
    border: 1px solid #0f2050 !important;
    border-radius: 3px !important;
    color: #6080c0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
}
.stTextInput > div > div > input {
    background: #030712 !important;
    border: 1px solid #0f2050 !important;
    border-radius: 3px !important;
    color: #c8d8f8 !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 15px !important;
    padding: 15px 18px !important;
    caret-color: #3b82f6 !important;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.stTextInput > div > div > input:focus {
    border-color: #1d4ed8 !important;
    box-shadow: 0 0 0 1px #1d4ed8, 0 0 28px rgba(29,78,216,0.12) !important;
}
.stTextInput > div > div > input::placeholder { color: #152040 !important; }

.stFormSubmitButton > button {
    background: linear-gradient(135deg, #1d4ed8 0%, #4f46e5 100%) !important;
    border: none !important;
    border-radius: 3px !important;
    color: #e0eaff !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important; letter-spacing: 4px !important;
    text-transform: uppercase !important;
    padding: 15px 0 !important;
    width: 100%;
    box-shadow: 0 0 32px rgba(29,78,216,0.25);
    transition: opacity 0.15s, box-shadow 0.15s !important;
}
.stFormSubmitButton > button:hover {
    opacity: 0.9 !important;
    box-shadow: 0 0 48px rgba(29,78,216,0.4) !important;
}

.ans-outer { margin-top: 48px; }
.ans-topbar {
    display: flex; align-items: center; gap: 14px; margin-bottom: 20px;
}
.ans-tag {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px; letter-spacing: 4px;
    text-transform: uppercase; color: #3b82f6;
}
.ans-rule { flex: 1; height: 1px;
    background: linear-gradient(to right, #0f2050, transparent); }
.ans-card {
    background: #030712;
    border: 1px solid #0d1e42;
    border-top: 1px solid #1d4ed8;
    border-radius: 2px;
    padding: 36px 40px;
    color: #7090c8;
    font-size: 14px; line-height: 2;
    letter-spacing: 0.15px;
}
.ans-card b { color: #a0b8e8; }
.ans-card ul { padding-left: 20px; margin: 10px 0 14px; }
.ans-card li { margin-bottom: 8px; }

.src-bar {
    display: flex; flex-wrap: wrap; gap: 6px;
    margin-top: 20px; padding-top: 18px;
    border-top: 1px solid #0a1830;
}
.src-chip {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; color: #1d4ed8; letter-spacing: 0.5px;
    border: 1px solid #0f2050; border-radius: 2px;
    padding: 4px 12px;
}

.idle { text-align: center; padding: 72px 0; }
.idle-sym {
    font-family: 'JetBrains Mono', monospace;
    font-size: 22px; letter-spacing: 12px;
    color: #0a1428; margin-bottom: 18px;
}
.idle-hint {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; letter-spacing: 2.5px;
    color: #0d1e3a; text-transform: uppercase;
}
</style>
""", unsafe_allow_html=True)


# ── Drive helpers ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_folders():
    try:
        from drive_client import drive_service
        res = drive_service().files().list(
            q="mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false",
            fields="files(id,name)",
            orderBy="name",
            pageSize=50,
        ).execute()
        return {f["name"]: f["id"] for f in res.get("files", [])}
    except Exception as e:
        st.error(f"Could not load Drive folders: {e}")
        return {}


@st.cache_data(ttl=30, show_spinner=False)
def get_files_in_folder(folder_id: str):
    try:
        from drive_client import drive_service
        res = drive_service().files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'",
            fields="files(id,name,mimeType)",
            orderBy="name",
            pageSize=100,
        ).execute()
        return res.get("files", [])
    except Exception:
        return []


def fetch_texts(files: list, max_chars_per_file: int = 2000) -> list[dict]:
    """Extract text from a list of Drive file dicts."""
    from drive_client import extract_text
    results = []
    for f in files:
        text = extract_text(f["id"], f.get("mimeType", ""), f.get("name", ""))
        if text and text.strip():
            results.append({
                "name": f["name"],
                "text": text[:max_chars_per_file],
            })
    return results


def ask_claude(question: str, docs: list[dict]) -> dict:
    """Send extracted docs + question to Claude and get a cited answer."""
    from anthropic import Anthropic

    if not docs:
        return {"answer": "No readable content found in the selected files.", "sources": []}

    # Build context block
    context = "\n\n---\n\n".join(
        f"[{d['name']}]\n{d['text']}" for d in docs
    )

    system = (
        "You are a research assistant. Answer the question using ONLY the source documents provided.\n"
        "Rules:\n"
        "1. Do not invent or infer anything not present in the documents.\n"
        "2. Cite every claim with the source file name in brackets, e.g. [FileName].\n"
        "3. Structure your answer clearly with bold section headings where appropriate.\n"
        "4. Be thorough and detailed — cover all relevant points across all documents.\n"
        "5. If the answer is not in any document, say exactly: 'This was not found in the provided documents.'"
    )

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": (
            f"Source documents:\n\n{context}\n\n"
            f"Question: {question}"
        )}],
    )

    answer = "".join(b.text for b in resp.content if b.type == "text").strip()
    sources = [d["name"] for d in docs]
    return {"answer": answer, "sources": sources}


# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hdr">
  <div class="hdr-mono">◈ &nbsp; A I O S &nbsp; · &nbsp; D r i v e &nbsp; I n t e l l i g e n c e</div>
  <div class="hdr-title">Your documents.<br><span class="g">Plain English answers.</span></div>
  <p class="hdr-sub">semantic search &nbsp;·&nbsp; cited sources &nbsp;·&nbsp; nothing invented</p>
</div>
<div class="hdr-line"></div>
""", unsafe_allow_html=True)

# ── Folder + file selectors (outside form — updates instantly) ────────────────
folders = get_folders()
folder_options = ["— select a folder —"] + list(folders.keys())

folder_name = st.selectbox("Folder", folder_options, label_visibility="visible")
folder_id = folders.get(folder_name)

files_in_folder = get_files_in_folder(folder_id) if folder_id else []
file_display = ["All files in folder"] + [f["name"] for f in files_in_folder]

file_choice = st.selectbox(
    "Narrow to specific file  (optional)",
    file_display,
    label_visibility="visible",
    disabled=(not folder_id),
)

# ── Question + submit ─────────────────────────────────────────────────────────
with st.form("search", border=False):
    question = st.text_input(
        "Question",
        placeholder="e.g.  What are the key risks identified in this project?",
        label_visibility="visible",
    )
    submitted = st.form_submit_button("SEARCH", use_container_width=True)

# ── Run search ────────────────────────────────────────────────────────────────
if submitted:
    if not question.strip():
        st.warning("Enter a question first.")
    elif not folder_id:
        st.warning("Select a folder first.")
    else:
        # Determine which files to read
        if file_choice == "All files in folder":
            target_files = files_in_folder[:100]
        else:
            target_files = [f for f in files_in_folder if f["name"] == file_choice]

        with st.spinner("Reading your documents..."):
            docs = fetch_texts(target_files)

        if not docs:
            st.warning("No readable content found in the selected files. Try a different folder or file.")
        else:
            with st.spinner(f"Analysing {len(docs)} document(s)..."):
                result = ask_claude(question, docs)

            answer = result["answer"]
            sources = result["sources"]

            # Render answer — convert markdown-ish bold and newlines to HTML
            import re
            html_answer = answer
            html_answer = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html_answer)
            html_answer = html_answer.replace("\n\n", "</p><p>").replace("\n", "<br>")
            html_answer = f"<p>{html_answer}</p>"

            chips = "".join(f'<span class="src-chip">⬡ {s}</span>' for s in sources)

            st.markdown(f"""
<div class="ans-outer">
  <div class="ans-topbar">
    <span class="ans-tag">answer</span>
    <div class="ans-rule"></div>
    <span style="font-family:'JetBrains Mono',monospace;font-size:9px;color:#0f2050;letter-spacing:2px;">
      {len(docs)} DOCUMENT(S) READ
    </span>
  </div>
  <div class="ans-card">{html_answer}</div>
  <div class="src-bar">{chips}</div>
</div>""", unsafe_allow_html=True)

else:
    st.markdown("""
<div class="idle">
  <div class="idle-sym">◈ &nbsp; ◈ &nbsp; ◈</div>
  <div class="idle-hint">select a folder &nbsp;·&nbsp; ask a question &nbsp;·&nbsp; get answers</div>
</div>
""", unsafe_allow_html=True)
