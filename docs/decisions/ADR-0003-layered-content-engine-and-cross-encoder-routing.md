# ADR-0003: Layered content engine (three paths, one validator) with cross-encoder routing; standalone templating blueprint retired

## Status

Accepted (product owner, 2026-10-18 — "we go with your verdict only", full review approved without exceptions)

## Date

2026-10-18

## Context

Three design documents were reviewed before chunk 0.2 (review of 2026-10-18, owner-approved):

1. **Deterministic Semantic Templating Blueprint** — proposes replacing
   generative LLM rewrites entirely with extractive parsing plus
   deterministic markdown templating, advertising "$0.00 / sub-5ms / zero
   hallucination risk".
2. **Layered AEO Content Engine Design** — proposes three routed paths
   (template-only / constrained LLM rewrite / ask the customer) feeding
   one shared validator, with code doing the routing.
3. **Cross-Encoder Routing: Honest Assessment** — endorses the cross-encoder
   as the extract/score/route step, names the overclaims, and lists five
   required changes (retrieve-then-rerank, tuned thresholds, validator
   after every path, renamed low band, swappable provider).

Review findings (all accepted by the owner):

- The templating blueprint is **superseded by the layered design**, which
  explicitly identifies the pure extract-and-template engine as a failed
  extreme: it cannot choose the right passage, fill a content gap, or
  write a clear standalone answer.
- The blueprint's performance matrix is misleading: cost and latency move
  into extraction + routing (the model that scores passages), and an
  extractive result is not automatically safe to publish — a perfectly
  extracted passage can still be outdated, partial, or
  context-dependent. "Zero risk" and "bulletproof" are excluded from all
  specs.
- The blueprint's reference code has defects to avoid when the template
  layer is built: 50-word truncation cuts mid-sentence and can drop a
  negation (meaning flip); entity bolding is a case-sensitive substring
  match without word boundaries; missing table cells render as `None`;
  `## What is {keyword}?` produces ungrammatical headings for many
  keyword forms.

## Decision

**1. The Layered AEO Content Engine is the official fix-generation
architecture.** Three paths, one validator:

| Situation | Path |
|---|---|
| A strong, self-contained answer exists on the page | Template only |
| An answer exists but is buried, vague, or context-dependent | Constrained LLM rewrite (passage-only input, no new facts) |
| No usable answer on the page | Ask the customer |

All three paths feed **one validator**; anything that fails is held back,
never published.

**2. The cross-encoder is the concrete implementation of the routing
step.** A local cross-encoder reranker (ms-marco-MiniLM-L-6-v2 class,
CPU-capable) scores how well each candidate passage answers the target
question; code routes on the score. This replaces the generic "decision
model or small language model" entry for the passage-relevance row in
`ARCHITECTURE.md`'s decision table.

**3. All five "what to change" items from the honest assessment are hard
requirements, not advice:**

- **Retrieve, then rerank:** embedding prefilter narrows chunks; only the
  top few go to the cross-encoder.
- **Thresholds are tuned, not guessed:** calibrated on ~200 labeled
  page/question pairs, chosen by measured accuracy.
- **Validator runs after every path**, including the template path.
- **Low band renamed "no good passage on this page"** — other pages of
  the site are checked before falling back to the customer.
- **The rewrite provider stays swappable** (GPT-4o-mini class starting
  point, never hardwired).

**4. Routing observability is a requirement from day one:** every routing
decision is logged (score, band, path chosen, model version) and
thresholds live in configuration, not code constants. The 200-pair
tuning set is bootstrapped from these production logs instead of a later
manual labeling sprint.

**5. Sequencing (matches the layered design's first version):** build
extract + template path + validator first, with "ask the customer" as
the fallback. The constrained-LLM layer is added only when real pages
show where the template path fails — the data decides.

**6. The validator interface is specified before the router.** The
validator also serves the Phase 1 audit engine, so its contract (checks,
return shape, reject/hold semantics) is designed early and independently
of routing.

**7. Honesty constraint on validation:** automated code checks cover
numbers, names, dates, length limits, schema validity, and simple
negation-word presence. Semantic "meaning has not flipped" checking is
NOT claimed as automated; ambiguous cases go to human approval (which
the publish flow already requires).

**8. Chunking is structure-aware:** chunk per heading section, keep the
heading path as chunk context, tables as their own chunks. Fixed-size
token windows are rejected.

**9. Runtime note for the dev machine:** when the routing chunk lands,
prefer an ONNX INT8 quantized reranker runtime over full torch
(~2 GB dependency on the owner's Windows device); final choice is made
at that chunk's DEFINE step.

**10. Template-layer code rules (when built):** sentence-boundary
truncation (never word-count chopping that can drop negations);
word-boundary, case-insensitive entity bolding; no `None` cells in
generated tables; intent-aware question heading templates.

**11. The standalone Deterministic Semantic Templating Blueprint is
retired as a build target.** It remains in `docs/references/` as source
material for the template path only. Its performance matrix is excluded
from all specifications.

## Alternatives Considered

### Build the templating blueprint standalone (its original framing)

- Pros: cheapest, fastest, deterministic
- Cons: cannot choose the passage, fill gaps, or write standalone
  answers; superseded by the owner's own layered design; marketing
  claims ("$0.00 / sub-5ms / zero risk") do not survive review
- **Rejected** as a standalone target; template path retained as one
  layer

### Pure LLM rewrite everywhere

- Pros: handles every input shape
- Cons: cost, latency, hallucination risk on every page; the layered
  design exists precisely to avoid this
- **Rejected**

### Calibrated probability model for routing instead of score thresholds

- Pros: interpretable confidence values
- Cons: requires calibration data and machinery before any value is
  delivered; raw ranking scores + tuned thresholds + logged decisions
  reach the same routing quality earlier
- **Deferred** — revisit if logged scores prove poorly separated

### Fixed-size token-window chunking

- Pros: trivially simple
- Cons: shreds exactly the answer passages the system depends on;
  heading context lost
- **Rejected**

## Consequences

- The "Does this passage answer the question directly?" row in
  `ARCHITECTURE.md`'s decision table is implemented as cross-encoder
  routing (amendment recorded in the register).
- "TypeSafe Jev" (Rev 2 decision-model candidate) keeps its Rev 2 status:
  a candidate to test on ~200 labeled examples before committing — the
  cross-encoder takes over only the passage-relevance job, not intent
  classification, sentiment, or auto-apply decisions (per the honest
  assessment's point 7).
- The fixes chunk (Phase 3 territory) inherits a large pre-made design;
  its DEFINE step focuses on interface contracts, not re-litigating the
  architecture.
- Two new artifacts are owed when their chunks arrive: the validator
  interface spec (before routing exists) and the prompt→page mapping
  table (the `prompts` app is the question source; the mapping is the
  missing piece named in the assessment's point 6).
- Reference documents added to `docs/references/`: Layered AEO Content
  Engine Design.pdf; Cross-Encoder Routing Honest Assessment.pdf;
  semantic_templating_blueprint.pdf (retired blueprint, source material
  only).
