---
name: alex
description: Ask Alex Hormozi's books ($100M Offers, Leads, Money Models, Lost Chapters) anything, or build with them, such as an offer PDF for a client, a money model or a lead magnet, with every idea cited to a book and page. Use when Heinrich types /alex or /hormozi, or asks what Hormozi says about something.
argument-hint: "[question, or a job like: offer PDF for <client>]"
---

# Alex

> Ask Alex Hormozi's books anything, or have them build something with you. Searches the local library ($100M Offers, $100M Leads, $100M Money Models, $100M Lost Chapters), reads the chapters that matter, and applies them to the job in front of us, with every idea traced to a book and a page. `/hormozi` does the same thing.

## Variables

request: $ARGUMENTS

---

## What this is for

Three kinds of request come in, and each ends differently:

| Kind | Sounds like | Ends with |
|---|---|---|
| **Ask** | "how should I price the audit", "what does he say about guarantees for services" | An answer applied to Heinrich's situation, with citations |
| **Build** | "create me a PDF with my offer for {client}", "design a money model for the quote bot", "write a lead magnet for dentists" | A deliverable, then a discussion of the choices in it |
| **Review** | "tear this offer apart", "score my cold email against the book" | A scored critique and the three changes worth making |

If `request` is empty, ask in one line what he wants to work on. Nothing else.

---

## Step 1: Check the library

```bash
uv run --no-project --system-certs --with pymupdf --with numpy --with voyageai --with python-dotenv --with truststore python scripts/hormozi_search.py --status
```

If it says nothing is indexed, or `ls Hormozi/*.pdf` shows a book the status does not list, build the index. Unchanged books are skipped, so this is safe to run any time, and a full build costs about five US cents:

```bash
uv run --no-project --system-certs --with pymupdf --with numpy --with voyageai --with python-dotenv --with truststore python scripts/hormozi_index.py
```

**A new book also needs its images read.** Run `scripts/hormozi_figures.py --batches 6` (with `--with pymupdf --with python-dotenv`). It cuts out every image and writes work lists to `Hormozi/figures/_batches/`. Give each list to a general-purpose agent (model sonnet, in the background) with the brief in `reference/hormozi-figure-brief.md`, putting the list's path where it says `{BATCH_FILE}`. Then re-run the indexer. `hormozi_index.py --audit` lists every page as indexed or skipped with the reason, and says whether the saved index is up to date.

Don't narrate this step unless something is wrong.

---

## Step 2: Search wide, then read deep

**Search wide.** Break the request into 3 to 6 searches, one idea each, and run them in ONE call. Phrase at least one in Hormozi's own words and one in plain words, because the search matches both exact names and meaning:

```bash
uv run --no-project --system-certs --with pymupdf --with numpy --with voyageai --with python-dotenv --with truststore python scripts/hormozi_search.py "value equation dream outcome likelihood time effort" "how to make a service offer worth more than its price" "guarantee for a service business" --k 6
```

Options: `--book offers|leads|money-models|lost-chapters` narrows to one book, `--k` sets passages per question (default 6), `--toc` lists every chapter with pages.

**Where things live.** Use this to aim the searches and to know which chapter to read:

| Topic | Read |
|---|---|
| Building an offer from scratch | Offers ch 6 *The Value Equation*, ch 8 *The Thought Process*, ch 9 *Problems & Solutions*, ch 10 *Trim & Stack* |
| Pricing, market choice | Offers ch 3 *Commodity Problem*, ch 4 *Starving Crowd*, ch 5 *Charge What It's Worth* |
| Scarcity, urgency, bonuses, guarantees, naming | Offers ch 12 to 16, one chapter each |
| Upsells, downsells, continuity, attraction offers | Money Models sections II to VI; Lost Chapters Section C |
| Unit economics (CAC, lifetime gross profit, payback) | Lost Chapters Section B |
| Who to sell to | Lost Chapters *Your First Avatar*; Offers ch 4 |
| Getting leads | Leads *#1 Warm Outreach*, *#2 Post Free Content*, *#3 Cold Outreach*, *#4 Run Paid Ads* |
| Lead magnets | Leads *Engage Your Leads: Offers and Lead Magnets* |
| Referrals, affiliates, agencies, staff | Leads Section IV; Lost Chapters Section D |

**Read deep.** A passage is about 380 words and most of his frameworks run for pages. When a search hit belongs to a framework with steps (the Value Equation, the problem-to-solution list, the guarantee types, MAGIC naming, the four offer types in a money model), read the whole chapter before using it:

```bash
uv run --no-project --system-certs --with pymupdf --with numpy --with voyageai --with python-dotenv --with truststore python scripts/hormozi_search.py --chapter "guarantees" --book offers
```

Never build from a fragment when the chapter is one command away.

**Look at the diagram when it matters.** Words inside the books' images (whiteboard formulas, handwritten worked examples, ad screenshots, author-note boxes) were transcribed and sit inside passages as `[Figure: ...]`. A transcript gives the labels and numbers but not the layout. When a figure carries the point you're using, open the page and read the PNG it prints:

```bash
uv run --no-project --system-certs --with pymupdf --with numpy --with voyageai --with python-dotenv --with truststore python scripts/hormozi_search.py --page 62 --book lost-chapters
```

Figures are transcribed exactly as drawn, arithmetic included. If a diagram's numbers don't add up, that is the book, so say so rather than repeating the sum as correct.

