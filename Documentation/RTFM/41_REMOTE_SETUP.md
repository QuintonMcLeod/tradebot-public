# 41. Remote Setup — Running the Brain on Linux, the Face on Windows

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"So I got this bot. I got a Linux machine. I got a Windows machine. How do I make them talk to each other? Because right now neither one of them is doing anything useful and honestly I feel like I'm babysitting two toddlers."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Okay. Here's the deal. The bot has two halves — a <b>brain</b> and a <b>face</b>.<br><br>The <b>brain</b> is the Python engine. That's the piece that actually trades. It reads candles. It crunches indicators. It decides whether to enter, exit, or sit on its hands. It runs on Linux because Linux doesn't randomly restart itself at 3 AM to install a Candy Crush update.<br><br>The <b>face</b> is the Electron GUI. The pretty dashboard with the candle chart, the trade history, the Payout Mentor. It's a glorified TV screen for your bot. It runs on Windows because you, a human person, are sitting in front of a Windows machine and you want to <em>see</em> what the bot is doing without SSH'ing into a terminal like a 1997 hacker.<br><br>They talk to each other over a <b>WebSocket</b> — which is basically a phone line that stays open 24/7. The brain broadcasts everything it does over that line. The face listens. That's it. That's the whole architecture."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Think of it like a kitchen and a dining room, baby. The Linux machine is the kitchen — that's where the cooking happens. The Windows machine is the dining room — that's where you sit and eat. You don't need to be in the kitchen to enjoy the meal. You just need someone to carry the plate to you. The WebSocket is that waiter."</td></tr></table>

---

## Part 1: Setting Up the Kitchen (Linux)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The Linux machine is where the real work happens. This is the server. The engine room. The place that never sleeps. Let's set it up."</td></tr></table>

### Step 1: Make Sure You Have the Ingredients

Before we start cooking, we need tools. Open a terminal on your Linux machine and check:

```bash
python3 --version     # Need 3.11 or higher
pip3 --version        # Need pip to install packages
tmux -V               # Need tmux for the dashboard
git --version         # Need git to download the code
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"If any of those commands give you an error, don't panic. Just install them:<br><br><code>sudo apt install python3.11 python3.11-venv python3-pip tmux git</code><br><br>That's it. That's like going to the store and buying flour, eggs, butter, and a pan. Now you can cook."</td></tr></table>

### Step 2: Download the Bot

```bash
cd ~/Scripts
git clone <REPO_URL> tradebot-sci
cd tradebot-sci
```

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"What's <code>&lt;REPO_URL&gt;</code>?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The URL of the Git repository. Ask the person who gave you the bot. If that person is me, I already sent it to you. Check your messages. Check your email. Check your DMs. If you still can't find it, you're not ready for a trading bot. You're not even ready for a toaster."</td></tr></table>

### Step 3: Install the Python Stuff

```bash
cd tradebot-sci
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"That <code>venv</code> thing? That's like putting on an apron before you start cooking. It keeps the mess contained. You don't want your bot's ingredients getting mixed up with your system's ingredients. That's how you get food poisoning. Digital food poisoning."</td></tr></table>

If you're using Poetry instead (fancy chef energy):
```bash
pip install poetry
poetry install
```

### Step 4: Set Up Your API Keys

The bot needs to talk to your broker. Your broker needs to know who you are. That means API keys.

```bash
mkdir -p ~/.config/tradebot-sci
nano ~/.config/tradebot-sci/.env.secrets
```

Put your broker credentials in there:
```env
IBKR_HOST=127.0.0.1
IBKR_PORT=4001

# Or for OANDA:
OANDA_API_KEY=your_key_here
OANDA_ACCOUNT_ID=your_account_id
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"<b>DO NOT</b> share this file with anyone. Ever. Not your girlfriend. Not your homeboy. Not your cat. This file has your broker API keys in it. If someone gets these, they can trade your account. And they will not be trading it in your favor. They will be trading it like a five-year-old at a carnival — wildly and irresponsibly."</td></tr></table>

### Step 5: Configure the Bot

```bash
cp config.json ~/.config/tradebot-sci/config.json
nano ~/.config/tradebot-sci/config.json
```

Make sure these key settings are correct:

```json
{
  "active_profile": "forex_continuous",
  "global": {
    "execute_trades": false,
    "ws_port": 8080
  }
}
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"See that <code>execute_trades: false</code>? That means the bot is in <b>Paper Mode</b>. It makes fake trades with fake money. Keep it that way until you've verified everything works. <br><br>Don't be the guy who sets it to <code>true</code> on day one and wakes up to a margin call. Don't be that guy. That guy cries in the shower. That guy calls his mom at 4 AM. Don't be that guy."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"The <code>ws_port: 8080</code> part? That's the port number. Think of it as the apartment number on your building. Your Linux machine is the building. Port 8080 is the specific door where the Windows GUI knocks to say 'Hey, what's going on in there?' If someone asks you what port the bot uses, you say 8080. Practice saying it. <em>Eight-oh-eight-oh.</em> Good."</td></tr></table>

### Step 6: Start the Bot (Headless)

