#!/usr/bin/env bash
# Run a read-only Codex review and save the answer.
#
# Usage: codex_review.sh <prompt_file> <output_file> [repo_dir]
# Exit codes: 0 ok, 3 not signed in with ChatGPT, 4 quota/plan limit, 5 network blocked, 1 other.
# The Codex log (stderr) is written to <output_file>.log.
set -u
prompt=${1:?prompt file}
out=${2:?output file}
repo=${3:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}

case "$(codex login status 2>&1)" in
  *"using ChatGPT"*) ;;
  *) echo "NOT_SIGNED_IN: run codex_login.sh first (ChatGPT account, not an API key)"; exit 3 ;;
esac

# Never let an API key take over the ChatGPT login. </dev/null: without it, codex exec waits
# forever on "Reading additional input from stdin".
unset OPENAI_API_KEY
codex exec --sandbox read-only --skip-git-repo-check -C "$repo" "$(cat "$prompt")" \
  </dev/null >"$out" 2>"$out.log"
rc=$?

if grep -qiE "quota exceeded|usage limit|rate limit" "$out.log"; then
  echo "QUOTA: $(grep -iE 'quota|limit' "$out.log" | tail -1)"; exit 4
fi
if grep -qiE "403|tunnel failed|blocked" "$out.log" && [ ! -s "$out" ]; then
  echo "NETWORK: $(grep -iE '403|tunnel|blocked' "$out.log" | tail -1)"; exit 5
fi
if [ "$rc" -ne 0 ] || [ ! -s "$out" ]; then
  echo "FAILED rc=$rc: $(tail -3 "$out.log" | tr '\n' ' ')"; exit 1
fi
echo "OK $(wc -c <"$out") bytes -> $out"
