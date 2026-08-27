# TenderPack retrieval layer — Voyage embeddings on Supabase

**Date:** 2026-08-27
**Status:** plan, pending execution
**Repo:** `tenderpack-master/`

---

## 1. What is actually there right now

I read the code before designing anything. The short version: **TenderPack has a retrieval system that has never worked, and could not have worked.** Four independent reasons, any one of which is fatal on its own.

### 1.1 There is no embedding key, so nothing is ever embedded

`src/lib/services/embedding-service.ts:35` returns `null` from `generateEmbedding()` when `OPENAI_API_KEY` is unset. `tenderpack-master/.env.local` sets fifteen variables and `OPENAI_API_KEY` is not among them. `isVectorSearchAvailable()` (line 374) is literally `return !!process.env.OPENAI_API_KEY`, so it has been returning `false` on every call.

Consequence: `embedAndStore()` returns `false` every time, `retrieveKnowledge()` falls through to `keywordFallbackSearch()`, and the `embeddings` table has never received a row.

### 1.2 Even with a key, every write would be rejected

`storeEmbedding()` (line 126) inserts `user_id`, `source_type`, `source_id`, `content`, `embedding`, `metadata`. It does **not** insert `workspace_id`.

The table has `workspace_id uuid REFERENCES workspaces(id)` and the RLS insert policy is:

```sql
CREATE POLICY "embeddings_insert_workspace" ON public.embeddings
  FOR INSERT WITH CHECK (workspace_id IN (SELECT public.user_workspace_ids()));
```

`NULL IN (...)` is never true. Every insert is rejected by RLS.

This is the identical defect class fixed in `proposals-store.ts` earlier this session (`workspace_id: null` → guaranteed RLS rejection). It is silent here for the same reason it was silent there: the write is fire-and-forget inside `Promise.allSettled` at `document-parser.ts:293`, so the rejection never surfaces.

### 1.3 The search functions filter on the wrong column

`match_embeddings` and `retrieve_knowledge` (`migrations/001_expand_schema.sql:312`, `:351`) both filter `e.user_id = filter_user_id`. The RLS model, and the whole rest of the application, scopes by **workspace**. Two people in one workspace would not see each other's indexed knowledge, which defeats the point of a shared bid desk.

### 1.4 The vector index is misconfigured for the data volume

`USING ivfflat (...) WITH (lists = 100)`. ivfflat partitions the vector space using the rows present when the index is built; built on an empty table it degrades to something close to a sequential scan, and `lists = 100` is tuned for roughly 100k+ rows. TenderPack will have hundreds to low thousands.

### 1.5 What this means for the block retriever

Because vector search is dead, **100% of content selection today runs through `block-retriever.ts:37`**:

```ts
for (const tag of block.tags) {
  if (allText.includes(tag.toLowerCase())) score += 15;
}
```

Literal substring matching over 28 static blocks in `block-library.ts`. This is precisely the "differently framed questions" failure. When one department writes *"provide evidence of similar projects completed in the last 5 years"* and another writes *"list comparable engagements undertaken within the preceding five-year period"*, the second one shares almost no vocabulary with the first, and the right case study is never retrieved. There is no error. The pack is just thinner and less responsive, and nobody can tell.

There is a working semantic matcher in the codebase already — `semanticCoverageFallback()` in `requirement-coverage.ts:149` — but it only runs as a **fallback when the LLM's JSON parse fails**. The good mechanism is wired to the error path.

---

## 2. Why we are building this

Three reasons, in order of how much money they are worth.

**Because the wording varies and the meaning does not.** Every organ of state writes its tender in its own house style. The requirement is the same; the sentence is not. Keyword matching needs literal overlap and gets *worse* as the client base widens, because each new department brings new phrasing. Semantic matching gets *better* as the content library grows, because there are more candidates for the nearest match to be found among. This is the scaling argument, and it is correct.

**Because the failure is invisible.** A missed block does not raise. The pack simply does not mention the case study that would have won the functionality points. Nobody reviews what was not included. That is the worst shape a defect can have, and it is the same shape as the `requirement_id` bug fixed earlier today: silently defaulting to "nothing found" while looking exactly like a legitimate result.

