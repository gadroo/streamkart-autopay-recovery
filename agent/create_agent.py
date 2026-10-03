"""Create the Retell agent via REST. Key comes from the CLI's macOS keychain entry."""
import json
import subprocess
import sys
import urllib.request

key = subprocess.run(
    ["security", "find-generic-password", "-s", "retell-cli", "-a", "api-key", "-w"],
    capture_output=True, text=True,
).stdout.strip()
if not key:
    print("KEYCHAIN READ FAILED")
    sys.exit(1)

payload = json.load(open("/tmp/agent_payload.json"))
req = urllib.request.Request(
    "https://api.retellai.com/create-agent",
    data=json.dumps(payload).encode(),
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read())
        print("HTTP", r.status)
        print(json.dumps({k: body.get(k) for k in
                          ("agent_id", "agent_name", "voice_id", "voice_model",
                           "language", "response_engine")}, indent=2))
        with open("/tmp/agent_created.json", "w") as f:
            json.dump(body, f, indent=2)
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode()[:1000])
    sys.exit(1)
