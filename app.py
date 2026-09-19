import json

import streamlit as st

from scorer import Applicant, assess
from rag import build_index, retrieve, explain

try:
    from model import predict_pd, reconcile
    PD_AVAILABLE = True
except Exception:
    PD_AVAILABLE = False

from audit import log_assessment, recent, get as get_logged

st.set_page_config(page_title="Credit Risk Analyst Assistant", layout="wide")


@st.cache_resource
def store():
    return build_index()


st.title("Credit Risk Analyst Assistant")
st.caption("Deterministic scorecard + RAG over the internal policy manual. Decision support, not decision authority.")

tab_assess, tab_audit = st.tabs(["Assess", "Audit log"])

with st.sidebar:
    st.header("Applicant profile")
    name = st.text_input("Name", "Applicant A")
    age = st.number_input("Age", 21, 75, 34)
    income = st.number_input("Gross monthly income (INR)", 0, 10_000_000, 90_000, step=5_000)
    debt = st.number_input("Existing monthly obligations (INR)", 0, 10_000_000, 18_000, step=1_000)
    amount = st.number_input("Requested amount (INR)", 10_000, 50_000_000, 800_000, step=50_000)
    tenure = st.slider("Tenure (months)", 6, 84, 48)
    score = st.slider("Bureau score", 300, 900, 735)
    emp_type = st.selectbox("Employment type", ["salaried", "self_employed"])
    emp_months = st.number_input("Months in current employment", 0, 600, 30)
    collateral = st.number_input("Collateral value (INR, 0 if unsecured)", 0, 100_000_000, 0, step=50_000)
    dpd90 = st.checkbox("Currently 90+ DPD")
    dpd30 = st.checkbox("30-59 DPD in last 12 months")
    st.divider()
    st.caption("Optional — feeds the statistical PD model, not the policy scorecard")
    housing = st.selectbox("Housing", ["own", "rent", "free"], disabled=not PD_AVAILABLE)
    saving = st.selectbox("Savings account level",
                           ["little", "moderate", "quite rich", "rich"], disabled=not PD_AVAILABLE)
    checking = st.selectbox("Checking account level",
                             ["little", "moderate", "rich"], disabled=not PD_AVAILABLE)
    purpose = st.selectbox("Loan purpose",
                            ["car", "furniture/equipment", "radio/TV", "education",
                             "business", "repairs", "vacation/others"], disabled=not PD_AVAILABLE)
    go = st.button("Assess", type="primary", use_container_width=True)

with tab_assess:
    if go:
        a = Applicant(name, age, income, debt, amount, tenure, score, emp_months,
                      emp_type, collateral, dpd90, dpd30)
        result = assess(a)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Risk score", result["risk_score"])
        c2.metric("Band", result["band"])
        c3.metric("Decision", result["decision"])
        c4.metric("DTI", f"{result['metrics']['dti']:.0%}")

        left, right = st.columns([3, 2])

        with left:
            st.subheader("Analyst memo")
            with st.spinner("Retrieving policy and drafting..."):
                docs = retrieve(store(), result)
                memo = explain(result, docs)
                st.markdown(memo)

            st.subheader("Policy references")
            for d in docs:
                with st.expander(d.metadata.get("policy", d.metadata.get("code", "Policy"))):
                    st.text(d.page_content)

        pd_res, rec = None, None
        with right:
            st.subheader("Scorecard trace")
            st.dataframe(
                [{"Policy": f["policy"], "Pts": f["points"], "Finding": f["finding"]}
                 for f in result["findings"]],
                hide_index=True, use_container_width=True,
            )
            st.caption("Estimated EMI at 14% p.a.: INR " + f"{result['metrics']['emi']:,}")
            with st.expander("Raw assessment JSON"):
                st.json(result)

            st.subheader("Statistical signal (secondary)")
            if not PD_AVAILABLE:
                st.caption("model.py not importable — scikit-learn/pandas/joblib not installed.")
            else:
                try:
                    pd_res = predict_pd({
                        "Age": age,
                        "Credit amount": amount / 25,   # crude INR->DM scale bridge for demo purposes
                        "Duration": tenure,
                        "Job": 2,
                        "Housing": housing,
                        "Saving accounts": saving,
                        "Checking account": checking,
                        "Purpose": purpose,
                    })
                    rec = reconcile(result, pd_res)
                    st.metric("Model PD", f"{pd_res['pd']:.1%}", f"{pd_res['lift_vs_book']}x book rate")
                    st.caption(
                        f"Holdout AUC {pd_res['holdout']['auc']} · trained on German Credit (1994, DM) · "
                        f"excludes {', '.join(pd_res['excluded_features'])} per POL-008 · directional only."
                    )
                    if "DIVERGENCE" in rec["verdict"]:
                        st.warning(rec["verdict"])
                    else:
                        st.success(rec["verdict"])
                except FileNotFoundError:
                    st.caption("pd_model.joblib not found — run `python model.py` after placing the "
                               "German Credit CSV in data/. See CONTEXT.md §5.")

        row_id = log_assessment(result, memo, docs, pd_res,
                                 rec["verdict"] if rec else None)
        st.caption(f"Logged as audit record #{row_id}.")
    else:
        st.info("Fill the profile on the left and press Assess.")

with tab_audit:
    st.subheader("Past assessments")
    rows = recent(50)
    if not rows:
        st.caption("No assessments logged yet.")
    else:
        st.dataframe(rows, hide_index=True, use_container_width=True)
        pick = st.number_input("View full record by ID", min_value=1,
                                value=rows[0]["id"], step=1)
        if st.button("Load record"):
            record = get_logged(pick)
            if record:
                st.markdown(record["memo"])
                with st.expander("Full assessment JSON"):
                    st.json(json.loads(record["full_assessment_json"]))
            else:
                st.warning("No record with that ID.")
