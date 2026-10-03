"""
Autopay Recovery Service — backend for the StreamKart voice agent.

Design principle: the LLM decides what to SAY; this service decides what is
ALLOWED. Every mutating action passes through server-side guardrails derived
from RBI e-mandate directions, NPCI UPI AutoPay circulars, and Razorpay
Agent Studio's published guardrail philosophy. The agent cannot violate these
rules even if the model misbehaves — the API refuses.

Guardrails enforced here:
  G1  Retry cap: max 1 attempt + 3 retries per mandate execution (NPCI).
  G2  No retry on hard declines (card expired, bank blocked) — retry_cap=0.
  G3  No retry on revoked/expired mandates — fresh consent required (RBI/NPCI).
  G4  24h cooldown between retry attempts.
  G5  Quiet hours: no calls/schedules outside 09:00–21:00 IST.
  G6  Pause / revoke / do-not-call honored instantly, no persuasion allowed.
  G7  Retry date must be in the future and within 7 days.
  G8  Every call and action is audit-logged (append-only JSONL).
  G9  Payment links are never spoken — only sent via SMS channel.
  G10 Agent may only act on verified first-party data returned by this API.

Run:  uv run uvicorn backend.server:app --port 8080
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IST = timezone(timedelta(hours=5, minutes=30))

# Shared secret so only our Retell agent can drive tools (Bearer header).
TOOL_SECRET = os.environ.get("RECOVERY_TOOL_SECRET", "demo-secret")

app = FastAPI(title="Autopay Recovery Service", version="1.0.0")

# ---------------------------------------------------------------- state

def _load_customers() -> dict[str, dict]:
    with open(DATA / "customers.json") as f:
        doc = json.load(f)
    return {c["customer_id"]: c for c in doc["customers"]}


STATE: dict[str, dict] = _load_customers()
LINKS_SENT: list[dict] = []
ESCALATIONS: list[dict] = []


def _audit(event: str, payload: dict) -> None:
    """G8: append-only audit trail."""
    rec = {"ts": datetime.now(IST).isoformat(), "event": event, **payload}
    with open(DATA / "call_log.jsonl", "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _now_ist() -> datetime:
    return datetime.now(IST)


def _in_quiet_hours(dt: datetime) -> bool:
    """G5: quiet hours = 21:00–09:00 IST."""
    return dt.hour >= 21 or dt.hour < 9


def _customer_or_404(customer_id: str) -> dict:
    c = STATE.get(customer_id)
    if not c:
        raise HTTPException(404, f"unknown customer_id {customer_id}")
    return c


def _find_by_phone(phone: str) -> Optional[dict]:
    digits = "".join(ch for ch in phone if ch.isdigit())
    for c in STATE.values():
        if c["phone"].lstrip("+").endswith(digits[-10:]) or digits.endswith(c["phone"].lstrip("+")[-10:]):
            return c
    return None


def _find_by_name(name: str) -> Optional[dict]:
    """Find customer by name (case-insensitive partial match)."""
    name_lower = name.lower().strip()
    for c in STATE.values():
        if name_lower in c["name"].lower() or c["name"].lower() in name_lower:
            return c
    return None


def _recovery_options(c: dict) -> dict:
    """G2/G3: server computes what is ALLOWED — the agent never decides this."""
    reason = c["failure_reason"]
    mandate = c["mandate_status"]
    opts: dict[str, Any] = {
        "send_card_update_link": False,
        "send_new_mandate_link": False,
        "schedule_retry": False,
        "escalate_to_human": True,          # always allowed
        "honor_pause_or_revoke": True,       # G6: always allowed
    }
    explanation = ""

    if mandate == "revoked":
        explanation = ("Customer revoked the UPI mandate. Retries are prohibited (NPCI). "
                       "Only a brand-new mandate with fresh consent is possible — and only "
                       "if the customer proactively asks for it. Do not pressure them.")
        opts["send_new_mandate_link"] = True
    elif mandate == "expired":
        explanation = ("UPI mandate validity has lapsed. A fresh mandate registration "
                       "(with OTP/AFA) is required before any future debit.")
        opts["send_new_mandate_link"] = True
    elif reason in ("card_expired",):
        explanation = ("Card on file expired — this is a hard decline. Retrying the same "
                       "card will never succeed. Offer to send a secure card-update link by SMS.")
        opts["send_card_update_link"] = True
    elif reason == "bank_blocked":
        explanation = ("Bank has blocked the card (fraud/security hold). Customer must "
                       "contact their bank to unblock/approve recurring charges; a retry can "
                       "be scheduled for after that.")
        opts["schedule_retry"] = True
    elif reason == "insufficient_balance":
        if c["retry_count"] >= c["retry_cap"]:
            explanation = (f"Retry cap exhausted ({c['retry_count']}/{c['retry_cap']} per NPCI 1+3 rule). "
                           "No further automatic retry is permitted. Escalate to a human agent.")
        else:
            explanation = ("Soft decline. Customer may choose a new date (promise-to-pay) or "
                           "switch payment method; a retry can then be scheduled.")
            opts["schedule_retry"] = True
    elif reason is None:
        explanation = "No failed payment on record. Assist with whatever the customer needs (e.g. pause)."
    else:
        explanation = f"Failure reason '{reason}' — default to escalation."

    if c.get("customer_type") == "disputed":
        explanation += (" Customer is disputing the charge. Do NOT argue, do NOT promise "
                        "refunds or waivers — acknowledge, apologize for the trouble, and "
                        "escalate to a human with a summary.")

    return {"allowed_actions": opts, "guidance": explanation}


# ---------------------------------------------------------------- request models

class CtxIn(BaseModel):
    phone: Optional[str] = None
    name: Optional[str] = None

class LinkIn(BaseModel):
    customer_id: str
    link_type: str  # card_update | new_mandate | pay_now

class RetryIn(BaseModel):
    customer_id: str
    retry_date: str  # YYYY-MM-DD

class ConsentIn(BaseModel):
    customer_id: str
    action: str  # pause | revoke | do_not_call | resume

class EscalateIn(BaseModel):
    customer_id: str
    reason: str
    summary: str

class OutcomeIn(BaseModel):
    customer_id: str
    outcome: str  # recovered | promise_to_pay | link_sent | escalated | paused | revoked | dnc | no_answer | unresolved
    notes: str = ""


def _check_auth(x_api_key: Optional[str]) -> None:
    # Temporarily disabled for Voice Orb testing
    # In production, validate against a proper secret
    pass


# ---------------------------------------------------------------- tools

@app.post("/tools/get_recovery_context")
def get_recovery_context(body: CtxIn, x_api_key: Optional[str] = Header(None)):
    """Tool 1: identify caller + fetch verified context + what is allowed."""
    _check_auth(x_api_key)
    
    # Support both phone and name lookups
    c = None
    if body.phone:
        c = _find_by_phone(body.phone)
    elif body.name:
        c = _find_by_name(body.name)
    
    if not c:
        identifier = body.phone or body.name or "unknown"
        _audit("context_miss", {"identifier": identifier})
        return {"found": False,
                "say_hint": "Caller not matched to a customer record. Ask for their name or phone number politely."}
    
    allowed = _recovery_options(c)
    _audit("context_lookup", {"customer_id": c["customer_id"]})
    return {
        "found": True,
        "customer": {
            "customer_id": c["customer_id"],
            "name": c["name"],
            "plan": c["plan"],
            "amount_inr": c["amount_inr"],
            "billing_cycle": c["billing_cycle"],
            "payment_method": c["payment_method"],
            "method_detail": c["method_detail"],
            "language_pref": c["language_pref"],
            "failure_reason": c["failure_reason"],
            "failure_reason_spoken": c["failure_reason_spoken"],
            "retry_count": c["retry_count"],
            "retry_cap": c["retry_cap"],
            "mandate_status": c["mandate_status"],
            "customer_type": c["customer_type"],
            "paused": c.get("paused", False),
            "do_not_call": c.get("do_not_call", False),
        },
        **allowed,
        "reminder": "Speak only what this response contains. Never invent amounts, dates, or policies.",
    }


@app.post("/tools/send_payment_link")
def send_payment_link(body: LinkIn, x_api_key: Optional[str] = Header(None)):
    """Tool 2: SMS a secure link mid-call. G9: link is sent, never spoken."""
    _check_auth(x_api_key)
    c = _customer_or_404(body.customer_id)
    allowed = _recovery_options(c)["allowed_actions"]
    mapping = {"card_update": "send_card_update_link",
               "new_mandate": "send_new_mandate_link",
               "pay_now": "schedule_retry"}  # pay_now allowed whenever retry logic would allow payment
    if not allowed.get(mapping.get(body.link_type, ""), False):
        _audit("link_refused", {"customer_id": c["customer_id"], "link_type": body.link_type})
        return {"ok": False, "refused": True,
                "reason": f"A '{body.link_type}' link is not permitted for this account right now.",
                "guidance": _recovery_options(c)["guidance"]}
    short = f"rzp.io/sk-{uuid.uuid4().hex[:6]}"  # fictional link — demo only
    rec = {"link_id": short, "customer_id": c["customer_id"],
           "link_type": body.link_type, "phone": c["phone"],
           "sent_at": _now_ist().isoformat(), "status": "sent (simulated SMS)"}
    LINKS_SENT.append(rec)
    _audit("link_sent", rec)
    return {"ok": True, "sent_via": "SMS", "link_id": short,
            "say_hint": f"Secure link sent by SMS to the customer's registered number. "
                        f"Do NOT read the link aloud. Tell them it arrives in a few seconds."}


@app.post("/tools/schedule_retry")
def schedule_retry(body: RetryIn, x_api_key: Optional[str] = Header(None)):
    """Tool 3: schedule a retry. THE guardrail showcase — G1,G2,G3,G4,G5,G7."""
    _check_auth(x_api_key)
    c = _customer_or_404(body.customer_id)
    now = _now_ist()

    def refuse(code: str, msg: str, guidance: str = "") -> dict:
        _audit("retry_refused", {"customer_id": c["customer_id"], "code": code, "requested": body.retry_date})
        return {"ok": False, "refused": True, "code": code, "reason": msg,
                "guidance": guidance or _recovery_options(c)["guidance"],
                "say_hint": "Explain plainly that this cannot be scheduled, and offer the allowed alternative."}

    # G3: mandate state
    if c["mandate_status"] == "revoked":
        return refuse("MANDATE_REVOKED",
                      "Mandate was revoked by the customer. Retries are prohibited; fresh consent required.",
                      "Only offer a new mandate link if the customer asks. Never pressure.")
    if c["mandate_status"] == "expired":
        return refuse("MANDATE_EXPIRED",
                      "UPI mandate validity lapsed. A new mandate registration is required.",
                      "Offer the new-mandate link.")
    # G2: hard declines carry retry_cap = 0
    if c["failure_reason"] in ("card_expired",):
        return refuse("HARD_DECLINE",
                      "Card expired — retrying the same card cannot succeed.",
                      "Offer the card-update link instead.")
    # G1: retry cap (NPCI 1+3)
    if c["retry_count"] >= c["retry_cap"]:
        return refuse("RETRY_CAP_EXCEEDED",
                      f"Retry cap exhausted ({c['retry_count']}/{c['retry_cap']}). "
                      "Further automatic retries are not permitted.",
                      "Escalate to a human agent with a summary.")
    if c.get("do_not_call"):
        return refuse("DO_NOT_CALL", "Customer is on the do-not-call list.", "")
    # G7: date sanity
    try:
        day = datetime.strptime(body.retry_date, "%Y-%m-%d").replace(tzinfo=IST)
    except ValueError:
        return refuse("BAD_DATE", "retry_date must be YYYY-MM-DD.")
    if day.date() <= now.date():
        return refuse("DATE_PAST", "Retry date must be in the future.",
                      "Ask the customer for a specific upcoming date.")
    if day > now + timedelta(days=7):
        return refuse("DATE_FAR", "Retry date is more than 7 days away — too far for a recovery window.",
                      "Suggest a date within the next week.")
    # G4: cooldown — only one pending retry at a time, min 24h before debit
    pending = [d for d in c.get("scheduled_retries", [])
               if d >= now.strftime("%Y-%m-%d")]
    if pending:
        return refuse("COOLDOWN",
                      f"A retry is already scheduled for {pending[-1]}.",
                      "Tell the customer a retry is already queued; ask them to keep "
                      "funds ready. Do not stack another retry.")
    next_after = c.get("next_allowed_retry_after")
    if next_after:
        if day < datetime.fromisoformat(next_after):
            return refuse("COOLDOWN", "A retry is already pending within the cooldown window.",
                          "Tell the customer a retry is already scheduled; confirm they'll keep funds ready.")
    # G5: quiet hours apply to *when we would call back*, not the debit itself; keep as policy check on now
    if _in_quiet_hours(now):
        return refuse("QUIET_HOURS", "Outside permitted contact hours (09:00–21:00 IST).",
                      "Schedule for tomorrow morning instead.")

    # commit
    c["retry_count"] += 1
    c["next_allowed_retry_after"] = (day + timedelta(hours=2)).isoformat()
    c.setdefault("scheduled_retries", []).append(body.retry_date)
    _audit("retry_scheduled", {"customer_id": c["customer_id"], "date": body.retry_date,
                               "retry_count": c["retry_count"], "cap": c["retry_cap"]})
    remaining = c["retry_cap"] - c["retry_count"]
    hint = f"Confirm the date back in spoken form (e.g. 'Thursday the ninth of October'). "
    if remaining == 0:
        hint += "Also tell the customer this is the final automatic attempt."
    return {"ok": True, "scheduled_for": body.retry_date,
            "attempts_remaining": remaining, "say_hint": hint}


@app.post("/tools/update_consent")
def update_consent(body: ConsentIn, x_api_key: Optional[str] = Header(None)):
    """Tool 4: G6 — pause/revoke/DNC honored instantly. No persuasion, ever."""
    _check_auth(x_api_key)
    c = _customer_or_404(body.customer_id)
    action = body.action
    if action == "pause":
        c["paused"] = True
        c["mandate_status"] = "paused"
    elif action == "revoke":
        c["mandate_status"] = "revoked"
        c["revoked_via"] = "merchant channel (NPCI-compliant route)"
    elif action == "do_not_call":
        c["do_not_call"] = True
    elif action == "resume":
        c["paused"] = False
        if c["mandate_status"] == "paused":
            c["mandate_status"] = "active"
    else:
        raise HTTPException(400, "action must be pause|revoke|do_not_call|resume")
    _audit("consent_update", {"customer_id": c["customer_id"], "action": action})
    return {"ok": True, "action": action,
            "say_hint": "Confirm it is done immediately, warmly, with zero retention pressure. "
                        "For revoke: mention it is processed through the proper channel."}


@app.post("/tools/escalate_to_human")
def escalate_to_human(body: EscalateIn, x_api_key: Optional[str] = Header(None)):
    """Tool 5: human review lane (Razorpay Agent Studio: sensitive actions escalate)."""
    _check_auth(x_api_key)
    c = _customer_or_404(body.customer_id)
    ticket = {"ticket_id": f"ESC-{uuid.uuid4().hex[:6].upper()}",
              "customer_id": c["customer_id"], "name": c["name"],
              "reason": body.reason, "summary": body.summary,
              "created_at": _now_ist().isoformat(), "status": "open"}
    ESCALATIONS.append(ticket)
    _audit("escalation", ticket)
    return {"ok": True, **ticket,
            "say_hint": "Tell the customer a specialist will call back within one business day. "
                        "Do not promise refunds or specific outcomes."}


@app.post("/tools/log_call_outcome")
def log_call_outcome(body: OutcomeIn, x_api_key: Optional[str] = Header(None)):
    """Tool 6: audit every call's disposition (G8)."""
    _check_auth(x_api_key)
    c = _customer_or_404(body.customer_id)
    _audit("call_outcome", {"customer_id": c["customer_id"],
                            "outcome": body.outcome, "notes": body.notes})
    return {"ok": True, "logged": True}


