# Hormozi figure transcription brief

The prompt given to each transcription agent when the four $100M books were indexed on 2026-09-16. `scripts/hormozi_figures.py --batches N` writes the work lists. Give one list to each general-purpose agent (Sonnet reads the handwriting well), replacing `{BATCH_FILE}` with the list's full path. Then run `scripts/hormozi_index.py`.

Local OCR was tested first and rejected. It read typed boxes but turned handwriting into noise ("PoorCommunlcafton nochermetru"), and the handwritten and whiteboard figures carry the frameworks.

---

You are transcribing images cut out of business books (Alex Hormozi's $100M series) that the user owns, for a private search index on their own machine. The text layer of a PDF misses everything written inside images, so each image needs its words written down.

Your work list is the file:
{BATCH_FILE}

Each line has four tab-separated fields: PNG path, JSON output path, book title, PDF page number.

## For every line, in order

1. If the JSON output path already exists, skip the line (a previous run did it).
2. Read the PNG with the Read tool.
3. Write the JSON output file with the Write tool, containing exactly one JSON object:
   {"id": "<PNG file name without .png, e.g. p062-1>", "kind": "<kind>", "text": "<transcription>"}

## kind: pick exactly one

- "text": typed text set as an image (author notes, callout boxes, quotes)
- "diagram": drawn or whiteboard diagrams, charts, graphs, formulas, flows with labels
- "table": a grid of rows and columns
- "handwritten": handwritten notes or lists
- "screenshot": an ad, social post, email, web page, app screen or document
- "photo": a photograph
- "qr": a QR code (with or without "SCAN ME")
- "logo": a company logo or wordmark
- "decorative": book covers, ornaments, dividers, anything with no information

## text: the rules

- Transcribe every word and number EXACTLY as shown. Never correct spelling, and never fix arithmetic even if the numbers don't add up. Write what the image says.
- Keep reading order: top to bottom, left to right.
- Diagrams: turn the structure into plain sentences using "->" for arrows, "=" for equals, and ";" between parts, so it reads as text. Include every label and number.
- Tables: one row per sentence, as "Column header: value; Column header: value."
- Screenshots: start with what it is in a few words ("Facebook ad:", "Email:"), then the visible copy (headline, body, call to action).
- Handwritten: transcribe as written; write [illegible] for any word you cannot read.
- Photos: "" unless the photo contains visible words or shows something a reader needs (then one short factual sentence).
- qr, logo, decorative: text is "" (empty string).
- No commentary, no opinions, no "this image shows". Just the content.
- Keep the text on one line inside the JSON string and escape quotes properly so the file is valid JSON.

## Two examples of the expected output

A whiteboard diagram:
{"id": "p062-1", "kind": "diagram", "text": "Lifetime Gross Profit (LTGP). *COGS = Cost of Goods Sold. Mo 1 to Mo 5, each month: Revenue -> $50; *COGS -> $10; Gross Profit -> $40. $40 + $40 + $40 + $40 + $40 = $300 LT Revenue - $50 COGS = $250 LTGP."}

A handwritten list:
{"id": "p091-1", "kind": "handwritten", "text": "Dream Outcome -> Amazing, loving relationship in 90 days. Problems -> no good options; not attractive; not available; boring; no chemistry; poor communication; not hot enough; sex isn't good; no intellectual stimulation; not enough effort into relat[ionship]; no time; insecurity; \"needs\" not met; too many unmet expectations; acting crazy, emotional; relationship is dull; want different things; not good at relationships; too much pressure; moves too slow; fizzles out fast; kids involved; sexual incompatibility."}

## Limits

- Only read the batch file and the PNG files it lists. Only write the JSON output paths it lists. Do not create, edit or delete anything else. Do not run scripts. Never read any .env file.
- Do every line. Do not stop early or sample.

## When finished

Reply with a short report: how many lines, how many written, how many skipped because they already existed, a count per kind, and the ids of any figure containing [illegible] or that you could not read at all.
