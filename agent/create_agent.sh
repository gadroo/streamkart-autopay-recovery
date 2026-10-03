#!/bin/bash
# Create the Retell agent via REST directly, using the key from the CLI keychain.
set -uo pipefail
KEY=*** find-generic-password -s retell-cli -a api-key -w 2>/dev/null)
if [ -z "$KEY" ]; then echo "KEYCHAIN READ FAILED"; exit 1; fi

curl -s --max-time 60 -X POST "https://api.retellai.com/create-agent" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/agent_payload.json
echo
echo "CURL_EXIT=$?"