Now we light the stove. Two options:

**Option A — Daemon Mode** (silent background, no dashboard):
```bash
./scripts/tradebot.sh --daemon -p forex_continuous
```

**Option B — Tmux Dashboard** (recommended, you can see what's happening):
```bash
./scripts/tradebot.sh -p forex_continuous
```

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"What's tmux?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"tmux is a terminal multiplexer. It's like having four TVs in one screen. One shows the bot's decisions. One shows the candle chart. One shows AI commentary. One shows your open positions. And the whole thing survives if you close the terminal window or disconnect your SSH session. It's indestructible. Unlike your portfolio."</td></tr></table>

### Step 7: Verify It's Running

```bash
pgrep -f run_dev_bot && echo "THE BOT IS ALIVE" || echo "HOUSTON WE HAVE A PROBLEM"
```

Then check the WebSocket is listening:
```bash
ss -tlnp | grep 8080
```

You should see something like:
```
LISTEN  0  128  0.0.0.0:8080  0.0.0.0:*  users:(("python3",pid=12345,fd=8))
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"That <code>0.0.0.0</code> means the bot is accepting visitors from <em>any</em> IP address on your network. It's like leaving the front door open for guests. Which is what we want — because the guest is your Windows machine coming over to see the show."</td></tr></table>

### Step 8: Find Your IP Address

```bash
hostname -I | awk '{print $1}'
```

This gives you something like `192.168.1.100`. **Write this down.** You'll need it.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's your Linux machine's address on the network. It's literally the street address of your kitchen. Your Windows machine needs to know where to send the waiter."</td></tr></table>

### Step 9: Open the Firewall

If your Linux machine has a firewall (most do), you need to let port 8080 through:

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 8080/tcp

# Fedora/RHEL (firewalld)
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"A firewall is like a security guard at the door. Right now the guard is blocking everyone, including your Windows machine. You're telling the guard: 'Hey, if anyone comes to door 8080, let them in. They're with me.' The guard nods. Problem solved."</td></tr></table>

---

## Part 2: Setting Up the Dining Room (Windows)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The Windows side is the easy part. You're not running a trading engine here. You're running a fancy TV. All it needs to do is connect to the Linux machine and show you what's happening."</td></tr></table>

### Step 1: Install Node.js

Download and install **Node.js 18+** (LTS) from [https://nodejs.org](https://nodejs.org).

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Node.js is what makes the GUI run. It's like electricity for the TV. Without it, you're staring at a blank screen. Just download it. Click 'Next' a bunch of times. Don't read the terms and conditions. Nobody reads the terms and conditions. They know that. That's why they put the bad stuff in there."</td></tr></table>

Also install **Git for Windows** from [https://git-scm.com/download/win](https://git-scm.com/download/win) if you don't have it.

### Step 2: Clone the Repository

Open **PowerShell** (not Command Prompt — we're professionals here):

```powershell
cd C:\Users\Patrick\Scripts
git clone <REPO_URL> tradebot-sci
cd tradebot-sci
```

### Step 3: Install GUI Dependencies

```powershell
cd src\tradebot_sci\electron_gui
npm install
```

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"It's downloading like 400 packages. Is that normal?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yes. Welcome to JavaScript development. Every project downloads half the internet. Just let it finish. Go get a snack. Come back when it's done. It'll be fine. Probably."</td></tr></table>

### Step 4: Tell the GUI Where the Bot Lives

This is the **most important step**. The GUI defaults to looking for the bot on `localhost` — which means your own Windows machine. But the bot isn't on your Windows machine. It's on your Linux machine. You need to redirect the GUI to the right address.

**Create this folder:**
```powershell
mkdir "$env:USERPROFILE\.config\tradebot-sci"
```

**Create the secrets file:**
```powershell
notepad "$env:USERPROFILE\.config\tradebot-sci\.env.secrets"
```

**Add this single line** (replace the IP with YOUR Linux machine's IP from Step 8 above):
```env
GUI_WS_URL=ws://192.168.1.100:8080/ws
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Read that line carefully, baby. It says: 'Dear GUI, the bot is not here. The bot is at 192.168.1.100, door number 8080. Go there.'<br><br>If you get the IP wrong, the GUI will just sit there spinning like a lost puppy. It's not broken — it's just looking for the bot at the wrong address. Like showing up to a party at the wrong house and wondering why nobody's there."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Make sure you type it exactly. <code>ws://</code> at the front. <code>/ws</code> at the end. The IP in the middle. No extra spaces. No 'http' instead of 'ws'. This is not the URL for your grandma's recipe blog. This is a WebSocket address. Precision matters."</td></tr></table>

### Step 5: Launch the GUI

```powershell
cd C:\Users\Patrick\Scripts\tradebot-sci\src\tradebot_sci\electron_gui
npm start
```

The dashboard should open. Look at the **top-right corner**:

- 🟢 **Green dot** = Connected. You're cooking. The GUI sees the bot. Everything is beautiful.
- 🔴 **Red dot** = Disconnected. Something went wrong. See Troubleshooting below. Don't panic. Panicking never helped anybody do anything except throw up.

### Alternative: Use the Settings UI

If you hate editing text files (no judgment), you can set the bot address through the GUI itself:

1. Launch the GUI with `npm start`
2. Click the **⚙️ Settings** gear icon
3. Scroll all the way down to the **Advanced** section
4. Find **"WebConnect URL"**
5. Change it from `ws://localhost:8080/ws` to `ws://192.168.1.100:8080/ws`
6. Hit Save

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's it. The GUI will reconnect automatically. One field. One change. And suddenly your Windows machine is watching a bot that's running on a completely different computer across the room. Or across the country. Or across the ocean. The WebSocket doesn't care about distance. It just cares about the address."</td></tr></table>

---

## Part 3: When Things Go Wrong (And They Might)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Look. Networking between two machines is one of those things that either works perfectly the first time or makes you question every decision you've ever made in your life. There is no in-between. Here's how to fix the most common problems."</td></tr></table>

### "The GUI says DISCONNECTED"

**Check 1: Is the bot actually running?**
```bash
# On Linux:
pgrep -f run_dev_bot && echo "RUNNING" || echo "NOT RUNNING"
```

If it says NOT RUNNING — start the bot. Problem solved. You were staring at a TV connected to a kitchen with nobody in it.

**Check 2: Is port 8080 open?**
```bash
# On Linux:
ss -tlnp | grep 8080
```

If there's no output, the WebSocket server isn't running. Restart the bot.

**Check 3: Can Windows reach the Linux machine?**
```powershell
# On Windows (PowerShell):
Test-NetConnection -ComputerName 192.168.1.100 -Port 8080
```

If it says `TcpTestSucceeded: True` — your network is fine. The problem is somewhere else.
If it says `TcpTestSucceeded: False` — the firewall is blocking you. Go back to Step 9 in Part 1.

**Check 4: Is the URL correct?**

Open `%USERPROFILE%\.config\tradebot-sci\.env.secrets` and verify it says:
```
GUI_WS_URL=ws://192.168.1.100:8080/ws
```

No typos. No extra spaces. No `http://`. No missing `/ws` at the end.

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Honey, 90% of networking problems are either 'the thing isn't running' or 'you typed the address wrong.' That's it. It's never a cosmic mystery. It's always something simple and embarrassing. Like losing your glasses when they're on your head."</td></tr></table>

### "Chart is empty / no candles showing"

The chart needs the bot to be actively running cycles. If you just started the bot, give it 30-60 seconds. It needs to fetch candles from the broker first.

### "I changed settings on Windows but the bot didn't change"

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Here's the thing. The <code>config.json</code> that the bot reads is on the <b>Linux machine</b> at <code>~/.config/tradebot-sci/config.json</code>. The GUI on Windows writes to the <b>Windows</b> config by default.<br><br>For now, if you need to change bot settings, SSH into the Linux machine and edit the config there directly:<br><br><code>ssh patrick@192.168.1.100</code><br><code>nano ~/.config/tradebot-sci/config.json</code><br><br>Then restart the bot. Yes, I know that's annoying. It's on the roadmap to fix. Life is a journey."</td></tr></table>

### "How do I see the logs from Windows?"

```powershell
# SSH into the Linux machine and tail the log:
ssh patrick@192.168.1.100
tail -f ~/.config/tradebot-sci/logs/tradebot.log
```

---

## Quick Reference Card

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Print this. Tape it to your monitor. Laminate it if you have to."</td></tr></table>

| What | Where |
|------|-------|
| Bot config | `~/.config/tradebot-sci/config.json` (Linux) |
| API keys | `~/.config/tradebot-sci/.env.secrets` (Linux) |
| Bot logs | `~/.config/tradebot-sci/logs/tradebot.log` (Linux) |
| Paper state | `~/.config/tradebot-sci/data/paper_state.json` (Linux) |
| WS URL override | `%USERPROFILE%\.config\tradebot-sci\.env.secrets` (Windows) |
| GUI dependencies | `src\tradebot_sci\electron_gui\node_modules\` |

| Action | Command |
|--------|---------|
| Start bot (daemon) | `./scripts/tradebot.sh --daemon -p forex_continuous` |
| Start bot (tmux) | `./scripts/tradebot.sh -p forex_continuous` |
| Start GUI (Windows) | `cd src\tradebot_sci\electron_gui && npm start` |
| Stop bot | `pkill -f run_dev_bot` |
| Restart bot | `./scripts/tradebot.sh --restart` |
| Check bot status | `pgrep -f run_dev_bot` |
| Check WebSocket | `ss -tlnp \| grep 8080` |
| Find Linux IP | `hostname -I \| awk '{print $1}'` |

---

## The Bottom Line

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Linux runs the brain. Windows displays the face. They talk over WebSocket port 8080. You set one URL in one file. That's it.<br><br>If you can order pizza online, you can do this setup. The pizza app is harder. At least the bot doesn't ask you to choose between stuffed crust and thin crust. The bot doesn't have existential crises about toppings."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"And remember, baby — if you get stuck, re-read this manual. The answer is in here somewhere. It always is. That's why they call it RTFM."</td></tr></table>
