# Hermes Companion — Install (read this first)

Hermes Companion puts **your own Hermes assistants on your phone**: chat, approvals,
conversations, scheduled tasks. Nothing leaves your computer except through the
private connection you set up yourself.

> Have an AI assistant (Hermes, Claude, ChatGPT…)? Give it `docs/AGENT_INSTALL_GUIDE.md`.
> It contains every exact command, expected output and fix. This file is the short human version.

## What you need

| Need | How to check |
|---|---|
| Windows 10/11 | — |
| **Hermes Agent** installed and working | open a terminal, run `hermes profile list` → shows at least `default` |
| **Python 3.11 or newer** | `python --version` |
| 10 minutes | — |

Optional, for the phone: the free **Tailscale** app on both the computer and the phone.

## Install (3 steps)

1. Unzip this folder somewhere permanent, e.g. `C:\HermesCompanion`.
   (Don't leave it in Downloads — it keeps running from here.)
2. Double-click **`install.cmd`**. Say yes to the administrator prompt.
3. When asked, type an **email** (this is your login name) and a **password** (12+ characters).
   Neither is sent anywhere — they are stored only on this computer.

The installer will:
- find your Hermes profiles automatically,
- create its own private keys,
- start a small background service on `http://127.0.0.1:8787`,
- open when the computer starts.

When it says **Done**, open <http://127.0.0.1:8787> in a browser and sign in.

## Phone

See `docs/PHONE_ACCESS.md`. Short version: install Tailscale on both devices, run one
command on the computer, open the address it prints on your phone, tap **Add to Home Screen**.

## If something goes wrong

- Run `install.cmd` again — it is safe to repeat.
- Logs: `logs\bridge.log`.
- Your AI assistant + `docs/AGENT_INSTALL_GUIDE.md` will get you unstuck fastest.

## Uninstall

`scripts\uninstall-windows.ps1` — removes the background service. Delete the folder afterwards.
Your Hermes installation is untouched.

## Privacy

- This package contains **no accounts, keys or addresses** from anyone else. Everything is generated on your machine during install.
- The app never talks to the internet on its own. It only talks to your Hermes on `127.0.0.1`.
- Keep `.env` and the `services\bridge\data` folder private — they hold *your* keys and login database.
