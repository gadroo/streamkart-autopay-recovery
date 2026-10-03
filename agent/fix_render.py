"""
Fix: Create new LLM with Render URLs, then create new agent pointing to it.
"""
import json
import urllib.request
import urllib.error

KEY = "key_94c103d01ea580afe820a0255071"
NEW_BACKEND = "https://streamkart-autopay-recovery.onrender.com"

def api_call(method, url, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json"
    }, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"ERROR {e.code}: {e.read().decode()[:500]}")
        raise

# Step 1: Build the new LLM config (only the fields Retell expects for create)
new_llm_config = {
    "model": "gpt-4.1",
    "model_temperature": 0.15,
    "start_speaker": "agent",
    "begin_message": "Hi, this is Sana from StreamKart. I'm calling about your subscription payment. Do you have a moment?",
    "max_model_response_wait_time_ms": 10000,
    "responsive_proneness_seconds": 2,
    "responsiveness": 0.75,
    "general_prompt": open("/Users/beehoney413/fde-assignment/autopay-recovery/agent/system_prompt.txt").read() if __import__("os").path.exists("/Users/beehoney413/fde-assignment/autopay-recovery/agent/system_prompt.txt") else open("/Users/beehoney413/fde-assignment/autopay-recovery/agent/retell_llm.json").read() and json.load(open("/Users/beehoney413/fde-assignment/autopay-recovery/agent/retell_llm.json")).get("general_prompt", ""),
    "general_tools": [
        {
            "type": "custom",
            "name": "get_recovery_context",
            "description": "MANDATORY first step of every call. Looks up the customer and returns their account context.",
            "url": f"{NEW_BACKEND}/tools/get_recovery_context",
            "method": "POST",
            "headers": {"x-api-key": "demo-secret"},
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "The customer's registered phone number.",
                        "const": "{{customer_phone}}"
                    }
                },
                "required": ["phone"]
            },
            "parameter_type": "json",
            "args_at_root": True,
            "speak_during_execution": True,
            "speak_after_execution": True,
            "timeout_ms": 12000,
            "max_retry": 0
        },
        {
            "type": "custom",
            "name": "send_payment_link",
            "description": "Send a secure payment link by SMS during the call.",
            "url": f"{NEW_BACKEND}/tools/send_payment_link",
            "method": "POST",
            "headers": {"x-api-key": "demo-secret"},
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID from get_recovery_context"},
                    "link_type": {"type": "string", "enum": ["card_update", "new_mandate", "pay_now"]}
                },
                "required": ["customer_id", "link_type"]
            },
            "parameter_type": "json",
            "args_at_root": True,
            "speak_during_execution": True,
            "speak_after_execution": True,
            "timeout_ms": 12000,
            "max_retry": 0
        },
        {
            "type": "custom",
            "name": "schedule_retry",
            "description": "Schedule a payment retry for a customer-chosen date.",
            "url": f"{NEW_BACKEND}/tools/schedule_retry",
            "method": "POST",
            "headers": {"x-api-key": "demo-secret"},
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID from get_recovery_context"},
                    "retry_date": {"type": "string", "description": "Date in YYYY-MM-DD format"}
                },
                "required": ["customer_id", "retry_date"]
            },
            "parameter_type": "json",
            "args_at_root": True,
            "speak_during_execution": True,
            "speak_after_execution": True,
            "timeout_ms": 12000,
            "max_retry": 0
        },
        {
            "type": "custom",
            "name": "update_consent",
            "description": "Record a consent decision (pause/revoke/do_not_call/resume).",
            "url": f"{NEW_BACKEND}/tools/update_consent",
            "method": "POST",
            "headers": {"x-api-key": "demo-secret"},
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID from get_recovery_context"},
                    "action": {"type": "string", "enum": ["pause", "revoke", "do_not_call", "resume"]}
                },
                "required": ["customer_id", "action"]
            },
            "parameter_type": "json",
            "args_at_root": True,
            "speak_during_execution": False,
            "speak_after_execution": True,
            "timeout_ms": 12000,
            "max_retry": 0
        },
        {
            "type": "custom",
            "name": "escalate_to_human",
            "description": "Escalate to a human agent.",
            "url": f"{NEW_BACKEND}/tools/escalate_to_human",
            "method": "POST",
            "headers": {"x-api-key": "demo-secret"},
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID from get_recovery_context"},
                    "reason": {"type": "string", "description": "Short reason for escalation"},
                    "summary": {"type": "string", "description": "2-3 sentence call summary"}
                },
                "required": ["customer_id", "reason", "summary"]
            },
            "parameter_type": "json",
            "args_at_root": True,
            "speak_during_execution": True,
            "speak_after_execution": True,
            "timeout_ms": 12000,
            "max_retry": 0
        },
        {
            "type": "custom",
            "name": "log_call_outcome",
            "description": "Log the final call disposition.",
            "url": f"{NEW_BACKEND}/tools/log_call_outcome",
            "method": "POST",
            "headers": {"x-api-key": "demo-secret"},
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID from get_recovery_context"},
                    "outcome": {"type": "string", "enum": ["recovered", "promise_to_pay", "link_sent", "escalated", "paused", "revoked", "dnc", "no_answer", "unresolved"]},
                    "notes": {"type": "string", "description": "Optional one-line note"}
                },
                "required": ["customer_id", "outcome"]
            },
            "parameter_type": "json",
            "args_at_root": True,
            "speak_during_execution": False,
            "speak_after_execution": False,
            "timeout_ms": 12000,
            "max_retry": 0
        },
        {
            "type": "end_call",
            "name": "end_call",
            "description": "End the call after goodbye."
        }
    ]
}

