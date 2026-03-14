# 41. Remote Setup — Running the Core on One Machine and the GUI on Another

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wait — I can run the bot on one computer and watch it from a completely different one?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yes. And it's not even complicated. The bot was <em>designed</em> to work this way.<br><br>Here's the deal. The bot has two halves — a <b>brain</b> and a <b>face</b>.<br><br>The <b>brain</b> is the Python engine. That's the piece that actually trades. It reads candles. It crunches indicators. It decides whether to enter, exit, or sit on its hands. It runs as a background process on whatever computer you want — your desktop, a server in your closet, a VPS in the cloud, a Raspberry Pi duct-taped to your ceiling fan. It doesn't care. It just needs Python and an internet connection.<br><br>The <b>face</b> is the Electron GUI. The pretty dashboard with the candle chart, the trade history, the Payout Mentor. It's a glorified TV screen for your bot. It can run on <em>any</em> other computer — same network, different network, across the room, across the country.<br><br>They talk to each other over a <b>WebSocket</b> — which is basically a phone line that stays open 24/7. The brain broadcasts everything it does over that line. The face listens. That's it. That's the whole architecture."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Think of it like a kitchen and a dining room, baby. One computer is the kitchen — that's where the cooking happens. The other computer is the dining room — that's where you sit and eat. You don't need to be in the kitchen to enjoy the meal. You just need someone to carry the plate to you. The WebSocket is that waiter."</td></tr></table>

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"So I could run the bot on a beast PC in my office and watch trades from my laptop on the couch?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yes. Or run it on a Linux server and watch it from your Windows gaming rig. Or run it on a Mac Mini and watch it from a Chromebook. Or run it on a cloud VPS and watch it from your phone's browser. The brain doesn't care who's watching. It trades whether you're watching or not. Like a microwave. It heats your food whether or not you stand there staring at it through the little window."</td></tr></table>

---

## How It Works (The 30-Second Version)

```
┌──────────────────────────┐              ┌─────────────────────────────┐
│    COMPUTER A (Core)     │              │    COMPUTER B (GUI)         │
│                          │   WebSocket  │                             │
│  Python Engine (daemon)  │◄────────────►│   Electron Dashboard        │
│  Broadcasts on port 8080 │   Port 8080  │   Connects to Computer A    │
│                          │              │                             │
│  Config, logs, state     │              │  Just needs Node.js +       │
│  all live HERE           │              │  one URL to connect         │
└──────────────────────────┘              └─────────────────────────────┘
```

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The Python engine starts a WebSocket server on port 8080, bound to <code>0.0.0.0</code> — which means it accepts connections from any IP address on the network. The Electron GUI just needs to know the IP address of Computer A to connect. One setting. One line. That's the entire setup."</td></tr></table>

---

## Part 1: Setting Up Computer A (The Kitchen — Where the Bot Runs)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This is the computer that does the actual work. It runs the Python engine 24/7. Pick a machine that's reliable, stays on, and has a decent internet connection. This can be any OS — Linux, macOS, Windows, whatever. As long as Python runs on it, the bot runs on it."</td></tr></table>

### Step 1: Install Prerequisites

You need **Python 3.11+**, **pip**, and **git**. If you're on Linux, you probably also want **tmux** for the terminal dashboard.

