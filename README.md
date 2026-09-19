# Credit Risk Analyst Assistant

RAG-powered credit risk decision support: a deterministic scorecard decides,
an LLM explains and cites the policy manual that backs each claim.

> Full setup from zero (VS Code, Windows/macOS/Linux): see `SETUP.md`.
> Needs a free Groq API key (console.groq.com, no card required) in a local
> `.env` file — not included in this repo.

```bash
pip install -r requirements.txt
# .env (create this yourself, not committed):
#   GROQ_API_KEY=gsk_...
streamlit run app.py
```

First run downloads the MiniLM embedding model (~90 MB) and builds `faiss_index/`.
Delete that folder after editing `policies.md`, or call `build_index(force=True)`.

## Architecture

```
policies.md ──> MarkdownHeaderTextSplitter ──> MiniLM embeddings ──> FAISS
                                                                       │
applicant ──> scorer.py (deterministic rules) ──> findings ──> retrieval query
                     │                                                 │
                     └──────────> prompt + retrieved excerpts ──> Groq LLM ──> memo
```

The score is never produced by the LLM. The LLM only explains a scorecard result and
cites retrieved policy. This is the point of the design: an auditable decision with a
narrative layer on top, not a model that decides.

LLM calls run on Groq's free tier (`openai/gpt-oss-120b`), not a paid provider —
a deliberate choice to keep this project runnable at zero cost. See `CONTEXT.md`
for why, and for what to do if Groq deprecates that model (they do this on a
rolling schedule — check console.groq.com/docs/deprecations first).

## Demo profiles

| Case | Income | Debt | Amount | Score | Emp mo | Expected |
|---|---|---|---|---|---|---|
| Clean approve | 150000 | 10000 | 600000 | 800 | 60 | A / APPROVE |
| Thin file refer | 70000 | 15000 | 700000 | 690 | 14 | C / REFER |
| DTI decline | 50000 | 20000 | 900000 | 760 | 40 | D / DECLINE (POL-001) |
| Delinquency decline | 200000 | 5000 | 400000 | 720 | 80 | D / DECLINE (POL-005) |

## Optional: statistical PD model

`model.py` trains a probability-of-default model on the Kaggle German Credit
dataset as a *second, independent* signal shown alongside the policy decision —
it does not feed the scorecard (that dataset has no income/credit-score/liability
fields) and it does not replace the rules engine. See `CONTEXT.md` §5 for scope
and caveats before using it. Not yet wired into `app.py`.

## If time remains
- Batch mode: CSV upload, one memo per row, export to Excel
- Add real source documents (RBI master directions) as a second collection
- Log every decision to SQLite for the audit trail