**Because the infrastructure is already paid for.** pgvector is enabled, the table exists, the RPCs exist, the search route exists, the pipeline already has a `RETRIEVE` stage with a hook for vector results (`cost-optimized-pipeline.ts:568`). None of it has ever executed. This is finishing a build, not starting one.

---

## 3. What we are building — and what we are deliberately not

### In scope

| # | Thing | Why |
|---|---|---|
| 1 | Voyage provider behind the existing embedding interface | One place that talks to the provider, swappable |
| 2 | Migration `046` — correct dimension, model tagging, HNSW index, workspace-scoped RPCs | The current schema cannot hold a Voyage vector |
| 3 | Fix the `workspace_id` write bug | Without it nothing is ever stored |
| 4 | Index the 28 content blocks | The actual differently-framed-question problem |
| 5 | Hybrid search — vector + keyword, fused | Tender text is full of literal codes that vectors are bad at |
| 6 | A retrieval router with a hard compliance guard | The reasoning layer, see §4 |
| 7 | Semantic block scoring in `block-retriever.ts` | Replaces substring matching as the primary signal |
| 8 | "Search my documents" over `extracted_fields` | Read-only discovery, never autofill |

### Explicitly out of scope, permanently

**The 790 compliance facts do not move behind semantic retrieval.** SBD 1, 3.1, 3.3, 4, 6.1, 8 and 9 are Treasury's forms and name their fields by law. `sbd-autofill.ts` resolves them by exact key against `field-store.ts`, gated on human approval, validity at the tender's closing date, and the `pinned > longest-valid > most-recent > confidence` precedence, with full document/page/excerpt provenance.

Vector search returns the *nearest* candidate above a threshold. It has no concept of wrong. Put a BEE level behind it and it will one day return the expired certificate, or the sister entity's, because they are textually adjacent — with a confident-looking score, into a legal document, behind a Compliance-Pass Guarantee that pays out when that goes wrong.

This is enforced in code, not by convention. See §4.3.

---

## 4. The reasoning layer — when retrieval runs, and when it is refused

A new module, `src/lib/retrieval/router.ts`. Every retrieval request goes through it. It decides *which store answers*, deterministically, with no model call.

### 4.1 The three routes

| Route | Question shape | Store | Example |
|---|---|---|---|
| `exact` | Names a canonical field | Relational (`field-store.ts`) | "What is our B-BBEE level?" · filling SBD 6.1 |
| `semantic` | Open-ended, wording unpredictable | Voyage + pgvector | "Evidence of similar projects in the last five years" |
| `hybrid` | Carries a literal code *and* prose | Both, RRF-fused | "CIDB 5CE electrical work in Gauteng" |

### 4.2 How the route is chosen

Deterministic, in this order:

1. **Canonical field hit** → `exact`. The query normalises to a known `field_key` or a modelled SBD field name. No embedding call, no LLM.
2. **Literal code detected** → `hybrid`. Regex for the identifier families that actually appear in SA tenders: `SBD \d(\.\d)?`, CIDB grades (`\d[A-Z]{2}`), `B-BBEE` levels, `ISO \d+`, `SANS \d+`, tender reference numbers.
3. **Otherwise** → `semantic`.

Deterministic on purpose. A router that asks a model which store to use adds a call, latency, and a new way to be wrong, to answer a question a regex answers correctly.

### 4.3 The guard

`assertNotComplianceFact()` runs before any semantic result is returned. If the resolved route is `semantic` or `hybrid` **and** the caller is a form-filling context, it throws rather than returning a match.

It is a thrown error, not a filter, and not a warning. A filter that silently drops the result leaves the caller with an empty answer that looks like "we do not have that fact" — which is the exact silent-wrong-answer shape this whole plan exists to avoid. Loud is correct here.

### 4.4 Query-side vs document-side embedding

Voyage tunes the two sides of a match differently and takes an `input_type` parameter. Indexing uses `input_type: "document"`, live search uses `input_type: "query"`. Getting this backwards costs retrieval quality silently — it does not error. `apps/boschai-backend/services/embeddings.py` already does this correctly and is the reference.

---

## 5. Use cases — where this runs

