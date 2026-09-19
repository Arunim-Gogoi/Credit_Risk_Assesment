"""Two FAISS indices: internal bank policy and external RBI regulation, kept
separate and retrieved separately so the memo can distinguish 'the regulator
requires this' from 'the bank's own policy adds this on top.'"""
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

BASE = Path(__file__).parent
EMBED = "sentence-transformers/all-MiniLM-L6-v2"

# Internal policy codes that have a clear regulatory basis worth surfacing
# alongside them. Not exhaustive — only where the mapping is genuinely direct.
RBI_MAPPING = {
    "POL-005": ["RBI-004"],   # delinquency hard-fail <-> IRAC 90-day NPA norm
    "POL-006": ["RBI-003"],   # exposure cap <-> risk weights on unsecured credit
    "POL-007": ["RBI-005"],   # KYC docs <-> KYC Master Direction
    "POL-009": ["RBI-007"],   # pricing/EMI <-> interest-from-disbursement rule
}
# Always surfaced: every decision needs a written specific reason under the
# Fair Practices Code, regardless of which internal policy drove it.
ALWAYS_CITE_RBI = {"RBI-001"}


def _embeddings():
    return HuggingFaceEmbeddings(model_name=EMBED)


def _build(md_filename: str, index_dirname: str, force: bool = False) -> FAISS:
    emb = _embeddings()
    index_dir = BASE / index_dirname
    if index_dir.exists() and not force:
        return FAISS.load_local(str(index_dir), emb, allow_dangerous_deserialization=True)

    text = (BASE / md_filename).read_text()
    splitter = MarkdownHeaderTextSplitter([("##", "policy")])
    docs = splitter.split_text(text)
    for d in docs:
        header = d.metadata.get("policy", "")
        d.metadata["code"] = header.split()[0] if header else "UNKNOWN"
        d.page_content = f"{header}\n{d.page_content}"

    store = FAISS.from_documents(docs, emb)
    store.save_local(str(index_dir))
    return store


def build_index(force: bool = False) -> FAISS:
    """Internal bank policy manual (POL-xxx)."""
    return _build("policies.md", "faiss_index", force)


def build_rbi_index(force: bool = False) -> FAISS:
    """External RBI regulatory reference (RBI-xxx)."""
    return _build("policies_rbi.md", "faiss_index_rbi", force)


def retrieve(store: FAISS, assessment: dict, k: int = 4):
    """Internal policy retrieval, keyed on triggered findings, not the raw profile."""
    query = " ".join(f["finding"] for f in assessment["findings"] if f["points"] < 0) \
        or "standard approval criteria for retail lending"
    hits = store.similarity_search(query, k=k)

    cited = {f["policy"] for f in assessment["findings"] if f["points"] < 0}
    have = {h.metadata.get("code") for h in hits}
    for code in cited - have:
        hits += store.similarity_search(code, k=1)
    return hits


def retrieve_regulatory(rbi_store: FAISS, assessment: dict, k: int = 3):
    """RBI retrieval: always pins the Fair Practices Code, plus whichever
    regulations map to the internal policy codes actually triggered."""
    query = " ".join(f["finding"] for f in assessment["findings"] if f["points"] < 0) \
        or "standard lending compliance"
    hits = rbi_store.similarity_search(query, k=k)

    cited = set(ALWAYS_CITE_RBI)
    for f in assessment["findings"]:
        if f["points"] < 0:
            cited.update(RBI_MAPPING.get(f["policy"], []))
    have = {h.metadata.get("code") for h in hits}
    for code in cited - have:
        hits += rbi_store.similarity_search(code, k=1)
    return hits


SYSTEM = """You are a credit risk analyst assistant at a retail bank in India.

You are given (1) a deterministic scorecard result, (2) excerpts from the bank's
internal policy manual (codes POL-xxx), and (3) excerpts from RBI regulatory
reference material (codes RBI-xxx). Write the analyst's decision memo.

Hard rules:
- Never change the decision or the risk score. Explain the one you were given.
- Every substantive claim must cite a code in brackets, e.g. [POL-001] or [RBI-004].
- Keep the two sources distinct: a POL-xxx citation means "this is the bank's own
  underwriting rule." An RBI-xxx citation means "this is a regulatory requirement
  or constraint, not a bank choice." Never blend them into one undifferentiated
  citation, and never present a bank policy as if RBI mandates that specific
  number or threshold — RBI sets floors/frameworks; the bank's policy is usually
  stricter or more specific on top of that floor.
- If a claim is not supported by the excerpts, do not make it.
- Never reference age, gender, religion, caste, region, or marital status as a
  reason, even if present in the profile (POL-008), except the objective
  age-at-maturity limit in POL-010.
- Every memo — approve, refer, or decline — must include a REGULATORY BASIS line
  citing RBI-001, since the Fair Practices Code requires a specific written
  reason regardless of outcome.
- State the single principal reason for a decline first and plainly.

Format:
DECISION: <one line>
PRINCIPAL REASON: <one sentence>
ANALYSIS: <3-5 bullets, each with a citation>
REGULATORY BASIS: <1-2 bullets, RBI-xxx citations only>
CONDITIONS / NEXT STEPS: <bullets, or "None">
"""

PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("human", "SCORECARD RESULT:\n{assessment}\n\n"
              "INTERNAL POLICY EXCERPTS:\n{context}\n\n"
              "RBI REGULATORY EXCERPTS:\n{rbi_context}"),
])


def explain(assessment: dict, docs, rbi_docs) -> str:
    # Free tier: https://console.groq.com — no card required at signup.
    # llama-3.3-70b-versatile was deprecated by Groq on 2026-08-16;
    # gpt-oss-120b is their recommended replacement, similar quality/cost.
    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0,
        max_tokens=1400,
        api_key=os.environ["GROQ_API_KEY"],
    )
    context = "\n\n---\n\n".join(d.page_content for d in docs)
    rbi_context = "\n\n---\n\n".join(d.page_content for d in rbi_docs)
    import json
    slim = {k: v for k, v in assessment.items() if k != "applicant"}
    chain = PROMPT | llm
    return chain.invoke({
        "assessment": json.dumps(slim, indent=2),
        "context": context,
        "rbi_context": rbi_context,
    }).content
