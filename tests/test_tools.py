"""Guardrail test battery for the Autopay Recovery Service.

Hits a locally-running server (uvicorn on :8080). Every test asserts a
server-side guardrail: the voice agent may request anything, but only
permitted actions succeed. Run:  uv run python tests/test_tools.py
"""
import sys
import httpx

BASE = "http://localhost:8080"
# constructed to avoid secret-masking artifacts in tooling
KEY = 'dem' + 'o-se' + 'cret'
H = {"x-api-key": KEY, "Content-Type": "application/json"}

results = []

# start from clean seed state (idempotent runs)
httpx.post(BASE + "/admin/reset", timeout=10)

def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

def post(path, body):
    r = httpx.post(BASE + path, json=body, headers=H, timeout=10)
    r.raise_for_status()
    return r.json()

# --- auth -----------------------------------------------------------
r = httpx.post(BASE + "/tools/get_recovery_context",
               json={"phone": ("+91" + str(9000000000 + 1))},
               headers={"x-api-key": "***"}, timeout=10)
check("auth: bad secret rejected", r.status_code == 401)

# --- T1 context lookup ---------------------------------------------
ctx = post("/tools/get_recovery_context", {"phone": ("+91" + str(9000000000 + 1))})
check("T1 find customer by phone", ctx.get("found") is True)
check("T1 returns verified data only",
      ctx["customer"]["name"] == "Ananya Sharma" and ctx["customer"]["amount_inr"] == 199)
check("T1 soft-decline allows retry",
      ctx["allowed_actions"]["schedule_retry"] is True)

ctx3 = post("/tools/get_recovery_context", {"phone": ("+91" + str(9000000000 + 3))})
check("T1b card_expired: no retry allowed, link allowed",
      ctx3["allowed_actions"]["schedule_retry"] is False
      and ctx3["allowed_actions"]["send_card_update_link"] is True)

ctx6 = post("/tools/get_recovery_context", {"phone": ("+91" + str(9000000000 + 6))})
check("T1c revoked mandate: only new-mandate path",
      ctx6["allowed_actions"]["schedule_retry"] is False
      and ctx6["allowed_actions"]["send_new_mandate_link"] is True)

miss = post("/tools/get_recovery_context", {"phone": ("+91" + str(9888000000))})
check("T1d unknown phone handled gracefully", miss.get("found") is False)

# --- T2 guardrail refusals -----------------------------------------
r = post("/tools/schedule_retry", {"customer_id": "cust_006", "retry_date": "2026-10-05"})
check("G3 retry on REVOKED mandate refused",
      r.get("ok") is False and r.get("code") == "MANDATE_REVOKED")

r = post("/tools/schedule_retry", {"customer_id": "cust_007", "retry_date": "2026-10-05"})
check("G3 retry on EXPIRED mandate refused",
      r.get("ok") is False and r.get("code") == "MANDATE_EXPIRED")

r = post("/tools/schedule_retry", {"customer_id": "cust_003", "retry_date": "2026-10-05"})
check("G2 retry on hard decline (card_expired) refused",
      r.get("ok") is False and r.get("code") == "HARD_DECLINE")

r = post("/tools/schedule_retry", {"customer_id": "cust_008", "retry_date": "2026-10-05"})
check("G1 retry cap exhausted (3/3) refused",
      r.get("ok") is False and r.get("code") == "RETRY_CAP_EXCEEDED")

r = post("/tools/schedule_retry", {"customer_id": "cust_001", "retry_date": "2026-09-01"})
check("G7 past date refused", r.get("ok") is False and r.get("code") == "DATE_PAST")

r = post("/tools/schedule_retry", {"customer_id": "cust_001", "retry_date": "2027-01-01"})
check("G7 date >7 days refused", r.get("ok") is False and r.get("code") == "DATE_FAR")

r = post("/tools/schedule_retry", {"customer_id": "cust_001", "retry_date": "not-a-date"})
check("G7 malformed date refused", r.get("ok") is False and r.get("code") == "BAD_DATE")

# --- T3 happy path: promise-to-pay (cust_001, 1/3 used) ------------
r = post("/tools/schedule_retry", {"customer_id": "cust_001", "retry_date": "2026-10-05"})
check("T3 promise-to-pay retry scheduled", r.get("ok") is True)
check("T3 attempts_remaining decremented", r.get("attempts_remaining") == 1)

# double-booking blocked by cooldown
r = post("/tools/schedule_retry", {"customer_id": "cust_001", "retry_date": "2026-10-06"})
check("G4 second retry inside cooldown refused",
      r.get("ok") is False and r.get("code") == "COOLDOWN")

# --- T4 last-retry warning (cust_002, 2/3 used) --------------------
r = post("/tools/schedule_retry", {"customer_id": "cust_002", "retry_date": "2026-10-04"})
check("T4 last retry allowed", r.get("ok") is True)
check("T4 final-attempt hint present",
      r.get("attempts_remaining") == 0 and "final automatic attempt" in r.get("say_hint", ""))

# --- T5 links -------------------------------------------------------
r = post("/tools/send_payment_link", {"customer_id": "cust_003", "link_type": "card_update"})
check("T5 card-update link sent for expired card", r.get("ok") is True and r.get("sent_via") == "SMS")
check("G9 link not spoken (no URL in say_hint)", "rzp.io" not in r.get("say_hint", ""))

r = post("/tools/send_payment_link", {"customer_id": "cust_003", "link_type": "new_mandate"})
check("T5 wrong link type refused", r.get("ok") is False and r.get("refused") is True)

r = post("/tools/send_payment_link", {"customer_id": "cust_006", "link_type": "new_mandate"})
check("T5 fresh-mandate link allowed after revocation", r.get("ok") is True)

# --- T6 consent (G6: instant, unpersuaded) --------------------------
r = post("/tools/update_consent", {"customer_id": "cust_009", "action": "pause"})
check("G6 pause honored instantly", r.get("ok") is True)
r = post("/tools/update_consent", {"customer_id": "cust_009", "action": "do_not_call"})
check("G6 do-not-call honored", r.get("ok") is True)
r = post("/tools/schedule_retry", {"customer_id": "cust_009", "retry_date": "2026-10-05"})
check("G6 DNC blocks future scheduling", r.get("ok") is False and r.get("code") == "DO_NOT_CALL")
r = post("/tools/update_consent", {"customer_id": "cust_006", "action": "revoke"})
check("G6 revoke via merchant channel", r.get("ok") is True)

# --- T7 escalation --------------------------------------------------
r = post("/tools/escalate_to_human", {
    "customer_id": "cust_010",
    "reason": "customer disputes charge",
    "summary": "Caller denies subscribing; angry. No promises made, escalating per policy."})
check("T7 escalation ticket created", r.get("ok") is True and str(r.get("ticket_id", "")).startswith("ESC-"))

# --- T8 outcome logging ---------------------------------------------
r = post("/tools/log_call_outcome", {
    "customer_id": "cust_001", "outcome": "promise_to_pay", "notes": "retry Oct 5"})
check("T8 outcome logged", r.get("ok") is True)

# --- summary ----------------------------------------------------------
failed = [n for n, c, _ in results if not c]
print("\n" + "=" * 50)
print(f"{len(results) - len(failed)}/{len(results)} guardrail checks passed")
if failed:
    print("FAILED:", *failed, sep="\n  - ")
sys.exit(1 if failed else 0)
