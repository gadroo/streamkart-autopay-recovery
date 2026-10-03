"""Verify the agent on Retell and publish its draft version."""
import json
import subprocess
import sys
import urllib.request

def api(method, path, body=None):
    key = subprocess.run(
        ["security", "find-generic-password", "-s", "retell-cli", "-a", "api-key", "-w"],
        capture_output=True, text=True,
    ).stdout.strip()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"https://api.retellai.com{path}",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]

# 1) get the agent
st, agent = api("GET", "/get-agent/agent_dd770bb0d7b48d7869c713c96a")
print("get-agent HTTP", st)
if st == 200:
    print(json.dumps({k: agent.get(k) for k in
                      ("agent_id", "agent_name", "voice_id", "language",
                       "latest_version", "latest_published_version")}, indent=2))

# 2) list versions to find the draft to publish
st, versions = api("GET", "/list-agent-versions/agent_dd770bb0d7b48d7869c713c96a")
print("list-versions HTTP", st)
if st == 200:
    items = versions.get("items", versions) if isinstance(versions, dict) else versions
    for v in (items if isinstance(items, list) else [items])[:5]:
        if isinstance(v, dict):
            print("  version:", {k: v.get(k) for k in ("version", "is_published", "version_description")})

# 3) publish version 0
st, pub = api("POST", "/publish-agent-version/agent_dd770bb0d7b48d7869c713c96a", {"version": 0})
print("publish HTTP", st)
print(json.dumps(pub, indent=2)[:400] if isinstance(pub, (dict, list)) else str(pub)[:400])
