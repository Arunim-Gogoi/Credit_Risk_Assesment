"""
Statistical PD model trained on the German Credit dataset (Kaggle: kabure).

    kaggle datasets download -d kabure/german-credit-data-with-risk -p data --unzip

Scope note: this dataset has no income, credit score, or existing-liability fields,
so it CANNOT drive the policy scorecard. It produces an independent probability of
default from the features it does have. The two signals are compared, never merged.

Fair lending: `Sex` is dropped before training (POL-008). This is deliberate and is
surfaced in the UI. Do not re-add it for an AUC bump.
"""
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE = Path(__file__).parent
CSV = BASE / "data" / "german_credit_data.csv"
MODEL_PATH = BASE / "pd_model.joblib"

EXCLUDED = ["Sex"]                       # protected attribute, POL-008
NUMERIC = ["Age", "Credit amount", "Duration", "Job"]
CATEGORICAL = ["Housing", "Saving accounts", "Checking account", "Purpose"]
FEATURES = NUMERIC + CATEGORICAL


def load() -> pd.DataFrame:
    df = pd.read_csv(CSV, index_col=0)
    df = df.drop(columns=[c for c in EXCLUDED if c in df.columns])
    # "Risk": good -> 0 (repaid), bad -> 1 (default). We predict P(bad).
    df["target"] = (df["Risk"].str.strip().str.lower() == "bad").astype(int)
    return df


def _pipeline(estimator):
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                          ("sc", StandardScaler())]), NUMERIC),
        ("cat", Pipeline([("imp", SimpleImputer(strategy="constant", fill_value="not_known")),
                          ("oh", OneHotEncoder(handle_unknown="ignore"))]), CATEGORICAL),
    ])
    return Pipeline([("pre", pre), ("clf", estimator)])


def train(seed: int = 42):
    df = load()
    X, y = df[FEATURES], df["target"]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, stratify=y, random_state=seed)

    candidates = {
        "logistic": _pipeline(LogisticRegression(max_iter=2000, class_weight="balanced")),
        "hgb": _pipeline(HistGradientBoostingClassifier(
            max_depth=4, learning_rate=0.06, max_iter=300, random_state=seed)),
    }

    report, best, best_auc = {}, None, -1.0
    for name, pipe in candidates.items():
        cal = CalibratedClassifierCV(pipe, method="isotonic", cv=5)
        cal.fit(Xtr, ytr)
        p = cal.predict_proba(Xte)[:, 1]
        auc, brier = roc_auc_score(yte, p), brier_score_loss(yte, p)
        report[name] = {"auc": round(auc, 3), "brier": round(brier, 3)}
        if auc > best_auc:
            best, best_auc, best_name = cal, auc, name

    base_rate = float(y.mean())
    joblib.dump({"model": best, "features": FEATURES, "base_rate": base_rate,
                 "excluded": EXCLUDED, "report": report, "chosen": best_name}, MODEL_PATH)
    return report, best_name, base_rate


_cache = None


def predict_pd(profile: dict) -> dict:
    """profile keys: Age, Credit amount, Duration, Job, Housing,
    Saving accounts, Checking account, Purpose"""
    global _cache
    if _cache is None:
        _cache = joblib.load(MODEL_PATH)
    row = pd.DataFrame([{k: profile.get(k) for k in _cache["features"]}])
    pd_hat = float(_cache["model"].predict_proba(row)[0, 1])
    base = _cache["base_rate"]
    return {
        "pd": round(pd_hat, 4),
        "lift_vs_book": round(pd_hat / base, 2),
        "book_base_rate": round(base, 4),
        "model": _cache["chosen"],
        "holdout": _cache["report"][_cache["chosen"]],
        "excluded_features": _cache["excluded"],
        "caveat": "Trained on 1000 German retail loans (1994, DM). Directional only; "
                  "not calibrated to the current Indian retail book.",
    }


def reconcile(assessment: dict, pd_result: dict) -> dict:
    """Flag where the rules engine and the statistical model disagree."""
    rules_says_ok = assessment["decision"] == "APPROVE"
    model_says_risky = pd_result["pd"] > 0.40
    if rules_says_ok and model_says_risky:
        verdict = "DIVERGENCE: policy approves, model flags elevated default risk. Refer."
    elif not rules_says_ok and pd_result["pd"] < 0.15:
        verdict = "DIVERGENCE: policy declines, model sees low risk. Policy prevails; note for review."
    else:
        verdict = "Aligned: model and policy engine point the same direction."
    return {"verdict": verdict, "pd": pd_result["pd"], "decision": assessment["decision"]}


if __name__ == "__main__":
    report, chosen, base = train()
    print(f"base default rate: {base:.1%}")
    for k, v in report.items():
        print(f"  {k:10s} AUC {v['auc']}  Brier {v['brier']}")
    print(f"chosen: {chosen}  -> {MODEL_PATH}")
