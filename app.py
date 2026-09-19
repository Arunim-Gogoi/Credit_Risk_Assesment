import streamlit as st

from scorer import Applicant, assess
from rag import build_index, retrieve, explain

st.set_page_config(page_title="Credit Risk Analyst Assistant", layout="wide")


@st.cache_resource
def store():
    return build_index()


st.title("Credit Risk Analyst Assistant")
st.caption("Deterministic scorecard + RAG over the internal policy manual. Decision support, not decision authority.")

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
    go = st.button("Assess", type="primary", use_container_width=True)

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
            st.markdown(explain(result, docs))

        st.subheader("Policy references")
        for d in docs:
            with st.expander(d.metadata.get("policy", d.metadata.get("code", "Policy"))):
                st.text(d.page_content)

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
else:
    st.info("Fill the profile on the left and press Assess.")
