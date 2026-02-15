
# 23. The Update Protocol (How the Bot Updates Itself)
> *"In the future, software updates itself. We're living in the future. It's terrifying."*

The bot has a self-update mechanism. It checks if a newer version is available on the remote repository, shows a button in the GUI, and applies the update with one click.

No `apt-get`. No `pip install`. No downloading a ZIP file and praying you put it in the right folder. Just click the button.

---

## How the Update Check Works

Every 5 minutes (configurable), the bot:

1. **Fetches** the latest remote repository state (`git fetch origin`)
2. **Compares** your local HEAD commit with the remote branch HEAD
3. **Counts** how many commits you're behind
4. **Shows a button** if updates are available

This check is lightweight — it doesn't download code yet. It just asks: "Is there something new?"

---

## How the Update Applies

When you click the "Update Available" button:

1. **The bot stops** the trading engine (gracefully — it waits for the current cycle to finish)
2. **Downloads** the latest code from the remote (`git fetch origin <branch>`)
3. **Resets** the local code to match the remote (`git reset --hard origin/<branch>`)
4. **Reloads** the GUI with the new code

The update is designed to be **download-only**. It treats your local repository as a read-only copy of the remote. Any local file changes (like `window-state.json` or your config) won't conflict with the update.

---

## What Gets Updated

| Updated | Not Updated |
|---------|------------|
| Python source code (`src/`) | Your config files (`config/`) |
| Electron GUI code (`electron_gui/`) | Your `.env` file |
| Strategy logic | Your `data/` directory |
| Documentation | Your log files |
| Scripts and tools | Your window size/position preferences |

The update changes the **code**, not your **configuration.** Your API keys, profiles, risk settings, and trading history are never touched.

---

## What Happens to Your Positions?

**Nothing.** Open positions live at the broker, not in the bot's code. If the bot restarts after an update, your positions are still there. The stop-losses and take-profits are server-side at the broker. The bot will reconnect and pick up where it left off.

---

## Rollback: "I Don't Like the New Version"

If an update breaks something (it shouldn't, but Murphy's Law never sleeps):

```bash
cd /path/to/tradebot-sci
git log --oneline -5           # See recent commits
git reset --hard <old-commit>  # Go back to the old version
```

That's it. Git makes rollbacks trivial.

---

## Why Not Just Use pip?

Because pip would only update the Python packages, not the Electron GUI, the scripts, the documentation, or the strategy configs. The bot isn't distributed as a pip package — it's distributed as a repository. A `git pull` updates everything atomically.

---

## The Trust Model

The update comes from the same Git remote you cloned from. You're trusting the same source you trusted when you first installed the bot. If that trust model works for your initial install, it works for updates too.

No auto-updates happen without your explicit click. The bot will never update itself in the background. It shows you the button and waits for your decision. You're always in control.