# Load the actual prompt from the JSON config
with open("/Users/beehoney413/fde-assignment/autopay-recovery/agent/retell_llm.json") as f:
    old_config = json.load(f)
    new_llm_config["general_prompt"] = old_config.get("general_prompt", "")

print("Step 1: Creating new LLM with Render URLs...")
result = api_call("POST", "https://api.retellai.com/create-retell-llm", new_llm_config)
new_llm_id = result["llm_id"]
print(f"✓ New LLM created: {new_llm_id}")

print("\nStep 2: Creating new agent...")
new_agent_config = {
    "agent_name": "Sana - StreamKart Autopay Recovery",
    "channel": "voice",
    "language": ["en-IN", "hi-IN"],
    "voice_id": "custom_voice_bb1f8a0b2c1291e9d8ccd2f361",
    "voice_model": "eleven_multilingual_v2",
    "interruption_sensitivity": 0.8,
    "responsiveness": 0.85,
    "ring_duration_ms": 15000,
    "max_call_duration_ms": 3600000,
    "stt_mode": "accurate",
    "boosted_keywords": [
        "StreamKart", "Sana", "Ananya", "Rohit", "Meera", "Vikram", "Priya",
        "Arjun", "Kavita", "Sameer", "Neha", "Ramesh", "Basic", "Standard",
        "Family", "Premium", "payment", "subscription", "retry", "mandate",
        "rupees", "hundred", "ninety nine", "pause", "cancel", "downgrade"
    ],
    "response_engine": {
        "type": "retell-llm",
        "llm_id": new_llm_id,
        "version": 0
    }
}
result2 = api_call("POST", "https://api.retellai.com/create-agent", new_agent_config)
new_agent_id = result2["agent_id"]
print(f"✓ New agent created: {new_agent_id}")

print("\nStep 3: Publishing agent version 0...")
result3 = api_call("POST", f"https://api.retellai.com/publish-agent-version/{new_agent_id}", {"version": 0})
print(f"✓ Published")

print("\nStep 4: Creating test call...")
result4 = api_call("POST", "https://api.retellai.com/v3/create-web-call", {"agent_id": new_agent_id})
call_id = result4["call_id"]
access_token = result4["access_token"]
test_url = f"https://widget.retellai.com/call/{call_id}?access_token={access_token}"

print(f"\n{'='*60}")
print(f"NEW AGENT ID: {new_agent_id}")
print(f"NEW LLM ID: {new_llm_id}")
print(f"BACKEND: {NEW_BACKEND}")
print(f"{'='*60}")
print(f"\n🔗 TEST URL (copy this):")
print(test_url)
print(f"{'='*60}")

# Save everything
with open("/Users/beehoney413/fde-assignment/autopay-recovery/agent/agent_id.txt", "w") as f:
    f.write(new_agent_id)
with open("/Users/beehoney413/fde-assignment/autopay-recovery/TEST_LINK.txt", "w") as f:
    f.write(test_url)
print("\n✓ Saved agent_id.txt and TEST_LINK.txt")
