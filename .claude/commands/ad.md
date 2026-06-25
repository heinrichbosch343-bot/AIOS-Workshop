# Ad

> Create a high-quality LinkedIn ad post + Higgsfield image brief. Authority. Pain. Solution. Dream outcome.

## Variables

topic: $ARGUMENTS (optional — the pain point or topic to build the post around)

---

## Instructions

You are creating a complete LinkedIn content package for Heinrich Bosch, founder of Boschly — an AI agency that builds custom AI Operating Systems for business owners.

### Step 1: Load context

Read these files before writing anything:
- `context/linkedin/content-pillars.md` — the 5 pillars posts map to
- `apps/boschai-backend/prompts/linkedin_voice.md` — Heinrich's exact voice and tone
- `context/business-info.md` — what Boschly does and who it serves

### Step 2: Get the topic

If a topic was provided in `$ARGUMENTS`, use it. If not, ask one question:

> "What's the pain point or topic for this post?"

Wait for the answer before proceeding.

### Step 3: Explore the angle internally

Before writing, think through these four angles silently. Do NOT show this thinking to the user — just use it to write a better post:

1. **Which pain** hits hardest for a business owner on this topic? Be specific. Use a number if possible (hours lost, money bleeding, deals missed). Always frame it as a BUSINESS-WIDE bottleneck, never a single tool problem. The reader should think "that's my whole business" not "that's my email."

2. **What authority** does Boschly have to speak on this? Draw from real results where possible:
   - Connie (Osun Consulting) used to manually search Google Drive for hours every time she built an annual report or RFP response. We built a system that pulls the right data automatically. That search time is gone.
   - Business owners are losing 8-15 hours a week across scattered tasks: emails, follow-ups, meeting notes, data hunting, reporting. We map and eliminate those bottlenecks.
   - We don't sell a tool. We audit the whole business and build an AI layer around it.

3. **What solution** does Boschly provide? Never name a single feature. Always position it as: we find every bottleneck draining your time and money, then build AI around your specific business to eliminate them. The result is an AI Operating System, not a plugin.

4. **What dream outcome** does the business owner actually want? Not a feature. The feeling:
   - Their business runs while they sleep
   - They stop being the bottleneck in their own company
   - Revenue grows without headcount growing
   - They work ON the business, not IN it
   - Hours recovered every single week, not once

### Step 4: Write the post

Follow this structure exactly, in this order:

```
[AUTHORITY — 1 line. A real result from a real business. Specific. Not a claim, a fact.]

[PAIN — 2-3 lines. The business-wide bottleneck. Time and money bleeding across the whole operation, not one tool. Use a number. Make them feel seen.]

[SOLUTION — 1-2 lines. We map the whole business, find every bottleneck, build AI around it. Never name a single feature. Sell the system, not the part.]

[DREAM OUTCOME — 2-3 lines. The life on the other side. Business runs without them. Hours back every week. Growth without more staff. Make it feel real and specific.]

[HOOK QUESTION — 1 line. Forces them to calculate their own loss. Their time, their money, their bottleneck.]
```

**Rules for the post:**
- 40-55 words MAXIMUM. Every word earns its place or it's cut.
- Each "paragraph" is 1-2 lines only. White space is part of the design.
- Short punchy lines. Mix a 3-word line with a 10-word line. Never uniform.
- No em dashes. Commas or periods only.
- No AI vocabulary: no "leverage", "streamline", "empower", "transformative", "cutting-edge", "seamless", "robust"
- Contractions always: "don't", "isn't", "you're", "we've"
- Never mention a single product, feature, or tool by name
- Always make the reader feel like their WHOLE business is the problem
- The hook question is the last line. One line only. Forces them to calculate their own loss.

### Step 5: Write the Higgsfield prompt

This is the ONLY output after the post. One copy-paste ready prompt. Nothing else.

The prompt must include:
- The full scene description (real people, real place, natural light, moody/cinematic)
- The headline text baked in as typography on the image — placed top-left, white, clean editorial serif, tight leading
- "Small 'Boschly' wordmark, bottom-right corner" — so Heinrich can replace it with the real PNG after

Anti-AI rules always apply:
- No robots, circuits, orbs, holograms, brain imagery
- Real hands, real desks, real offices, natural light, shallow depth of field
- Candid feel, slight imperfection

Output format — just this, nothing else:

---

**PROMPT**

[full Higgsfield prompt, copy-paste ready, everything included]

---

Do NOT add Canva instructions. Do NOT composite the image. Do NOT explain the watermark process. Do NOT add a "Why this image" section. Just the prompt.

### Step 6: Output format

Two sections. That's it.

---

**POST**

[the post]

---

**PROMPT**

[full Higgsfield prompt with headline baked in and "Boschly wordmark bottom-right" noted]

---

Then ask: "Want me to adjust the angle, try a different pain point, or generate a second version?"

---

## The formula — never skip any layer

| Layer | Job | Fail state |
|-------|-----|-----------|
| Authority | Earn the right to speak | Skipping this = sounds like any random person |
| Pain | Hit the exact nerve | Being vague = they scroll past |
| Solution | What Boschly does | Being too technical = they don't get it |
| Dream outcome | The life on the other side | Stopping at "solution" = no reason to care |
| Hook question | Pull them into thinking about themselves | Generic question = no engagement |

## Anti-AI image rules (always apply)

**Never use in image prompts:**
- Robots, humanoid AI figures, circuit boards
- Glowing neon orbs or floating holograms  
- Brain imagery, neural network visualisations
- Fake screens with AI-generated text on them
- Overly symmetrical or obviously staged scenes

**Always use:**
- Real hands, real desks, real phones, real people
- Natural ambient lighting (window light, office light, soft lamp)
- Candid angles, slight imperfection, "shot on iPhone" feel
- Specific real-world contexts (a desk, a coffee shop, a meeting room)
- Shallow depth of field to feel professional but not AI-rendered