| Tool | How to Check | How to Install |
|------|-------------|----------------|
| Python 3.11+ | `python3 --version` | Your OS package manager, or [python.org](https://python.org) |
| pip | `pip3 --version` | Usually comes with Python |
| git | `git --version` | Your OS package manager, or [git-scm.com](https://git-scm.com) |
| tmux (optional) | `tmux -V` | `apt install tmux` / `brew install tmux` |

### Step 2: Clone and Install

```bash
cd ~/Scripts
git clone <REPO_URL> tradebot-sci
cd tradebot-sci

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate    # Linux/Mac
# .venv\Scripts\activate     # Windows

# Install
pip install -e .
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"That <code>venv</code> thing? That's like putting on an apron before you start cooking. It keeps the mess contained. You don't want your bot's ingredients getting mixed up with your system's ingredients. That's how you get food poisoning. Digital food poisoning."</td></tr></table>

### Step 3: Configure API Keys

```bash
mkdir -p ~/.config/tradebot-sci
nano ~/.config/tradebot-sci/.env.secrets
```

> **Windows equivalent path:** `%USERPROFILE%\.config\tradebot-sci\.env.secrets`

Add your broker credentials:
```env
IBKR_HOST=127.0.0.1
IBKR_PORT=4001

# Or for OANDA:
OANDA_API_KEY=your_key_here
OANDA_ACCOUNT_ID=your_account_id
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"<b>DO NOT</b> share this file with anyone. Ever. Not your girlfriend. Not your homeboy. Not your cat. This file has your broker API keys. If someone gets these, they can trade your account. And they will not be trading it in your favor. They will be trading it like a five-year-old at a carnival — wildly and irresponsibly."</td></tr></table>

### Step 4: Verify the Config

Make sure your `config.json` has the WebSocket port set:

```json
{
  "active_profile": "forex_continuous",
  "global": {
    "execute_trades": false,
    "ws_port": 8080
  }
}
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"The <code>ws_port: 8080</code> part? That's the apartment number. Your computer is the building. Port 8080 is the specific door where the GUI knocks to say 'Hey, what's going on in there?' If someone asks you what port the bot uses, you say 8080. Practice saying it. <em>Eight-oh-eight-oh.</em> Good."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"And keep <code>execute_trades: false</code> until you've verified everything works. Don't be the guy who sets it to <code>true</code> on Day 1 and wakes up to a margin call. That guy cries in the shower."</td></tr></table>

### Step 5: Start the Bot

**Option A — Daemon Mode** (headless, runs in the background):
```bash
./scripts/tradebot.sh --daemon -p forex_continuous
```

**Option B — Tmux Dashboard** (recommended — you can see logs, candles, commentary):
```bash
./scripts/tradebot.sh -p forex_continuous
```

### Step 6: Verify It's Running

```bash
# Check the process is alive
pgrep -f run_dev_bot && echo "BOT IS ALIVE" || echo "BOT IS NOT RUNNING"

# Check the WebSocket is listening on port 8080
ss -tlnp | grep 8080
```

You should see something like:
```
LISTEN  0  128  0.0.0.0:8080  0.0.0.0:*
```

That `0.0.0.0` means the bot is accepting visitors from any IP on your network.

### Step 7: Find This Computer's IP Address

```bash
# Linux/Mac:
hostname -I | awk '{print $1}'

# Windows (PowerShell):
(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch 'Loopback' }).IPAddress
```

This gives you something like `192.168.1.100`. **Write this down.** This is the address you'll need for Computer B.

### Step 8: Make Sure the Firewall Isn't Blocking Port 8080

```bash
# Linux (ufw):
sudo ufw allow 8080/tcp

# Linux (firewalld):
sudo firewall-cmd --add-port=8080/tcp --permanent && sudo firewall-cmd --reload

# macOS: System Settings → Network → Firewall → allow port 8080

# Windows: Windows Defender Firewall → Inbound Rules → New Rule → Port → 8080 → Allow
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"A firewall is like a security guard at the front door. Right now the guard is blocking everyone, including your other computer. You're telling the guard: 'Hey, if anyone comes to door 8080, let them in. They're with me.' The guard nods. Problem solved."</td></tr></table>

---

## Part 2: Setting Up Computer B (The Dining Room — Where You Watch)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This is the easy side. You're not running a trading engine here. You're running a fancy TV. All it needs to do is connect to Computer A and show you what's happening. This can be <em>any</em> computer with Node.js installed."</td></tr></table>

### Step 1: Install Node.js

Download and install **Node.js 18+** (LTS) from [https://nodejs.org](https://nodejs.org).

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Node.js is what makes the GUI run. It's like electricity for the TV. Without it, you're staring at a blank screen. Just download it. Click 'Next' a bunch of times. It'll be fine."</td></tr></table>

### Step 2: Clone and Install GUI Dependencies

```bash
git clone <REPO_URL> tradebot-sci
cd tradebot-sci/src/tradebot_sci/electron_gui
npm install
```

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"It's downloading like 400 packages. Is that normal?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yes. Welcome to JavaScript. Every project downloads half the internet. Go get a snack. Come back when it's done."</td></tr></table>

### Step 3: Point the GUI at Computer A

This is the **most important step**. By default, the GUI looks for the bot on `localhost` — meaning the same computer. But the bot is on Computer A, not here. You need to redirect the GUI.

**Create your local secrets file:**

| OS | Path |
|----|------|
| Linux/Mac | `~/.config/tradebot-sci/.env.secrets` |
| Windows | `%USERPROFILE%\.config\tradebot-sci\.env.secrets` |

**Add this single line** (replace the IP with Computer A's IP from Part 1, Step 7):
```env
GUI_WS_URL=ws://192.168.1.100:8080/ws
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Read that line carefully, baby. It says: 'Dear GUI, the bot is not here. The bot is at 192.168.1.100, door number 8080. Go there.'<br><br>If you get the IP wrong, the GUI will just sit there spinning like a lost puppy. It's not broken — it's just looking at the wrong address. Like showing up to a party at the wrong house and wondering why nobody's there."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Make sure you type it exactly. <code>ws://</code> at the front. <code>/ws</code> at the end. The IP in the middle. No spaces. No <code>http://</code> instead of <code>ws://</code>. This is a WebSocket address. Precision matters."</td></tr></table>

### Step 4: Launch the GUI

```bash
cd tradebot-sci/src/tradebot_sci/electron_gui
npm start
```

Look at the **top-right corner** of the dashboard:

- 🟢 **Green dot** = Connected. The GUI sees the bot. Everything is beautiful.
- 🔴 **Red dot** = Disconnected. See Troubleshooting below.

### Alternative: Set the URL Through the GUI

If you prefer clicking over typing:

1. Launch the GUI with `npm start`
2. Click the **⚙️ Settings** gear icon
3. Scroll to the **Advanced** section
4. Find **"WebConnect URL"**
5. Change it from `ws://localhost:8080/ws` to `ws://192.168.1.100:8080/ws`
6. Save — the GUI reconnects automatically

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"One field. One change. And suddenly your computer is watching a bot running on a completely different machine. Across the room. Across the country. Across the ocean. The WebSocket doesn't care about distance. It just cares about the address."</td></tr></table>

---

## Part 3: When Things Go Wrong

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Networking between two machines is one of those things that either works perfectly the first time or makes you question every life decision you've ever made. There is no in-between. Here's the cheat sheet."</td></tr></table>

### "The GUI says DISCONNECTED"

Run through these checks in order. Stop as soon as you find the problem:

**1. Is the bot running on Computer A?**
```bash
pgrep -f run_dev_bot && echo "RUNNING" || echo "NOT RUNNING"
```

**2. Is port 8080 listening?**
```bash
ss -tlnp | grep 8080
```

**3. Can Computer B reach Computer A?**
```bash
# From Computer B:
# Linux/Mac:
nc -zv 192.168.1.100 8080

# Windows (PowerShell):
Test-NetConnection -ComputerName 192.168.1.100 -Port 8080
```

If it can't connect, the firewall is blocking you. Go back to Part 1, Step 8.

**4. Is the URL correct?**

Check your `.env.secrets` file on Computer B. It should read exactly:
```
GUI_WS_URL=ws://192.168.1.100:8080/ws
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Honey, 90% of networking problems are either 'the thing isn't running' or 'you typed the address wrong.' That's it. It's never a cosmic mystery. It's always something simple and embarrassing. Like losing your glasses when they're on your head."</td></tr></table>

### "Chart is empty / no candles"

The chart needs the bot to be actively running cycles. If you just started the bot, give it 30-60 seconds to fetch candles from the broker.

### "Settings I change on Computer B don't affect the bot"

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The <code>config.json</code> that the bot reads lives on <b>Computer A</b>. The GUI on Computer B writes to a <em>local</em> config. For now, if you need to change bot settings, SSH into Computer A (or walk over to it) and edit the config there directly. Then restart the bot."</td></tr></table>

---

## Quick Reference Card

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Print this. Tape it to your monitor. Laminate it if you have to."</td></tr></table>

| What | Where |
|------|-------|
| Bot config | `~/.config/tradebot-sci/config.json` (Computer A) |
| API keys | `~/.config/tradebot-sci/.env.secrets` (Computer A) |
| Bot logs | `~/.config/tradebot-sci/logs/tradebot.log` (Computer A) |
| WS URL override | `~/.config/tradebot-sci/.env.secrets` (Computer B) |

| Action | Command |
|--------|---------|
| Start bot (daemon) | `./scripts/tradebot.sh --daemon -p forex_continuous` |
| Start bot (tmux) | `./scripts/tradebot.sh -p forex_continuous` |
| Start GUI | `cd src/tradebot_sci/electron_gui && npm start` |
| Stop bot | `pkill -f run_dev_bot` |
| Restart bot | `./scripts/tradebot.sh --restart` |
| Check bot status | `pgrep -f run_dev_bot` |
| Check WebSocket | `ss -tlnp \| grep 8080` |
| Find your IP | `hostname -I \| awk '{print $1}'` |

---

## The Bottom Line

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"One computer runs the brain. Another computer displays the face. They talk over WebSocket port 8080. You set one URL in one file on the GUI machine. That's the entire setup.<br><br>Any OS. Any two machines. Could be two desktops sitting next to each other. Could be a cloud server and a laptop on a beach. The bot doesn't care. It trades. The GUI watches. They communicate over a single port. Simple as ordering pizza — except the bot doesn't ask you about toppings."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"And remember, baby — if you get stuck, re-read this manual. The answer is in here somewhere. It always is. That's why they call it RTFM."</td></tr></table>