If a line under the header starts with `! keyword only`, meaning search failed (usually Voyage was unreachable) and the results are keyword matches only. They are still usable. Mention it only if the results look thin.

---

## Step 3: Load the business side (Build and Review; Ask only when it is about his own business)

**Boschly's own offers:** `context/linkedin/offers-and-funnels.md`, `outputs/crm/offers.json`, `outputs/offer/offer-thesis-2026-08-03.md`, `context/icp.md`, `context/strategy.md`.

**A named client:** search in this order and read what you find.

1. `outputs/crm/crm.csv` (grep the name and the firm) for `notes`, `background`, `next_action`, `segment`, `status`
2. `outputs/crm/activity-log.csv` for every touch and note on that contact
3. `outputs/voice/meetings/*/transcript.md` for what they actually said
4. `auditos/03-active-audits/<slug>/` if an audit exists
5. `outputs/research/` and the memory index for anything filed on them

Say what you found and where, in one or two lines. **If there is nothing on the client, stop and ask** for what the offer cannot be built without: what they sell, the problem in their own words, what they have said about budget, and what Boschly would deliver. An offer built on an invented problem is worse than no offer.

---

## Step 4: Do the job

### Ask

Lead with the answer applied to his situation, then the reasoning from the book. Cite inline as *(Offers p. 142)* or *(Money Models pp. 87-89)*. End with a one-line **Sources** list.

### Review

Score the thing against the framework it is trying to use, usually the Value Equation (dream outcome, perceived likelihood, time delay, effort and sacrifice) plus the relevant enhancers. Show the score per lever with the evidence, cite the pages, then give the **three changes worth making**, most valuable first.

### Build: an offer PDF

Work the Grand Slam Offer steps from the chapters you read, in order, before writing a word of copy:

1. **Dream outcome** in the client's words, not ours.
2. **Every problem** between them and it: before, during and after, including the ones about time, effort and belief.
3. **A solution for each problem**, then how each gets delivered.
4. **Trim and stack:** keep what is high value to them and low cost to deliver.
5. **Bonuses, guarantee, scarcity, urgency, name,** each chosen from its chapter.
6. **Price against value**, and a **money model** if there is a real smaller way in or a continuity piece.

Then:

1. Copy `reference/offer-template.html` to `outputs/offers/<client-slug>/offer-YYYY-MM-DD.html` and replace every block. Delete blocks that don't apply. The template's comments say what each block is for.
2. Render it and require two pages. Allow three only if the stack needs it and say why.
   ```bash
   uv run --no-project --system-certs --with playwright --with pypdf python scripts/html_to_pdf.py outputs/offers/<client-slug>/offer-YYYY-MM-DD.html --pages 2
   ```
3. Check that `grep -c Ridgeback` on the HTML returns 0. Ridgeback Plumbing is the template's fictional client, so any match means a block was missed.
4. Look at the pages before handing over. Render them to PNG and read them:
   ```bash
   uv run --no-project --system-certs --with pymupdf python -c "import pymupdf,sys; d=pymupdf.open(sys.argv[1]); [p.get_pixmap(dpi=110).save(f'{sys.argv[2]}/offer-p{i+1}.png') for i,p in enumerate(d)]" <pdf> <scratchpad>
   ```
5. Hand over the PDF path, then open the discussion. For each lever, give what was chosen, why (with the page it came from), and the alternative that was considered. Then list the **decisions only Heinrich can make**: prices, whether he will honour the guarantee as written, and whether the scarcity is true. Revise the same HTML and re-render when he answers.

### Build: anything else

Money models, lead magnets, outreach scripts, ad hooks, naming options: put them in the chat unless he asks for a file. A client file goes in `outputs/offers/<client-slug>/`. Anything else goes in `outputs/hormozi/`.

---

## Rules

**The client sees the offer, never the book.** No Hormozi name, no page numbers and no quoted lines go into anything client-facing. The citations belong in the conversation with Heinrich.

**Paraphrase and apply; don't reprint.** Quote at most a sentence or two at a time, and only in chat. The value is in applying the idea to this client, not in copying the text. The books and `Hormozi/.index/` are gitignored and must never be copied into `shares/`, `module-installs/`, an artifact, or anything else that leaves this machine.

**Never invent a citation.** If the library doesn't cover something, say "the books don't cover this", then give your own reasoning and label it as yours.

**Workspace evidence beats the book where they disagree.** Hormozi writes from US gyms, agencies and ecommerce at scale. When the workspace has measured something (firm-specific demos closed 2 of 2 and generic pitches 0 of 7, calls come before WhatsApp, 086/087 numbers can't receive WhatsApp), the measurement wins. Say that the book and the evidence disagree, and why.

**Standing rules for anything client-facing:**
- The business is **Boschly**, never BoschAI.
- **R7,500 is the only price any client has paid.** Every other figure is a working estimate. Flag each one in chat and get Heinrich's yes before the PDF goes out.
- Every value in the stack must be one Heinrich could defend if the client asks where it came from.
- Scarcity and urgency must be **true**. If there is no real constraint, delete the block.
- The reference client is described, never named.
- No job-loss framing. Systems give people time back; they don't replace them.
- Follow the `writing-style` skill: no em dashes and no AI-sounding copy. Use South African English and rand.