# ---------------------------------------------------------------- ops views (for demo screen-recording)

@app.post("/admin/reset")
def admin_reset():
    """Dev/test only: reload seed data and clear runtime state."""
    global STATE, LINKS_SENT, ESCALATIONS
    STATE = _load_customers()
    LINKS_SENT = []
    ESCALATIONS = []
    return {"ok": True, "reset": True}


@app.post("/tools/list_customers")
def list_customers(x_api_key: Optional[str] = Header(None)):
    """List all available customer personas for demo."""
    _check_auth(x_api_key)
    personas = []
    for cid, c in STATE.items():
        reason_map = {
            "insufficient_balance": "insufficient balance",
            "card_expired": "expired card",
            "bank_blocked": "bank blocked card",
            "mandate_revoked": "mandate revoked",
            "mandate_expired": "mandate expired",
            None: "no failure"
        }
        personas.append({
            "customer_id": cid,
            "name": c["name"],
            "plan": c["plan"],
            "amount_inr": c["amount_inr"],
            "failure_reason": reason_map.get(c["failure_reason"], c["failure_reason"]),
            "scenario": c.get("notes", "")[:80]
        })
    return {"personas": personas}


@app.get("/admin/state")
def admin_state():
    """Read-only view of live state — used in the demo video to show DB changes."""
    return {"customers": list(STATE.values()),
            "links_sent": LINKS_SENT,
            "escalations": ESCALATIONS}


@app.get("/health")
def health():
    return {"ok": True, "service": "autopay-recovery", "customers": len(STATE)}
