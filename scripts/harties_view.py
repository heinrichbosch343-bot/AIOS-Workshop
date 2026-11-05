"""
harties_view.py - the Harties Board page inside Twenty: a visitor dashboard laid out like Plausible's (who visits, where they
came from, which pages they read), then how many have it on their phone and who has listed, by month and by week.

outreach_hub.py shows it when Twenty's frame asks for ?view=harties (twenty_setup.py points the "Harties Board" sidebar item
there). The numbers come from the Harties Board app's own /api/stats feed through harties_status.py. The key for that feed
stays on this PC: it goes in the request and never into the page.
"""

from __future__ import annotations

from datetime import datetime, timezone

import altair as alt
import pandas as pd
import streamlit as st

import harties_status as H
import linkedin_view as LV
import outreach_ui as ui
import replies_view as RV
import reply_status as R

PERIOD_HEAD = ["Opens", "People", "Icon", "Added", "Listed"]
DEFINITIONS = ("Opens is every time the app was opened, so one phone can open it many times. People is different phones. Icon is "
               "phones that opened it from the home screen. Added is phones that put it on the home screen for the first time. "
               "Listed is businesses sent in through Add your business.")
PHONE_NOTE = ("A phone is a person: someone who clears their browser or uses a second phone counts again, and an iPhone that used "
              "both the browser and the icon on one day counts twice.")
TRAFFIC_NOTE = ("A visit ends after 30 minutes with nothing done. Visit length runs from a visit's first page to its last, so time "
                "spent on the last page is not seen. A bounce is a visit that saw one page and tapped nothing. Direct means the "
                "phone did not say where it came from: a WhatsApp link usually shows as Direct, unless the link carries "
                "?ref=whatsapp.")
ACCENT = "#3e63dd"      # Twenty's own accent, readable on its light and dark looks

DASH_CSS = """
<style>
  .hb-top {display:flex; align-items:center; gap:10px; margin:-4px 0 10px 0; font-size:13px; color:var(--mut);}
  .hb-live {display:inline-flex; align-items:center; gap:6px; font-weight:500; color:var(--ink);}
  .hb-live i {width:8px; height:8px; border-radius:50%; background:#30a46c; box-shadow:0 0 0 3px rgba(48,164,108,.18);}
  .hb-card {border:1px solid var(--line); border-radius:10px; padding:14px 16px 6px 16px; margin:0 0 14px 0; background:var(--bg2);}
  .hb-tiles {display:grid; grid-template-columns:repeat(auto-fit, minmax(118px, 1fr)); gap:0;}
  .hb-tile {padding:6px 14px 10px 0; border-right:1px solid var(--line); margin-right:14px;}
  .hb-tile:last-child {border-right:0;}
  .hb-tile .v {white-space:nowrap;}
  .hb-tile span {display:block; font-size:10.5px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; color:var(--mut);}
  .hb-tile b {display:inline-block; font-size:22px; font-weight:700; color:var(--ink); margin-top:4px; font-variant-numeric:tabular-nums;}
  .hb-tile em {font-style:normal; font-size:12px; margin-left:6px; color:var(--faint);}
  .hb-tile em.good-up, .hb-tile em.good-down {color:#30a46c;}
  .hb-tile em.bad-up, .hb-tile em.bad-down {color:#e5484d;}
  .hb-list {width:100%; border-collapse:collapse; font-size:13px; border:none !important; margin:0 0 6px 0;}
  .hb-list tr, .hb-list th, .hb-list td {border:none !important; background:transparent !important;}
  .hb-list th {text-align:left; font-weight:500; font-size:12px; color:var(--faint); padding:4px 0 6px 0;}
  .hb-list th:last-child, .hb-list td.n {text-align:right; width:70px;}
  .hb-list td {padding:2px 0 !important; vertical-align:middle;}
  .hb-list th {padding:4px 0 6px 0 !important;}
  .hb-row {position:relative; padding:6px 8px; border-radius:5px; color:var(--ink); overflow:hidden;}
  .hb-row i {position:absolute; inset:0 auto 0 0; background:var(--soft); border-radius:5px; z-index:0;}
  .hb-row span {position:relative; z-index:1;}
  .hb-row small {position:relative; z-index:1; display:block; font-size:11px; color:var(--faint);}
  .hb-list td.n {font-variant-numeric:tabular-nums; font-weight:600; color:var(--ink); padding-left:10px;}
  .hb-empty {font-size:13px; color:var(--faint); padding:8px 0 12px 0;}
</style>
"""


def tiles_html(block: dict) -> str:
    cells = ""
    for t in H.tiles(block):
        arrow = {"up": "↑ ", "down": "↓ "}.get(t["mood"].split("-")[-1], "")
        cells += (f'<div class="hb-tile"><span>{ui.esc(t["label"])}</span><div class="v"><b>{ui.esc(t["value"])}</b>'
                  f'<em class="{ui.esc(t["mood"])}">{arrow}{ui.esc(t["change"])}</em></div></div>')
    return f'<div class="hb-tiles">{cells}</div>'


def list_html(head: str, rows: list[dict]) -> str:
    if not rows:
        return '<div class="hb-empty">Nothing yet in this period.</div>'
    body = ""
    for r in rows:
        sub = f'<small>{ui.esc(r["sub"])}</small>' if r["sub"] else ""
        body += (f'<tr><td><div class="hb-row"><i style="width:{r["width"]}%"></i><span>{ui.esc(r["name"])}</span>{sub}</div></td>'
                 f'<td class="n">{ui.esc(r["count"])}</td></tr>')
    return f'<table class="hb-list"><tr><th>{ui.esc(head)}</th><th>Visitors</th></tr>{body}</table>'


