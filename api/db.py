"""Everything the API asks the database. It reads ONLY schema `serving` (sql/06_serving/).

Connection settings come from the standard Postgres environment variables (PGHOST, PGPORT, PGUSER,
PGPASSWORD, PGDATABASE) — no password in code. A small pool keeps a few connections open and reuses them:
opening a new connection per request would cost tens of milliseconds.
Every query passes user text as a PARAMETER (%s), never pasted into the SQL string — no SQL injection.
"""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

pool = ConnectionPool(conninfo="", min_size=1, max_size=4, open=False, kwargs={"row_factory": dict_row})

INPUTS = ["product_id", "sub_product_id", "issue_id", "state_id", "is_older_american", "is_servicemember",
          "company_no_history", "company_issue_no_history", "company_issue_rate_s", "company_rate_s",
          "issue_rate_s", "product_rate_s", "company_untimely_rate", "company_share_90d",
          "company_issue_share_90d", "issue_share_90d", "company_trend_90d", "issue_trend_90d",
          "company_quiet_days"]                       # v_model_input order (the model's 19 inputs, v3)


class NotFound(ValueError):
    """A name the data doesn't know -> the API answers 422 with the valid choices."""


def resolve(conn, company: str, product: str, sub_product: str, issue: str, state: str | None):
    """Names -> ids. Unknown company = a company with no history (allowed); anything else unknown = an error."""
    notes = []
    p = conn.execute("SELECT product_id FROM serving.product WHERE lower(product_name) = lower(%s)",
                     (product,)).fetchone()
    if not p:
        names = [r["product_name"] for r in conn.execute("SELECT product_name FROM serving.product ORDER BY 1")]
        raise NotFound(f"unknown product {product!r}; choose one of {names}")
    sp = conn.execute("SELECT sub_product_id FROM serving.sub_product WHERE product_id = %s "
                      "AND lower(sub_product_name) = lower(%s)", (p["product_id"], sub_product)).fetchone()
    if not sp:
        names = [r["sub_product_name"] for r in conn.execute(
            "SELECT sub_product_name FROM serving.sub_product WHERE product_id = %s ORDER BY 1", (p["product_id"],))]
        raise NotFound(f"unknown sub_product {sub_product!r} for product {product!r}; choose one of {names}")
    i = conn.execute("SELECT issue_id FROM serving.issue WHERE lower(issue_name) = lower(%s)", (issue,)).fetchone()
    if not i:
        raise NotFound(f"unknown issue {issue!r}; see GET /options/issues")
    s = conn.execute("SELECT state_id FROM serving.state WHERE upper(state_code) = upper(%s)",
                     (state or "(not specified)",)).fetchone()
    if not s:
        raise NotFound(f"unknown state {state!r}; use a 2-letter code (see GET /options/states) or leave it empty")
    c = conn.execute("SELECT company_id, company_name FROM serving.company WHERE lower(company_name) = lower(%s)",
                     (company,)).fetchone()
    if not c:
        similar = [r["company_name"] for r in conn.execute(
            "SELECT company_name FROM serving.company WHERE company_name ILIKE %s ORDER BY 1 LIMIT 5",
            (f"%{company.split()[0] if company.split() else company}%",))]
        notes.append(f"company {company!r} is not in the data: scored as a company with no track record"
                     + (f" (did you mean one of {similar}?)" if similar else ""))
    return {"company_id": c["company_id"] if c else None, "product_id": p["product_id"],
            "sub_product_id": sp["sub_product_id"], "issue_id": i["issue_id"], "state_id": s["state_id"]}, notes


def model_input(conn, ids: dict, older: bool, servicemember: bool) -> dict:
    """The 19 inputs, computed by SQL from the end-2024 snapshot (serving.model_input — skew-tested)."""
    row = conn.execute("SELECT * FROM serving.model_input(%s, %s, %s, %s, %s, %s, %s)",
                       (ids["company_id"], ids["product_id"], ids["sub_product_id"], ids["issue_id"],
                        ids["state_id"], int(older), int(servicemember))).fetchone()
    return {k: row[k] for k in INPUTS}


def clean(conn, text: str) -> str:
    """Typed text is cleaned by the SAME SQL function as the training text (serving.clean_narrative)."""
    return conn.execute("SELECT serving.clean_narrative(%s) AS t", (text,)).fetchone()["t"]


def test_complaint(conn, complaint_id: int):
    return conn.execute("""
        SELECT t.*, c.company_name, p.product_name, sp.sub_product_name, i.issue_name, s.state_code
        FROM   serving.test_complaints t
        JOIN   serving.company c USING (company_id)
        JOIN   serving.product p USING (product_id)
        JOIN   serving.sub_product sp USING (sub_product_id)
        JOIN   serving.issue i USING (issue_id)
        JOIN   serving.state s USING (state_id)
        WHERE  t.complaint_id = %s""", (complaint_id,)).fetchone()


def random_test_complaint(conn, paid: bool | None) -> int:
    row = conn.execute("SELECT complaint_id FROM serving.test_complaints "
                       "WHERE %(p)s::boolean IS NULL OR paid = (%(p)s::boolean)::int "
                       "ORDER BY random() LIMIT 1", {"p": paid}).fetchone()
    return row["complaint_id"]


def snapshot_day(conn):
    return conn.execute("SELECT max(as_of) AS d FROM serving.snap_national").fetchone()["d"]


def options(conn, what: str, search: str | None = None):
    if what == "products":
        rows = conn.execute("""SELECT p.product_name, array_agg(sp.sub_product_name ORDER BY sp.sub_product_name) AS subs
                               FROM serving.product p JOIN serving.sub_product sp USING (product_id)
                               GROUP BY p.product_name ORDER BY 1""").fetchall()
        return [{"product": r["product_name"], "sub_products": r["subs"]} for r in rows]
    if what == "issues":
        return [r["issue_name"] for r in conn.execute("SELECT issue_name FROM serving.issue ORDER BY 1")]
    if what == "states":
        return [r["state_code"] for r in conn.execute("SELECT state_code FROM serving.state ORDER BY 1")]
    if what == "companies":
        return [r["company_name"] for r in conn.execute(
            "SELECT company_name FROM serving.company WHERE company_name ILIKE %s ORDER BY 1 LIMIT 25",
            (f"%{search}%",))]
