#!/bin/bash
# Create the Retell LLM engine. Uses the CLI's keychain credential (the VALID key
# stored by `retell auth login`), NOT the stale key in .env.
set -euo pipefail
cd "$(dirname "$0")/.."

# sanity: confirm CLI auth works non-interactively first (60s cap)
timeout 60 retell list-agents < /dev/null > /tmp/pre_check.json || {
  echo "PRECHECK FAILED"; cat /tmp/pre_check.json; exit 1;
}
echo "precheck OK: $(head -c 100 /tmp/pre_check.json)"

# create the LLM engine (120s cap, no stdin)
timeout 120 retell create-retell-llm --body agent/retell_llm.json < /dev/null
echo "EXIT=$?"
