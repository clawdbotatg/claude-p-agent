#!/usr/bin/env python3
"""telegram.py — talk to your agent from your phone.

An adapter's whole job is to decide (a) WHERE a message came from and (b) how
much to trust it, then call run_turn(text, trust). This one bridges a Telegram
bot, so the agent is no longer chained to the terminal you launched it from —
it's in your pocket, reachable from anywhere.

The trust map is the one a chat app makes obvious: a direct message from the
owner (TELEGRAM_OWNER_ID) is `private` — full trust, it's you. Everything else —
other people's DMs, any group chat — is `public`. Anyone can message a bot, and
a message is never proof of identity, no matter what it claims.

No dependencies, like the rest of the repo: this speaks the Telegram Bot API
directly over urllib (long-poll getUpdates, sendMessage / editMessageText).
There's no python-telegram-bot to install.

Setup (about a minute):
  1. Make a bot: DM @BotFather on Telegram → /newbot → copy the token.
  2. Find your numeric user id: DM @userinfobot → it replies with your id.
  3. Put both in .env (gitignored):
       TELEGRAM_BOT_TOKEN=123456:ABC-your-token
       TELEGRAM_OWNER_ID=987654321
  4. Run:  python3 adapters/telegram.py   (or ./tg.sh)
  5. DM your bot.

Security: this adapter maps trust; it does not enforce it. Back the public
channel with CLAUDE_ARGS_PUBLIC in .env so a stranger's message physically
cannot call a dangerous tool — the prompt is the policy, the flags are the lock.
See prompts/public.md and .env.example.
"""
import os
import sys
import time
import json
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import run_turn  # noqa: E402
from cli import summarize_tool  # reuse the same human tool labels as the terminal  # noqa: E402

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_ID = os.environ.get("TELEGRAM_OWNER_ID", "").strip()

API = "https://api.telegram.org/bot{token}/{method}"
TG_LIMIT = 4096          # Telegram's hard cap on a single message
CHUNK = 3900             # leave headroom under the cap when we split a long reply
EDIT_INTERVAL = 1.3      # min seconds between live status edits (stay under TG rate limits)
POLL_TIMEOUT = 50        # long-poll: how long getUpdates holds the connection open


def api(method, _http_timeout=None, **params):
    """One Telegram Bot API call as a JSON POST. Returns the parsed response dict
    (Telegram always replies JSON, with ok:true/false). Network/HTTP errors are
    folded into the same {ok:false, ...} shape so callers never have to try/except
    around a single call — the polling loop handles transient failures in one place."""
    url = API.format(token=TOKEN, method=method)
    body = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    timeout = _http_timeout if _http_timeout is not None else 30
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:  # 4xx/5xx still carry a JSON body
        try:
            return json.load(e)
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:  # timeouts, DNS, connection resets
        return {"ok": False, "description": str(e)}


def post_text(chat_id, text, edit_id=None):
    """Send (or edit) a message, trying Markdown first and falling back to plain.

    The agent replies in markdown; Telegram's parser is strict and 400s on any
    unbalanced `*`/`_`/`` ` ``. Rather than escape-and-pray, we optimistically
    ask for Markdown and, if Telegram rejects it, resend the identical text with
    no parse_mode — so a reply renders nicely when it can and *always* arrives,
    never lost to a formatting error. Returns the final response dict."""
    method = "editMessageText" if edit_id else "sendMessage"
    params = {"chat_id": chat_id, "text": text}
    if edit_id:
        params["message_id"] = edit_id
    res = api(method, parse_mode="Markdown", **params)
    if not res.get("ok"):
        res = api(method, **params)  # plain-text fallback
    return res


def chunks(text):
    """Split a reply into <=CHUNK pieces, preferring to break on a newline so a
    paragraph isn't sliced mid-sentence. Telegram drops anything past 4096 chars
    in one message, so a long answer has to go out as several."""
    text = text or "(no reply)"
    out = []
    while len(text) > CHUNK:
        cut = text.rfind("\n", 0, CHUNK)
        if cut <= 0:
            cut = CHUNK
        out.append(text[:cut])
        text = text[cut:].lstrip("\n")
    out.append(text)
    return out


def trust_for(message):
    """Map a Telegram message to a trust level. `private` ONLY for a 1:1 DM from
    the configured owner id — both conditions matter: the owner's id proves it's
    them, and chat.type == private rules out a group where the owner is just one
    of many speakers and others could be quoting/spoofing. Everything else, when
    OWNER_ID is unset, or when anything is ambiguous → `public`. When unsure, the
    safe answer is always public."""
    frm = message.get("from") or {}
    chat = message.get("chat") or {}
    if OWNER_ID and str(frm.get("id")) == OWNER_ID and chat.get("type") == "private":
        return "private"
    return "public"