def chart(block: dict, metric_label: str) -> None:
    points = H.series(block, H.CHART_METRICS[metric_label])
    if not points:
        return
    df = pd.DataFrame({"Day": pd.to_datetime([d for d, _ in points]), metric_label: [v for _, v in points]})
    fill = alt.Gradient(gradient="linear", stops=[alt.GradientStop(color=ACCENT, offset=0), alt.GradientStop(color="rgba(62,99,221,0)", offset=1)],
                        x1=1, x2=1, y1=0, y2=1)
    base = alt.Chart(df).encode(
        x=alt.X("Day:T", title=None, axis=alt.Axis(format="%-d %b", labelAngle=0, tickCount=7, grid=False)),
        y=alt.Y(f"{metric_label}:Q", title=None, scale=alt.Scale(zero=True, nice=True),
                axis=alt.Axis(tickCount=5, labelPadding=6, gridDash=[2, 3], tickMinStep=1, format="~s")),
        tooltip=[alt.Tooltip("Day:T", format="%a %-d %b"), alt.Tooltip(f"{metric_label}:Q", format=",")],
    )
    area = base.mark_area(opacity=0.22, color=fill, interpolate="monotone")
    line = base.mark_line(color=ACCENT, strokeWidth=2.2, interpolate="monotone")
    dots = base.mark_circle(color=ACCENT, size=26, opacity=0.9)
    st.altair_chart((area + line + dots).properties(height=230, padding={"left": 4, "right": 8, "top": 8, "bottom": 2}),
                    width="stretch")


def dashboard(data: dict) -> bool:
    """The Plausible-style part. False when the app does not send these numbers yet (the page then says so)."""
    if not H.traffic_range(data, 28):
        st.markdown(f'<div class="note">{ui.esc(H.NO_TRAFFIC)}</div>', unsafe_allow_html=True)
        return False
    days = st.segmented_control("Period", options=list(H.RANGES), default=28, format_func=lambda d: f"Last {d} days",
                                key="hb-range", label_visibility="collapsed") or 28
    block = H.traffic_range(data, days)
    live = H.num(H.dig(data, "traffic", "liveNow"))
    st.markdown(f'<div class="hb-top"><span class="hb-live"><i></i>{live} on the app now</span>'
                f'<span>· {ui.esc(H.range_label(block))}, compared with the {days} days before</span></div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="hb-card">{tiles_html(block)}</div>', unsafe_allow_html=True)
    metric = st.segmented_control("Chart", options=list(H.CHART_METRICS), default="Visitors", key="hb-metric",
                                  label_visibility="collapsed") or "Visitors"
    chart(block, metric)

    names = data.get("pageNames") if isinstance(data.get("pageNames"), dict) else {}
    left, right = st.columns(2, gap="medium")
    with left:
        channels, sources, devices = st.tabs(["Channels", "Sources", "Devices"])
        with channels:
            st.markdown(list_html("Channel", H.list_rows(block, "channels")), unsafe_allow_html=True)
        with sources:
            st.markdown(list_html("Source", H.list_rows(block, "sources")), unsafe_allow_html=True)
        with devices:
            st.markdown(list_html("Device", H.list_rows(block, "devices")), unsafe_allow_html=True)
    with right:
        top, entry, exit_ = st.tabs(["Top pages", "Entry pages", "Exit pages"])
        with top:
            st.markdown(list_html("Page", H.list_rows(block, "pages", names)), unsafe_allow_html=True)
        with entry:
            st.markdown(list_html("First page", H.list_rows(block, "entries", names)), unsafe_allow_html=True)
        with exit_:
            st.markdown(list_html("Last page", H.list_rows(block, "exits", names)), unsafe_allow_html=True)
    st.markdown(f'<div class="note">{ui.esc(TRAFFIC_NOTE)}</div>', unsafe_allow_html=True)
    return True


def page(now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    st.markdown(RV.CSS, unsafe_allow_html=True)
    st.markdown(LV.CSS, unsafe_allow_html=True)
    st.markdown(DASH_CSS, unsafe_allow_html=True)
    st.title("Harties Board")
    try:
        data = H.report()
    except R.Unreachable as e:
        st.markdown(RV.light(R.RED, "Harties Board: can't read the numbers", f"Twenty asked the Harties Board app and {e}."),
                    unsafe_allow_html=True)
        return

    since = H.day_label(H.dig(data, "stats", "firstDay") or "the first visit")
    st.markdown(f'<p class="sub">Who visits the app, where they came from and what they read. Counting started '
                f'{ui.esc(since)}, so anything before that reads zero · updated {ui.esc(R.ago(data.get("generatedAt"), now))}.</p>',
                unsafe_allow_html=True)
    dashboard(data)

    st.markdown("### On phones and listing")
    ui.strip([(big, label, None) for big, label in H.cards(data)])
    if H.num(data.get("waiting")):
        st.markdown(f'<div class="note">{H.n(data.get("waiting"))} businesses or promos are waiting for you. Nothing shows on the '
                    'board until you approve it on the app\'s review page.</div>', unsafe_allow_html=True)

    st.markdown("### Every month")
    st.markdown(LV.table(["Month"] + PERIOD_HEAD, H.period_rows(data, "months")), unsafe_allow_html=True)
    st.markdown("### Every week")
    st.markdown(LV.table(["Week of"] + PERIOD_HEAD, H.period_rows(data, "weeks")), unsafe_allow_html=True)
    st.markdown(f'<div class="note">{ui.esc(DEFINITIONS)}</div>', unsafe_allow_html=True)

    st.markdown("### Who is listing")
    st.markdown(LV.table(["", "Businesses", "Promos"], H.listing_rows(data)), unsafe_allow_html=True)
    st.markdown(f'<div class="note">{ui.esc(PHONE_NOTE)}</div>', unsafe_allow_html=True)
