---
title: 52 The Update Protocol: How the Bot Updates Itself
category: rtfm
icon: system_update
description: '"In the future, software updates itself. We''re living in the future.
  It''s terrifying." How the self-update mechanism works: git fetch, version comparison,
  one-click apply. What gets updated (code), what doesn''t (your config), and why
  your open positions are completely safe during updates. Plus how to roll back if
  you don''t like the new version.'
---

# 52. The Update Protocol — How the Bot Updates Itself

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Update with precision. One wrong move during an update can take the whole system down. Fortunately, we automated the whole thing."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The bot updates itself! You click one button in the GUI. Look at you, you don't even have to open a terminal! No `pip install` garbage, no downloading ZIP files and accidentally deleting system folders. The bot handles it like a grown adult."</td></tr></table>

---

## How the Update Check Works

Every 5 minutes (configurable):

1. **Fetches** latest remote state (`git fetch origin`)
2. **Compares** your local HEAD with remote HEAD
3. **Counts** commits you're behind
4. **Shows a button** if updates are available

Lightweight — it doesn't download code yet. Just asks: "Is there something new?"

---

## How the Update Applies

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"When you click 'Update Available':"</td></tr></table>

1. **Stops** the trading engine (gracefully — waits for current cycle)
2. **Downloads** latest code (`git fetch origin <branch>`)
3. **Resets** local code to match remote (`git reset --hard origin/<branch>`)
4. **Reloads** the GUI with new code

---

## What Gets Updated (And What Doesn't)

| Updated | Not Updated |
|---------|------------|
| Python source (`src/`) | Your config files (`config/`) |
| Electron GUI (`electron_gui/`) | Your `.env` file |
| Strategy logic | Your `data/` directory |
| Documentation | Your log files |
| Scripts and tools | Window preferences |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The update changes the CODE, not your CONFIGURATION. Your API keys, your profiles, your risk settings — those stay safe. We don't wipe your settings. I'm not Microsoft pushing a Windows update."</td></tr></table>

---

## What Happens to Your Positions?

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Nothing. Open positions live at the broker, not in the code. Stop-losses and take-profits are server-side. The bot reconnects and picks up where it left off."</td></tr></table>

---

## Rollback

If an update breaks something (Murphy's Law never sleeps):

```bash
cd /path/to/tradebot-sci
git log --oneline -5           # See recent commits
git reset --hard <old-commit>  # Go back
```

---

## The Trust Model

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"It does NOT auto-update. Because I know you. If the bot changed something while you were grabbing a sandwich, you'd think you were hacked. It shows the button, and it waits for your explicit permission."</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Target</b>. Try to keep up."</td></tr></table>