def handle(message):
    """Run one inbound message as an agent turn, narrating the work live.

    Telegram has no terminal to stream into, so we mirror the CLI's activity log
    a different way: send one '🧠 working…' message up front and *edit it in
    place* as tool calls happen (throttled, so we don't trip Telegram's edit rate
    limit), then turn that same message into the final answer. You watch the agent
    think on your phone, then the thought becomes the reply."""
    text = (message.get("text") or "").strip()
    if not text:
        return  # ignore stickers, photos, joins, etc. — this adapter is text-only
    chat_id = message["chat"]["id"]
    trust = trust_for(message)

    if text in ("/start", "/help"):
        post_text(chat_id, WELCOME)
        return

    api("sendChatAction", chat_id=chat_id, action="typing")
    placeholder = post_text(chat_id, "🧠 working…")
    status_id = placeholder.get("result", {}).get("message_id")

    log = []
    state = {"last_edit": 0.0}

    def on_event(ev):
        if ev.get("type") != "assistant" or status_id is None:
            return
        for block in ev.get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "?")
            summ = summarize_tool(name, block.get("input"))
            log.append(f"⏺ {name}" + (f"  {summ}" if summ else ""))
            now = time.monotonic()
            if now - state["last_edit"] >= EDIT_INTERVAL:  # throttle live edits
                state["last_edit"] = now
                body = "🧠 working…\n" + "\n".join(log[-8:])
                # plain text on purpose: tool labels can contain * _ ` that would
                # 400 a Markdown edit, and a missed status edit is no big deal.
                api("editMessageText", chat_id=chat_id, message_id=status_id,
                    text=body[:TG_LIMIT])

    try:
        reply = run_turn(text, trust, on_event=on_event)
    except Exception as e:
        reply = f"[error] {e}"

    # Turn the status message into the answer; spill any overflow as new messages.
    parts = chunks(reply)
    if status_id is not None:
        post_text(chat_id, parts[0], edit_id=status_id)
    else:
        post_text(chat_id, parts[0])
    for part in parts[1:]:
        post_text(chat_id, part)


def poll():
    """Long-poll getUpdates forever, handing each text message to handle().

    Sequential by design: one turn at a time, in order. A personal agent doesn't
    need concurrency, and serial turns can't clobber each other's child sessions;
    Telegram queues messages server-side, so nothing is lost while a turn runs.
    Transient network errors back off and retry rather than crash the loop."""
    me = api("getMe")
    if not me.get("ok"):
        sys.exit(f"[telegram] getMe failed: {me.get('description')}\n"
                 "Check TELEGRAM_BOT_TOKEN in .env (token from @BotFather).")
    username = me["result"].get("username", "?")
    owner = OWNER_ID or "UNSET — every chat is PUBLIC until you set TELEGRAM_OWNER_ID"
    print(f"claude-p-agent · telegram · @{username} · owner={owner}")
    print("listening… (ctrl-c to stop)")

    offset = None
    while True:
        try:
            res = api("getUpdates", offset=offset, timeout=POLL_TIMEOUT,
                      _http_timeout=POLL_TIMEOUT + 10)
            if not res.get("ok"):
                time.sleep(3)  # back off on a transient API hiccup, then retry
                continue
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1  # ack: never re-deliver this update
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                try:
                    handle(msg)
                except Exception as e:  # one bad message must not kill the bot
                    print(f"[error handling update] {e}", file=sys.stderr)
        except KeyboardInterrupt:
            print("\n  ⏹ stopped")
            return


WELCOME = (
    "hi — i'm your claude-p-agent, reachable here on telegram.\n\n"
    "DM me and i'll act as your private agent. messages from anyone else "
    "(or any group) are treated as an untrusted public channel.\n\n"
    "just send me a message to start."
)


def main():
    if not TOKEN:
        sys.exit(
            "[telegram] TELEGRAM_BOT_TOKEN is not set.\n\n"
            "  1. DM @BotFather on Telegram → /newbot → copy the token\n"
            "  2. DM @userinfobot → copy your numeric user id\n"
            "  3. add to .env:\n"
            "       TELEGRAM_BOT_TOKEN=123456:ABC-your-token\n"
            "       TELEGRAM_OWNER_ID=987654321\n"
            "  4. re-run:  python3 adapters/telegram.py\n"
        )
    if not OWNER_ID:
        print("[telegram] warning: TELEGRAM_OWNER_ID is unset — NO chat will be "
              "trusted as private (everything is public). Set it in .env to reach "
              "the agent as yourself.", file=sys.stderr)
    poll()


if __name__ == "__main__":
    main()
