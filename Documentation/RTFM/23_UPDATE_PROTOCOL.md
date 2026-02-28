# 23. The Update Protocol — How the Bot Updates Itself

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Update with precision. One wrong move during an update can take the whole system down. Fortunately, we automated the whole thing."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The bot has a self-update mechanism. It checks for newer versions, shows a button in the GUI, and applies the update with one click. No `apt-get`. No `pip install`. No downloading a ZIP file and praying you put it in the right folder."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The update changes the CODE, not your CONFIGURATION. API keys, profiles, risk settings, trading history — never touched."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"No auto-updates happen without your explicit click. The bot shows you the button and waits. You're always in control."</td></tr></table>