**Runs (semantic):**
- Assembly stage picking which of the 28 content blocks answer this tender's requirements
- The `RETRIEVE` pipeline stage pulling past-proposal and case-study passages
- Requirement coverage matching — promoting `semanticCoverageFallback` from error-path to a real signal
- A client searching their own uploaded documents: "show me anything about our insurance"

**Never runs (relational only):**
- Any SBD form field
- Any `company_profiles` canonical column
- Anything read by `sbd-autofill.ts`
- Any value that appears in a submitted document as fact

---

## 6. Technical decisions, with the reasoning

**Model: `voyage-3.5-lite`, 1024 dimensions, configurable.** Priced at parity with OpenAI's small model. The Voyage 4 family additionally shares an embedding space across `-lite`/`-4`/`-large`, meaning quality can be upgraded later without re-indexing the corpus — so the model is a config value, not a schema commitment. Default is set in one constant.

**Dimension must change.** The column is `vector(1536)`, an OpenAI shape. Voyage supports 2048 / 1024 / 512 / 256. 1536 is not available. The column is migrated to 1024.

**Every row records the model that produced it, and search filters on it.** This is the most important schema decision in the plan. Two vectors from different models occupy unrelated coordinate spaces; cosine similarity between them returns a number, and that number is noise. There is no error, no exception, no warning — just quietly meaningless rankings. A `model` column plus a filter in the RPC makes a model switch a no-op on old rows instead of a silent corruption.

**HNSW, not ivfflat.** ivfflat trains on the rows present at build time and was configured for ~100k rows. HNSW needs no training pass, performs well from the first row, and suits hundreds-to-thousands.

**Hybrid, not pure vector.** Tender language is dense with literal identifiers — "SBD 3.3", "CIDB 5CE", "B-BBEE Level 2", "ISO 9001". Embeddings are famously weak on exact rare tokens. Keyword search is excellent at them and weak at paraphrase. Reciprocal Rank Fusion combines the two rankings without needing the two scores to be on a comparable scale, which they are not.

**Degrade to what works today, never to nothing.** No Voyage key, provider down, rate limited: fall back to the existing keyword path and record the reason on the result. Retrieval quality drops; the pack still builds.

---

## 7. Cost

Roughly 28 blocks + a few hundred document chunks per client on the initial index, then one embedding per query. At `voyage-3.5-lite` rates this is cents per client, and the Voyage 4 generation ships with 200M free tokens. Cost is not a factor at this volume; correctness is the only thing being optimised.

---

## 8. Risks and how each is closed

| Risk | Guard |
|---|---|
| Mixed-model vectors silently rank as noise | `model` column + RPC filter; documented in the migration |
| Semantic result reaches an SBD form | `assertNotComplianceFact()` throws; unit-tested both directions |
| Writes silently rejected by RLS | `workspace_id` written and asserted non-null before insert; test asserts the throw |
| Provider outage breaks pack generation | Keyword fallback retained, reason recorded on the result |
| Literal codes lost to fuzzy matching | Hybrid search with RRF |
| Indexing drifts from source rows | `deleteEmbeddingsForSource()` before re-index; idempotent |
| Personal information indexed | `is_sensitive` rows excluded at the indexer, not at render |

---

## 9. Execution order

1. `046_voyage_retrieval.sql` — dimension, `model` column, HNSW, workspace-scoped RPCs, hybrid RPC
2. `src/lib/retrieval/voyage.ts` — provider, `input_type` split, batching, backoff
3. `embedding-service.ts` — provider-agnostic, `workspace_id` fix, non-null assertion
4. `src/lib/retrieval/router.ts` + the compliance guard
5. `src/lib/retrieval/indexer.ts` — content blocks, content library, documents; skips `is_sensitive`
6. `block-retriever.ts` — semantic scoring as primary, keyword as boost, sync path preserved
7. Tests at each step
8. `npx tsc --noEmit`, `npx vitest run`, `npm run build`

**Note for step 6:** `buildAssemblyContext` (`context-builder.ts:57`) is synchronous and calls `retrieveBlocksWithReport`. The async semantic variant is additive — the existing sync signature keeps working and keeps its keyword behaviour, so nothing breaks when embeddings are unavailable.
