#!/usr/bin/env bash
# Make sure Codex is installed and signed in with a ChatGPT account (plan quota, not API credits).
#
# Usage: codex_login.sh <log_file>
# Prints one of:
#   READY                      already signed in with ChatGPT
#   DEVICE_AUTH <url> <code>   show these to the user; the login keeps waiting in the background
#                              and appends "exit=<code>" to <log_file> when it finishes
#   ERROR <reason>
set -u
log=${1:?log file}

if ! command -v codex >/dev/null 2>&1; then
  npm install -g @openai/codex >/dev/null 2>&1 || { echo "ERROR npm install -g @openai/codex failed"; exit 1; }
fi

status=$(codex login status 2>&1)
case "$status" in
  *"using ChatGPT"*) echo "READY"; exit 0 ;;
  *"API key"*) codex logout >/dev/null 2>&1 ;;  # API key = pay-per-use credits; switch to ChatGPT
esac

# Device code login: works without a browser in this container. Needs auth.openai.com.
: > "$log"
( unset OPENAI_API_KEY; codex login --device-auth </dev/null >>"$log" 2>&1; echo "exit=$?" >>"$log" ) &
for _ in $(seq 1 20); do
  sleep 1
  clean=$(sed 's/\x1b\[[0-9;]*m//g' "$log")
  url=$(grep -oE 'https://auth\.openai\.com/codex/device[^ ]*' <<<"$clean" | head -1)
  code=$(grep -oE '\b[A-Z0-9]{4}-[A-Z0-9]{4,5}\b' <<<"$clean" | head -1)
  if [ -n "$url" ] && [ -n "$code" ]; then
    echo "DEVICE_AUTH $url $code"
    exit 0
  fi
  if grep -q "exit=" <<<"$clean"; then
    echo "ERROR $(grep -v '^exit=' <<<"$clean" | tail -2 | tr '\n' ' ')"
    exit 1
  fi
done
echo "ERROR no device code after 20 s: $(tail -2 "$log" | tr '\n' ' ')"
exit 1
