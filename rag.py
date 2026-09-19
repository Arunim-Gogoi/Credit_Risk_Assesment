from dotenv import load_dotenv
load_dotenv()

"""FAISS index over policies.md + retrieval keyed to the triggered rules."""
import os
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

BASE = Path(__file__).parent
INDEX_DIR = BASE / "faiss_index"
EMBED = "sentence-transformers/all-MiniLM-L6-v2"


def _embeddings():
    return HuggingFaceEmbeddings(model_name=EMBED)


def build_index(force: bool = False) -> FAISS:
    emb = _embeddings()
    if INDEX_DIR.exists() and not force:
        return FAISS.load_local(str(INDEX_DIR), emb, allow_dangerous_deserialization=True)

    text = (BASE / "policies.md").read_text()
    splitter = MarkdownHeaderTextSplitter([("##", "policy")])
    docs = splitter.split_text(text)
    for d in docs:
        header = d.metadata.get("policy", "")
        d.metadata["code"] = header.split()[0] if header else "UNKNOWN"
        d.page_content = f"{header}\n{d.page_content}"

    store = FAISS.from_documents(docs, emb)
    store.save_local(str(INDEX_DIR))
    return store


def retrieve(store: FAISS, assessment: dict, k: int = 4):
    """Retrieve on the actual findings, not the raw applicant blob."""
    query = " ".join(f["finding"] for f in assessment["findings"] if f["points"] < 0) \
        or "standard approval criteria for retail lending"
    hits = store.similarity_search(query, k=k)

    # Always pin the policies the scorecard cited, so nothing is silently dropped.
    cited = {f["policy"] for f in assessment["findings"] if f["points"] < 0}
    have = {h.metadata.get("code") for h in hits}
    for code in cited - have:
        hits += store.similarity_search(code, k=1)
    return hits


SYSTEM = """You are a credit risk analyst assistant at a retail bank.

You are given (1) a deterministic scorecard result and (2) excerpts from the bank's
policy manual. Write the analyst's decision memo.

Hard rules:
- Never change the decision or the risk score. Explain the one you were given.
- Every substantive claim must cite a policy code in brackets, e.g. [POL-001].
- If a claim is not supported by the excerpts, do not make it.
- Never reference age, gender, religion, caste, region, or marital status as a
  reason, even if present in the profile (POL-008), except the objective
  age-at-maturity limit in POL-010.
- State the single principal reason for a decline first and plainly.

Format:
DECISION: <one line>
PRINCIPAL REASON: <one sentence>
ANALYSIS: <3-5 bullets, each with a citation>
CONDITIONS / NEXT STEPS: <bullets, or "None">
"""

PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("human", "SCORECARD RESULT:\n{assessment}\n\nPOLICY EXCERPTS:\n{context}"),
])


def explain(assessment: dict, docs) -> str:
    # Free tier: https://console.groq.com — no card required at signup.
    # llama-3.3-70b-versatile was deprecated by Groq on 2026-08-16;
    # gpt-oss-120b is their recommended replacement, similar quality/cost.
    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0,
        max_tokens=1200,
        api_key=os.environ["GROQ_API_KEY"],
    )
    context = "\n\n---\n\n".join(d.page_content for d in docs)
    import json
    slim = {k: v for k, v in assessment.items() if k != "applicant"}
    chain = PROMPT | llm
    return chain.invoke({"assessment": json.dumps(slim, indent=2), "context": context}).content
