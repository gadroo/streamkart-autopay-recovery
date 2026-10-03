# StreamKart Autopay Recovery — AI Voice Agent

An intelligent AI voice agent that recovers failed subscription payments through natural conversation. Built for Razorpay Agent Studio.

## 🎯 What This Does

This voice agent calls customers whose subscription payments failed, identifies the specific issue, and guides them to a solution — retry scheduling, card updates via SMS, or plan downgrades. It handles 10 different failure scenarios with intelligent routing, guardrails, and escalation logic.

**🔴 Live demo:** [Test the agent now](https://widget.retellai.com/call/call_02b4983701fc7497bb7fc83e2e6?access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJjbGllbnQiLCJleHAiOjE3OTEwNTg1OTIsIm5iZiI6MTc5MTA1MDc5MiwiaWF0IjoxNzkxMDUwNzkyLCJpZGVudGl0eSI6ImNsaWVudCIsInZpZGVvIjp7InJvb21Kb2luIjp0cnVlLCJjYW5QdWJsaXNoIjp0cnVlLCJjYW5TdWJzY3JpYmUiOnRydWV9LCJjYWxsX2lkIjoiY2FsbF8wMmI0OTgzNzAxZmM3NDk3YmI3ZmM4M2UyZTYiLCJpbnN0IjoiaS0wNmY5OGE4Mjk5YjNmMmU4YiJ9.VYp9YpZbGKJYw8q3p2qK9qX5wR3nL8mT6vJ2kP1dRDuQ) (no setup needed)  
**Backend:** https://streamkart-autopay-recovery.onrender.com (always on)

---

## 📊 Conversation Flowchart

This flowchart shows every possible path the agent can take:

```mermaid
flowchart TD
    Start([Agent Calls Customer]) --> AskCustomer[Which customer?<br/>Ananya/Rohit/Meera...]
    AskCustomer --> GetContext[get_recovery_context<br/>Fetch account data]
    
    GetContext --> CheckReason{Failure Reason?}
    
    %% INSUFFICIENT FUNDS PATH
    CheckReason -->|Insufficient Balance| InsufficientFunds[Explain payment issue]
    InsufficientFunds --> OfferRetry{Offer Solutions}
    OfferRetry -->|Retry| AskDate[Ask for date<br/>within 7 days]
    AskDate --> ScheduleRetry[schedule_retry<br/>Server validates]
    ScheduleRetry --> RetrySuccess{Server Response?}
    RetrySuccess -->|Success| ConfirmRetry[Confirm date<br/>in spoken form]
    RetrySuccess -->|Refused: COOLDOWN| ExplainCooldown[Explain already scheduled]
    RetrySuccess -->|Refused: DATE_PAST| AskDate
    RetrySuccess -->|Refused: CAP_EXCEEDED| EscalateHuman
    
    OfferRetry -->|Downgrade| SuggestBasic[Suggest Basic plan<br/>₹199/month]
    SuggestBasic --> DowngradeAccept{Accept?}
    DowngradeAccept -->|Yes| ExplainDowngrade[Explain how to<br/>downgrade in account]
    DowngradeAccept -->|No| OfferRetry
    
    %% EXPIRED CARD PATH
    CheckReason -->|Card Expired| ExpiredCard[Explain card expired<br/>hard decline]
    ExpiredCard --> OfferLink[Offer card update link<br/>via SMS]
    OfferLink --> SendLink[send_payment_link<br/>card_update]
    SendLink --> ConfirmLink[Confirm link sent<br/>30 seconds to update]
    
    %% BANK BLOCKED PATH
    CheckReason -->|Bank Blocked| BankBlocked[Explain bank security<br/>block]
    BankBlocked --> OfferBank{Offer Solutions}
    OfferBank -->|Call Bank| ExplainBank[Explain how to<br/>unblock with bank]
    OfferBank -->|New Card| SendLink
    OfferBank -->|Downgrade| SuggestBasic
    
    %% MANDATE REVOKED PATH
    CheckReason -->|Mandate Revoked| MandateRevoked[Explain mandate<br/>was cancelled]
    MandateRevoked --> OfferMandate[Offer fresh mandate<br/>no pressure]
    OfferMandate --> MandateAccept{Accept?}
    MandateAccept -->|Yes| SendMandate[send_payment_link<br/>new_mandate]
    MandateAccept -->|No| RespectDecision[Respect decision<br/>no persuasion]
    
    %% MANDATE EXPIRED PATH
    CheckReason -->|Mandate Expired| MandateExpired[Explain mandate<br/>validity lapsed]
    MandateExpired --> SendMandate
    
    %% RETRY CAP EXHAUSTED PATH
    CheckReason -->|Retry Cap Exhausted| CapExhausted[Explain retries<br/>exhausted]
    CapExhausted --> EscalateHuman[escalate_to_human<br/>Human follow-up needed]
    
    %% NO FAILURE (PAUSE REQUEST) PATH
    CheckReason -->|No Failure| PauseRequest[Customer wants<br/>to pause]
    PauseRequest --> OfferPause{Offer Options}
    OfferPause -->|Pause| UpdatePause[update_consent<br/>pause]
    OfferPause -->|Downgrade| SuggestBasic
    OfferPause -->|Cancel| UpdateCancel[update_consent<br/>cancel]
    
    %% ANGRY/DISPUTE PATH
    CheckReason -->|Angry/Dispute| AngryCustomer[De-escalate<br/>empathize]
    AngryCustomer --> AngryResponse{Customer Response?}
    AngryResponse -->|Calm down| OfferSolutions[Offer solutions<br/>as appropriate]
    AngryResponse -->|Still angry| EscalateHuman
    AngryResponse -->|Asks for refund| ExplainRefund[Explain can't promise<br/>refunds]
    ExplainRefund --> EscalateHuman
    
    %% UNIVERSAL HANDLERS
    OfferSolutions --> CheckReason
    
    %% ESCALATION TRIGGERS (can happen anywhere)
    Anywhere[At any point] --> EscalationCheck{Escalation Triggers?}
    EscalationCheck -->|Disputes charge| EscalateHuman
    EscalationCheck -->|Asks about refunds/policies| EscalateHuman
    EscalationCheck -->|Hostile/angry| EscalateHuman
    EscalationCheck -->|Asks for human| EscalateHuman
    EscalationCheck -->|Complex technical issue| EscalateHuman
    
    %% CLOSING PATHS
    ConfirmRetry --> LogOutcome[log_call_outcome<br/>promise_to_pay]
    ConfirmLink --> LogOutcome2[log_call_outcome<br/>link_sent]
    ExplainDowngrade --> LogOutcome3[log_call_outcome<br/>downgraded]
    RespectDecision --> LogOutcome4[log_call_outcome<br/>declined]
    UpdatePause --> LogOutcome5[log_call_outcome<br/>paused]
    UpdateCancel --> LogOutcome6[log_call_outcome<br/>cancelled]
    EscalateHuman --> LogOutcome7[log_call_outcome<br/>escalated]
    
    LogOutcome --> Close[Thank customer<br/>End call]
    LogOutcome2 --> Close
    LogOutcome3 --> Close
    LogOutcome4 --> Close
    LogOutcome5 --> Close
    LogOutcome6 --> Close
    LogOutcome7 --> Close
    Close --> End([Call Ends])
    
    %% STYLING
    style Start fill:#10b981
    style End fill:#10b981
    style EscalateHuman fill:#f59e0b
    style GetContext fill:#3b82f6
    style ScheduleRetry fill:#8b5cf6
    style SendLink fill:#8b5cf6
    style SendMandate fill:#8b5cf6
    style UpdatePause fill:#8b5cf6
    style UpdateCancel fill:#8b5cf6
    style EscalateHuman fill:#ef4444
    style LogOutcome fill:#6b7280
    style LogOutcome2 fill:#6b7280
    style LogOutcome3 fill:#6b7280
    style LogOutcome4 fill:#6b7280
    style LogOutcome5 fill:#6b7280
    style LogOutcome6 fill:#6b7280
    style LogOutcome7 fill:#6b7280
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Retell Voice Agent                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   STT/TTS    │  │   GPT-4.1    │  │   Tools      │     │
│  │  (ElevenLabs)│  │  (Reasoning) │  │  (6 tools)   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP POST
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Backend (Guardrails)                    │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  get_recovery_context(phone)                          │ │
│  │  → Returns customer data + allowed_actions            │ │
│  │  → Server decides what's allowed, not the LLM         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  send_payment_link(customer_id, type)                 │ │
│  │  → Sends SMS link (simulated)                         │ │
│  │  → Validates link_type matches allowed_actions        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  schedule_retry(customer_id, date)                    │ │
│  │  → GUARDRAILS:                                        │ │
│  │    • Retry cap (1+3 max per mandate)                  │ │
│  │    • 24h cooldown between attempts                    │ │
│  │    • Date must be future, within 7 days               │ │
│  │    • Quiet hours: 09:00-21:00 IST                     │ │
│  │    • Cannot retry if mandate revoked                  │ │
│  │    • Cannot retry if mandate expired                  │ │
│  │    • Cannot retry if card expired (hard decline)      │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  update_consent(customer_id, action)                  │ │
│  │  → pause | revoke | do_not_call | resume              │ │
│  │  → Honored instantly, no retention pressure           │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  escalate_to_human(customer_id, reason, summary)      │ │
│  │  → Creates escalation ticket                          │ │
│  │  → Agent tells customer human will follow up          │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  log_call_outcome(customer_id, outcome, notes)        │ │
│  │  → Audit trail (call_log.jsonl)                       │ │
│  │  → outcome: recovered | promise_to_pay | link_sent |  │ │
│  │            escalated | paused | revoked | dnc |       │ │
│  │            no_answer | unresolved                     │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ SQLite
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Customer Database                         │
│                                                              │
│  customers.json                                             │
│  ├── 10 customer records                                    │
│  ├── Each with specific failure scenario                    │
│  ├── Plans: Basic (₹199), Standard (₹299), Family (₹499)  │
│  └── Languages: English, Hindi, Hinglish                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎬 The 10 Customer Scenarios

| # | Customer | Plan | Failure Reason | Expected Flow |
|---|----------|------|----------------|---------------|
| 1 | **Ananya Sharma** | Standard (₹299) | Insufficient balance | Soft decline → Offer retry OR suggest downgrade to Basic (₹199) |
| 2 | **Rohit Verma** | Standard Plus (₹349) | Insufficient balance (last retry) | Warn this is final attempt → Offer retry OR downgrade |
| 3 | **Meera Iyer** | Family (₹499) | Card expired | Hard decline → Send card update link → Suggest downgrade if hesitant |
| 4 | **Vikram Singh** | Premium Annual (₹4999) | Card expired (high-value) | Send link → Offer human follow-up for priority support |
| 5 | **Priya Nair** | Family (₹499) | Bank blocked | Coach to call bank → Schedule retry OR suggest downgrade |
| 6 | **Arjun Patel** | Standard (₹299) | Mandate revoked | HARD STOP → Cannot retry → Offer fresh mandate (no pressure) |
| 7 | **Kavita Joshi** | Standard Plus (₹349) | Mandate expired | Send new mandate link → Suggest downgrade if hesitant |
| 8 | **Sameer Khan** | Family (₹499) | Retry cap exhausted | Server refuses retry → Escalate to human |
| 9 | **Neha Gupta** | Standard (₹299) | No failure, wants to pause | Honor pause instantly → Suggest downgrade as alternative |
| 10 | **Ramesh Kumar** | Family (₹499) | Angry, disputes charge | De-escalate → Don't argue → Escalate to human with summary |

---

## 🛡️ Guardrails (Server-Side Enforcement)

The agent **cannot violate these rules** — the backend API rejects invalid requests:

| Guardrail | Rule | Why |
|-----------|------|-----|
| **Retry Cap** | Max 1 attempt + 3 retries per mandate | NPCI UPI AutoPay regulation |
| **Cooldown** | 24h minimum between retries | Prevents spamming customer's bank |
| **Quiet Hours** | No calls/schedules outside 09:00-21:00 IST | RBI Fair Practices Code |
| **No Retry on Revoked** | Mandate revoked = cannot retry | NPCI: fresh consent required |
| **No Retry on Expired** | Mandate expired = cannot retry | UPI mandate validity lapsed |
| **No Retry on Hard Decline** | Card expired = cannot retry same card | Will fail again, need new card |
| **Date Validation** | Retry date must be future, within 7 days | Prevents invalid scheduling |
| **Consent Honored** | Pause/revoke/DNC honored instantly | RBI: customer rights |
| **No Refund Promises** | Agent cannot promise refunds | Policy decisions require human |
| **Escalation Triggers** | Disputes, refunds, hostility → human | Complex cases need human judgment |

---

## 🚀 How to Test

### Option 1: Live Demo (Recommended)
1. Open the [web call widget](https://widget.retellai.com/call/[CALL_ID]?access_token=[TOKEN])
2. Grant microphone permission
3. When asked "Which customer?", say a name (e.g., "Ananya")
4. Have a natural conversation — the agent will adapt to your tone

### Option 2: Local Setup
```bash
# Clone the repo
git clone https://github.com/[YOUR_USERNAME]/streamkart-autopay-recovery.git
cd streamkart-autopay-recovery

# Install dependencies
pip install -r requirements.txt

# Start the backend
python backend/server.py
# Server runs on http://localhost:8080

# In another terminal, start the tunnel
ngrok http 8080
# Copy the public URL (e.g., https://abc123.ngrok.io)

# Update Retell agent with the public URL (see docs/retell-setup.md)

# Open the Retell widget and test
```

### Option 3: Watch Demo Videos
[Video folder with all 10 scenarios](https://drive.google.com/drive/folders/[FOLDER_ID])

---

## 📁 Project Structure

```
streamkart-autopay-recovery/
├── backend/
│   └── server.py              # FastAPI server with guardrails
├── data/
│   └── customers.json         # 10 customer records
├── agent/
│   ├── retell_llm.json        # Retell LLM configuration
│   └── system_prompt.txt      # Agent prompt
├── docs/
│   ├── architecture.png       # Architecture diagram
│   ├── flowchart.png          # Conversation flowchart
│   └── retell-setup.md        # How to configure Retell
├── tests/
│   └── test_tools.py          # 29/29 tests passing
├── README.md                  # This file
├── requirements.txt           # Python dependencies
└── .env.example               # Environment variables template
```

---

## 🧪 Testing

All 29 guardrail tests pass:

```bash
pytest tests/test_tools.py -v
```

Tests cover:
- Authentication (invalid key rejected)
- Context lookup (by phone, by ID, unknown customer)
- Retry scheduling (happy path, cooldown, cap exceeded, date validation)
- Payment links (card update, new mandate, wrong type rejected)
- Consent updates (pause, revoke, DNC, resume)
- Escalation (ticket creation, summary logging)
- Call outcome logging (all 9 outcomes)

---

## 🎯 Key Design Decisions

### 1. Server-Side Guardrails
The LLM **decides what to say**, the server **decides what's allowed**. This prevents the agent from violating RBI/NPCI regulations even if the model hallucinates.

### 2. Salesmanship Built In
When customers are hesitant about cost, the agent proactively suggests cheaper plans (Basic at ₹199, Standard at ₹299) before accepting cancellation. Framed as helpful options, not pressure.

### 3. Intelligent Conversation
No rigid scripts. The agent listens, adapts tone, handles questions naturally, and routes based on customer intent. The LLM is trusted to be intelligent; the server enforces rules.

### 4. Hinglish Support
Agent adapts to English, Hindi, or Hinglish code-switching. Pronunciation is phonetically correct for Indian accents.

### 5. Escalation as a Feature
Complex cases (disputes, refunds, hostility) are escalated to humans with full context. The agent doesn't guess or make promises it can't keep.

---

## 📄 License

MIT — use it, modify it, build on it.

---

## 🙏 Credits

- **Voice:** Palak M (ElevenLabs community voice, native Hindi)
- **LLM:** GPT-4.1 (OpenAI)
- **Platform:** Retell AI
- **Backend:** FastAPI + SQLite
- **Inspiration:** Razorpay Agent Studio, industry best practices from Rezoki, Outcraft, and payment recovery research

---

**Built in 48 hours for the Razorpay Agent Studio FDE assignment.**
