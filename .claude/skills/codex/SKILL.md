---
name: codex
description: Consult OpenAI Codex (the codex CLI) for a second opinion, such as a code or UX review, a root-cause analysis, or a design proposal. Use it whenever the user asks to ask, consult, or review with Codex (コーデックス / codex に聞く / codex とレビュー). It signs in with the user's ChatGPT account (plan quota) rather than API credits, and works in Claude Code cloud sessions.
---

# Consulting Codex

## Facts to get right first

- **Use the ChatGPT account login, not an API key.** The user's ChatGPT plan (Plus / Pro / Team) includes Codex usage.
  An `OPENAI_API_KEY` or a saved network secret for `api.openai.com` bills **API credits**, which is a separate account.
  If that account has no credits, the result is `Quota exceeded`. That error does **not** mean the cloud cannot run Codex,
  and it does not mean the user has to buy credits. Switch to the ChatGPT login.
- **Codex runs fine in a cloud session.** Don't tell the user it only works locally.
- **The container needs these hosts:** `auth.openai.com` for the login and `chatgpt.com` for requests made with the ChatGPT login.
  A `CONNECT tunnel failed, response 403` means the environment's network policy blocks them.
  In that case, call `get_environment`, then `update_environment` with `add_allowed_hosts: ["auth.openai.com", "chatgpt.com"]`
  (the user approves the change). The user's Default environment already allows both.
- **`codex exec` must get `</dev/null` on stdin.** Otherwise it hangs forever on "Reading additional input from stdin".
- **A login does not survive the container.** A new cloud session usually needs the device login again, which takes about a minute of the user's time.

## Steps

All scripts are in this folder (`.claude/skills/codex/`). Keep temporary files in the scratchpad directory.

1. **Sign in.** Run `codex_login.sh <scratchpad>/codex_login.log`.
   - `READY`: go to step 2.
   - `DEVICE_AUTH <url> <code>`: give the user the URL and the code in Japanese, and say the code expires in 15 minutes.
     Then wait in the background, not with a foreground sleep:
     `until grep -q "exit=" <log>; do sleep 2; done; tail -3 <log>`. `Successfully logged in` / `exit=0` means done.
   - `ERROR ... error sending request` / 403: allow the two hosts above, then run the script again.
2. **Write the prompt** to a file in the scratchpad, using the template below.
3. **Run the review in the background.** It takes several minutes:
   `codex_review.sh <prompt_file> <scratchpad>/codex_review.md [repo_dir]` with `run_in_background: true` and a long timeout (about 20 minutes).
   - `OK`: read the output file.
   - `NOT_SIGNED_IN`: go back to step 1.
   - `QUOTA`: the ChatGPT plan's Codex limit is used up. Tell the user the reset time shown in the log, and continue with your own review in the meantime.
   - `NETWORK`: allow the hosts above.
4. **Report.**
   - Don't paste Codex's answer blindly. Check each point against the code first, and say which ones you agree with, correct, or reject.
   - Give a short prioritized summary in Japanese, and send the full answer to the user as a file (SendUserFile, `display: attach`).
   - If the user asked to consult Codex **before** starting work, don't start implementing until Codex has answered or the user says to go on without it.

## Prompt template

```
You are reviewing <project / feature> in this repository. Do NOT modify files; this is a read-only review.
Context: <what changed, the user's feedback, relevant files>
Please answer in Japanese:
A. Bugs / risks: cite file:line, the failure scenario, a concrete fix, ranked High/Medium/Low.
B. UX (or design) review: prioritized, each with a short fix.
C. <anything else, e.g. Autodesk Marketplace review risks>
Be concrete and concise.
```

## On the user's own computer

The same scripts work in Git Bash or WSL with `npm install -g @openai/codex`. In PowerShell, run `codex login --device-auth`
(or plain `codex login`, which opens a browser), then
`codex exec --sandbox read-only "<prompt>" < NUL`.
