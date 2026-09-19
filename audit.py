"""Append-only audit log. Every assessment is recorded, never mutated.
This is what makes the 'auditable' claim in the README actually true."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "audit_log.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    applicant_name TEXT,
    decision TEXT NOT NULL,
    band TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    dti REAL,
    pd_estimate REAL,
    reconciliation TEXT,
    policy_codes_cited TEXT NOT NULL,
    memo TEXT NOT NULL,
    full_assessment_json TEXT NOT NULL
);
"""


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


def log_assessment(assessment: dict, memo: str, docs, pd_result: dict | None = None,
                    reconciliation: str | None = None) -> int:
    codes = sorted({d.metadata.get("policy", d.metadata.get("code", "")) for d in docs})
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO assessments
               (ts_utc, applicant_name, decision, band, risk_score, dti,
                pd_estimate, reconciliation, policy_codes_cited, memo, full_assessment_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                assessment["applicant"]["name"],
                assessment["decision"],
                assessment["band"],
                assessment["risk_score"],
                assessment["metrics"]["dti"],
                pd_result["pd"] if pd_result else None,
                reconciliation,
                json.dumps(codes),
                memo,
                json.dumps(assessment),
            ),
        )
        return cur.lastrowid


def recent(limit: int = 20) -> list[dict]:
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, ts_utc, applicant_name, decision, band, risk_score, dti, "
            "pd_estimate, reconciliation, policy_codes_cited FROM assessments "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get(assessment_id: int) -> dict | None:
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
        return dict(row) if row else None
