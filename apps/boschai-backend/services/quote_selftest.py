"""Does the model, on the real prompt, actually understand a technician?

The unit tests script the model's answers, so they prove the routing and the guards and
nothing whatsoever about the prompt. This runs the real call — and it lives on the
server because the working Anthropic key is on Railway, not on the laptop this was
written on. Hitting /quotebot/selftest?key=… is how the prompt gets verified without
guessing, and without sending a single WhatsApp message.

Nothing here touches Twilio, the database, or a customer. It reads and it reports.
"""
from services import quote_engine as engine

BLANK = {"job": {}, "history": [], "state": "collecting"}

CARD_SHOWN = {
    "job": {"customer_name": "Sarah Adams", "customer_phone": "+27825551234",
            "customer_email": "sarah@gmail.com",
            "line_items": [{"description": "2 x sliding panels, lounge — 6.38 "
                                           "laminated safety glass", "amount": 11500}],
            "total": 11500},
    "history": [{"who": "technician", "said": "sarah adams 0825551234 2 panels r11500"},
                {"who": "bot", "said": "showed the card"}],
    "state": "ready",
}

ASKED_FOR_NUMBER = {
    "job": {"customer_name": "Johan", "total": 2500,
            "line_items": [{"description": "Window repair", "amount": 2500}]},
    "history": [{"who": "technician", "said": "fixed a window for johan, 2500"},
                {"who": "bot", "said": "Nice one. What's Johan's number?"}],
    "state": "collecting",
}


def _digits(value) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())


# (label, session, message, expected action, extra check on the merged job)
CASES = [
    ("a full job, typed the way he types it", BLANK,
     "sarah adams 0825551234 sarah@gmail.com 2 slidin panels lounge 6.38 lam, "
     "replaced both tracks, r11500 incl labour", "confirm",
     lambda j: j.get("total") == 11500 and _digits(j.get("customer_phone")).endswith("5551234")),

    ("half a job", BLANK, "fixed a window for johan, 2500", "ask",
     lambda j: j.get("total") == 2500 and not j.get("customer_phone")),

    ("just the number, after being asked", ASKED_FOR_NUMBER, "076 389 7179", "confirm",
     lambda j: _digits(j.get("customer_phone")).endswith("3897179")),

    ("plain approval", CARD_SHOWN, "send", "send", None),
    ("approval in Afrikaans", CARD_SHOWN, "ja stuur dit vir haar", "send", None),
    ("approval, casually", CARD_SHOWN, "yes please send that to her", "send", None),
    ("a thumbs up", CARD_SHOWN, "\U0001f44d", "send", None),

    # The swipe-to-reply body that broke the first build: WhatsApp pastes the message
    # being replied to above what he typed, so SEND arrives wrapped in our own card.
    ("swipe-to-reply, our card comes back with SEND on the end", CARD_SHOWN,
     "Here it is.\n\n*Sarah Adams*\n082 555 1234 · sarah@gmail.com\n\n"
     "• 2 x sliding panels, lounge — R 11 500.00\n\n*Total: R 11 500.00*\n\n"
     "Send it?\nSEND", "send", None),

    ("a correction", CARD_SHOWN, "no make it 12500, i forgot the beading", "confirm",
     lambda j: j.get("total") == 12500 and j.get("customer_name") == "Sarah Adams"),

    ("a question", CARD_SHOWN, "whats the total again?", "chat", None),
    ("scrap it", CARD_SHOWN, "no forget it wrong customer", "cancel", None),

    ("a different job entirely", CARD_SHOWN,
     "different one - pieter van wyk 0711112222, shower door hinge, r850", "confirm",
     lambda j: j.get("total") == 850 and "Pieter" in str(j.get("customer_name") or "")),

    # He is talking about his crew, not approving anything. A keyword matcher sent a
    # quote on this sentence.
    ("not a send: he is talking about his crew", CARD_SHOWN,
     "im sending the boys round tomorrow to finish it", "chat", None),
]


def run() -> dict:
    results, passed = [], 0

    for label, session, message, want, job_check in CASES:
        row = {"case": label, "expected": want}
        try:
            out = engine.understand(session, message)
        except Exception as exc:
            results.append({**row, "ok": False, "error": str(exc)[:300]})
            continue

        got = out.get("action")
        ok = got == want
        row.update({"got": got, "reply": str(out.get("reply") or "")[:160]})

        if ok and job_check:
            merged = engine.merge_job(session["job"], out.get("job") or {},
                                      replace=bool(out.get("replace_job")))
            if not job_check(merged):
                ok = False
                row["job_read_as"] = {k: merged.get(k) for k in
                                      ("customer_name", "customer_phone", "total")}

        row["ok"] = ok
        passed += 1 if ok else 0
        results.append(row)

    return {
        "model": engine.MODEL,
        "passed": passed,
        "of": len(CASES),
        "verdict": "all good" if passed == len(CASES) else "SOMETHING IS WRONG",
        "failures": [r for r in results if not r.get("ok")],
        "results": results,
    }
