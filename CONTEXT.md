# CONTEXT.md — project capsule

**Purpose of this file:** if the assistant helping with this project has no memory of
prior conversations, reading this file plus the source code should be enough to resume
work without re-litigating settled decisions. Keep it current. Update the Status
section at the end of each working session.

---

## 1. What this is

An **AI-Powered Credit Risk Analyst Assistant**. A credit analyst enters an
applicant profile; the system returns an approve / refer / decline decision, a risk
score, a written memo explaining the decision, and citations to the internal policy
manual that justify it.

Built by KasoReaper as a portfolio project demonstrating **banking domain + AI +
decision support**. Target build time was ~5 hours. Developed in VS Code.

## 2. Architecture — and the one rule that matters

```
policies.md ──> MarkdownHeaderTextSplitter ──> MiniLM embeddings ──> FAISS index
                                                                       │
applicant ──> scorer.py (deterministic rules) ──> findings ──> retrieval query
                     │                                                 │
                     └──────────> prompt + retrieved excerpts ──> Groq LLM ──> memo
                                                                       │
                                                              audit.py ──> SQLite
```

**The LLM never produces the risk score or the decision.** `scorer.py` does, from
deterministic rules. The LLM only writes prose explaining a decision it was handed,
citing policy text it was given. This is not a stylistic choice — it is the whole
point of the design. Any change that lets the model influence the outcome breaks the
auditability story and should be rejected.

Corollary: if a future session is asked to "make it smarter by letting the LLM
decide", push back and explain this before complying.

## 3. Files

| File | Role |
|---|---|
| `policies.md` | The RAG corpus. 10 synthetic policies, POL-001..POL-010, `##`-delimited. |
| `scorer.py` | `Applicant` dataclass + rule registry + `assess()`. Returns score, band, decision, findings. |
| `rag.py` | FAISS build/load, findings-driven retrieval, system prompt, `explain()`. |
| `app.py` | Streamlit UI. Two tabs: Assess (sidebar form → metrics → memo → policy expanders → scorecard trace → PD panel) and Audit log (browse past runs). |
| `model.py` | PD model on the Kaggle German Credit dataset. Second signal only, wired into the Assess tab's "Statistical signal" panel — degrades gracefully (caption, not crash) if `pd_model.joblib` isn't trained yet or scikit-learn isn't installed. |
| `audit.py` | Append-only SQLite log (`audit_log.db`, gitignored). Every assessment — inputs, findings, decision, PD estimate, cited policy codes, full memo — is written here via `log_assessment()`, browsable via `recent()`/`get()`. |
| `SETUP.md` | Environment setup from zero. |
| `requirements.txt` | Dependencies. |

## 4. Design decisions already made — do not redo these

- **FAISS, not Pinecone.** Local, zero setup, zero cost. Pinecone adds an account and
  network latency for no demo benefit at this scale (10 documents).
- **Scoring base is 50 points**, adjusted by rule points, clamped 0–100. Any rule
  returning ≤ −100 is a *hard fail*: score goes to 0, decision to DECLINE, regardless
  of other positives. Hard fails model policy floors that cannot be offset.
- **Bands:** ≥85 A / ≥70 B / ≥55 C (REFER) / else D (DECLINE).
- **Retrieval is keyed on triggered findings, not the raw profile.** Embedding
  "income 90000, score 735" retrieves nothing useful; numbers do not embed
  meaningfully. `retrieve()` builds the query from negative findings, then pins any
  policy code the scorecard cited that similarity search missed. This is the part
  that distinguishes the project from a tutorial.
- **EMI assumes 14% p.a. flat** for the DTI calculation. Hardcoded in
  `Applicant.emi()`. Fine for a demo; a real system would price by band per POL-009.
