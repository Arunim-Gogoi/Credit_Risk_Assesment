"""Deterministic scorecard. The LLM explains this output; it never produces it."""
from dataclasses import dataclass, asdict


@dataclass
class Applicant:
    name: str
    age: int
    gross_monthly_income: float
    existing_monthly_debt: float
    requested_amount: float
    tenure_months: int
    credit_score: int
    employment_months: int
    employment_type: str          # "salaried" | "self_employed"
    collateral_value: float = 0.0
    dpd_90_plus: bool = False
    dpd_30_59_last_12m: bool = False

    def emi(self, annual_rate: float = 0.14) -> float:
        r = annual_rate / 12
        n = self.tenure_months
        return self.requested_amount * r * (1 + r) ** n / ((1 + r) ** n - 1)

    def dti(self) -> float:
        return (self.existing_monthly_debt + self.emi()) / self.gross_monthly_income

    def ltv(self) -> float:
        return self.requested_amount / self.collateral_value if self.collateral_value else 0.0


RULES = []


def rule(code, description):
    def wrap(fn):
        RULES.append((code, description, fn))
        return fn
    return wrap


# Each rule returns (points, triggered_message) or None.
@rule("POL-005", "Existing delinquency")
def _delinquency(a: Applicant):
    if a.dpd_90_plus:
        return (-100, "Account currently 90+ days past due.")
    if a.dpd_30_59_last_12m:
        return (-25, "30-59 DPD recorded in the last 12 months.")
    return (10, "No adverse repayment history in the last 12 months.")


@rule("POL-002", "Minimum credit score")
def _score(a: Applicant):
    s = a.credit_score
    if s < 650:
        return (-100, f"Bureau score {s} is below the unsecured floor of 650.")
    if s < 700:
        return (-20, f"Bureau score {s} is in the conditional 650-699 band.")
    if s < 780:
        return (15, f"Bureau score {s} meets the standard threshold.")
    return (30, f"Bureau score {s} is in the top band.")


@rule("POL-001", "Debt-to-income")
def _dti(a: Applicant):
    d = a.dti()
    if d > 0.50:
        return (-100, f"DTI of {d:.0%} exceeds the 50% hard ceiling.")
    if d > 0.40:
        return (-15, f"DTI of {d:.0%} falls in the 40-50% band needing a compensating factor.")
    if d > 0.30:
        return (10, f"DTI of {d:.0%} is acceptable but above the 30% preferred band.")
    return (25, f"DTI of {d:.0%} is comfortably within policy.")


@rule("POL-003", "Employment stability")
def _employment(a: Applicant):
    if a.employment_type == "salaried" and a.employment_months < 12:
        return (-30, f"Only {a.employment_months} months with current employer, below the 12-month minimum.")
    return (15, f"{a.employment_months} months of employment tenure meets policy.")


@rule("POL-010", "Age and tenure limits")
def _age(a: Applicant):
    age_at_maturity = a.age + a.tenure_months / 12
    cap = 65 if a.employment_type == "salaried" else 70
    if age_at_maturity > cap:
        return (-100, f"Age at maturity {age_at_maturity:.0f} exceeds the {cap}-year limit.")
    if a.tenure_months > 60:
        return (-100, f"Requested tenure of {a.tenure_months} months exceeds the 60-month cap.")
    return (5, "Age and tenure within policy limits.")


@rule("POL-006", "Exposure cap")
def _exposure(a: Applicant):
    if a.collateral_value == 0 and a.requested_amount > 2_500_000:
        return (-100, "Unsecured request exceeds the INR 25,00,000 single-borrower cap.")
    return (5, "Requested exposure within single-borrower limits.")


@rule("POL-004", "Loan to value")
def _ltv(a: Applicant):
    if not a.collateral_value:
        return None
    v = a.ltv()
    if v > 0.80:
        return (-40, f"LTV of {v:.0%} exceeds the 80% residential ceiling.")
    return (15, f"LTV of {v:.0%} is within policy.")


def assess(a: Applicant) -> dict:
    findings, total, hard_fail = [], 50, False
    for code, desc, fn in RULES:
        out = fn(a)
        if out is None:
            continue
        pts, msg = out
        if pts <= -100:
            hard_fail = True
        total += max(pts, -100)
        findings.append({"policy": code, "area": desc, "points": pts, "finding": msg})

    score = 0 if hard_fail else max(0, min(100, total))
    if hard_fail:
        band, decision = "D", "DECLINE"
    elif score >= 85:
        band, decision = "A", "APPROVE"
    elif score >= 70:
        band, decision = "B", "APPROVE"
    elif score >= 55:
        band, decision = "C", "REFER"
    else:
        band, decision = "D", "DECLINE"

    return {
        "risk_score": score,
        "band": band,
        "decision": decision,
        "hard_fail": hard_fail,
        "metrics": {"dti": round(a.dti(), 3), "emi": round(a.emi()), "ltv": round(a.ltv(), 3)},
        "findings": findings,
        "applicant": asdict(a),
    }
