# Credit Risk Analyst Assistant

```bash
pip install streamlit langchain langchain-community langchain-anthropic \
            langchain-huggingface langchain-text-splitters \
            faiss-cpu sentence-transformers
export ANTHROPIC_API_KEY=sk-...
streamlit run app.py
```

First run downloads the MiniLM embedding model (~90 MB) and builds `faiss_index/`.
Delete that folder after editing `policies.md`, or call `build_index(force=True)`.

## Architecture

```
policies.md ──> MarkdownHeaderTextSplitter ──> MiniLM embeddings ──> FAISS
                                                                      │
applicant ──> scorer.py (deterministic rules) ──> findings ──> retrieval query
                                    │                                 │
                                    └──────> prompt + excerpts ──> Claude ──> memo
```

The score is never produced by the LLM. The LLM only explains a scorecard result and
cites retrieved policy. This is the point of the design: an auditable decision with a
narrative layer on top, not a model that decides.

## Demo profiles

| Case | Income | Debt | Amount | Score | Emp mo | Expected |
|---|---|---|---|---|---|---|
| Clean approve | 150000 | 10000 | 600000 | 800 | 60 | A / APPROVE |
| Thin file refer | 70000 | 15000 | 700000 | 690 | 14 | C / REFER |
| DTI decline | 50000 | 20000 | 900000 | 760 | 40 | D / DECLINE (POL-001) |
| Delinquency decline | 200000 | 5000 | 400000 | 720 | 80 | D / DECLINE (POL-005) |

## If time remains
- Batch mode: CSV upload, one memo per row, export to Excel
- Add real source documents (RBI master directions) as a second collection
- Log every decision to SQLite for the audit trail