- **LLM provider is Groq (`openai/gpt-oss-120b`), not Anthropic.** This is a
  cost decision, not a quality one: the developer is a student with no budget for
  API credits, and Anthropic's API has no free tier. Groq's free tier has no card
  requirement and is generous enough for this project's call volume. Note:
  Groq deprecates models on a rolling schedule (`llama-3.3-70b-versatile` was
  shut down 2026-08-16 mid-build on this project) — if `explain()` throws a
  `model_not_found` / `model_decommissioned` error, check
  console.groq.com/docs/deprecations for the current recommended replacement
  before assuming anything else is broken. `rag.py` imports `ChatGroq`; the key
  lives in `.env` as `GROQ_API_KEY`. Do not "fix" this back to Anthropic without
  checking whether the budget constraint still holds — it's a real constraint,
  not a placeholder to clean up later. A fully local, zero-signup fallback
  (Ollama) is documented in `SETUP.md` if even Groq's free tier becomes a
  problem.
- **Fair lending is enforced in two places.** The system prompt forbids citing
  protected attributes (POL-008), and `model.py` drops `Sex` before training. Both
  are deliberate and should be pointed at during any demo.

## 5. The dataset question — settled

Kaggle `kabure/german-credit-data-with-risk`. Columns: Age, Sex, Job, Housing,
Saving accounts, Checking account, Credit amount, Duration, Purpose, Risk.
1000 rows, 1994 German retail loans, amounts in Deutsche Marks.

**It has no income, no credit score, no existing-liabilities field** — the three
inputs the scorecard runs on. So it cannot drive `scorer.py` and cannot generate
honest demo applicants.

It is used only in `model.py`, as an independent statistical PD signal shown
*alongside* the policy decision, with divergence flagged for human referral. The
`amount / 25` scaling in the UI wiring is a crude DM bridge to get rupee inputs
inside the training distribution — it is a demo hack, not a currency conversion, and
should be described as such rather than defended.

Expected holdout AUC 0.74–0.78. Quote AUC, not accuracy: the class split is ~70/30,
so 70% accuracy is the trivial baseline.

## 6. Known weaknesses — be honest about these, do not paper over them

- Policies are **synthetic**, written for the demo. They read like a real manual but
  are not sourced from RBI master directions or any real bank's manual.
- 10 policy chunks is far below the scale where retrieval quality is actually tested.
- The PD model transfers poorly: 1994 German data, different currency, different
  credit culture. Directional only.
- No auth. Every session shares the same local SQLite file; there's no per-user
  separation or access control on the audit log.
- Retrieval is plain similarity search — no reranking, no hybrid BM25.

If asked to present this as production-ready, decline and explain the above.

## 7. Backlog, roughly in value order

1. Batch mode — CSV upload, one memo per row, export to Excel.
2. Second corpus of real RBI master directions, retrieved separately from internal
   policy, with the memo distinguishing regulation from bank policy.
3. Hybrid retrieval (BM25 + dense) — matters once the corpus exceeds ~100 chunks.
4. Reranking with a cross-encoder.
5. Risk-based pricing output per POL-009 rather than the flat 14%.

## 8. Status log

> Update this at the end of each session. Newest entry on top.

- **[in progress]** Wired `model.py`'s PD signal into `app.py` (new sidebar
  inputs for Housing/Savings/Checking/Purpose, "Statistical signal" panel,
  graceful fallback if untrained). Added `audit.py` — append-only SQLite log,
  every assessment persisted, new "Audit log" tab in `app.py` to browse past
  runs. Updated README/CONTEXT to match. **Not yet tested locally** — next
  step: run all four demo profiles from the table above, confirm the PD panel
  either shows a real number (if `pd_model.joblib` exists) or fails gracefully
  (if not), and confirm the Audit log tab lists each run after Assess. Then
  commit and push.
- **[done]** Groq auth fixed, `llama-3.3-70b-versatile` swapped for
  `openai/gpt-oss-120b` after Groq deprecated the former (2026-08-16).
  Confirmed working end to end: DTI-decline case returns DECLINE/band D with
  POL-001 cited as principal reason. Pushed to GitHub at
  github.com/Arunim-Gogoi/Credit_Risk_Assesment.
- **[done]** Scaffold delivered: `policies.md`, `scorer.py`, `rag.py`, `app.py`,
  `model.py`, `SETUP.md`, `requirements.txt`.
