# 41. Remote Setup — Running the Core on One Machine and the GUI on Another

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wait — I can run the bot on one computer and watch it from a completely different one?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yes! And it takes 90 seconds! Are you people allergic to convenience? The bot has a brain, and it has a face. The brain trades. The face is the pretty little dashboard you drool over. They don't need to be in the same room! They talk over a WebSocket! It's not magic, it's basic networking!"</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Think of it like a kitchen and a dining room, baby. One computer is the kitchen — that's where the cooking happens. The other computer is the dining room — that's where you sit and watch. You don't need to be in the kitchen to enjoy the meal. You just need the waiter to know where the kitchen is."</td></tr></table>

---

## Step 1: Start the Bot on the Server Machine

On the computer that will run the engine, launch the bot the same way you always do — just make sure the WebSocket port isn't blocked by your firewall:

```bash
./scripts/tradebot.sh --gui
```

Or headless (no GUI on the server side):

```bash
./scripts/tradebot.sh --daemon
```

The `-p` flag lets you pick which trading profile to use (e.g. `-p forex_continuous`, `-p crypto_247`). **You don't need it** — the bot reads the active profile from `config.json`, and you can switch profiles anytime through the GUI's **Profiles** tab. The `-p` flag just overrides it from the command line if you want to.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's it! The server part is done! The bot turns on, starts yelling all its data on port 8080, and anyone can listen! You don't have to configure anything! I already did the hard part so you don't have to think!"</td></tr></table>

Before moving on, grab the server's IP address:

```bash
hostname -I | awk '{print $1}'
```

Write it down. Something like `192.168.1.100`. You'll need it in the next step.

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"If the firewall is blocking port 8080, open it up. On Ubuntu that's <code>sudo ufw allow 8080/tcp</code>. On most home networks, this isn't an issue. If in doubt, run <code>ss -tlnp | grep 8080</code> and make sure you see <code>LISTEN</code>. If you see it listening, you're golden."</td></tr></table>

---

## Step 2: Point the GUI at the Server

On the computer where you want to **watch** the dashboard:

1. Launch the GUI normally (`npm start` from the `electron_gui` folder, or however you usually open it)
2. Click the **⚙️ Settings** gear icon
3. Go to the **System** tab
4. Find **"WebConnect URL"**
5. Change it from `ws://localhost:8080/ws` to:

```
ws://192.168.1.100:8080/ws
```

*(Replace `192.168.1.100` with your server's actual IP from Step 1)*

6. Save

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"One field! You change ONE field! And it works! You're now watching your money being managed by a robot in another room... or another country! The WebSocket doesn't care! It's beautiful, isn't it? Just don't type the IP wrong."</td></tr></table>

---

## Troubleshooting

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"If the GUI shows a red dot (disconnected), it's always one of three things, baby:"</td></tr></table>

| Problem | Fix |
|---------|-----|
| Bot isn't running on the server | Start it. `pgrep -f run_dev_bot` tells you if it's alive. |
| Wrong IP in the WebConnect URL | Double-check `hostname -I` on the server. Make sure you typed it right. |
| Firewall blocking port 8080 | Open it: `sudo ufw allow 8080/tcp` (Linux) or add an inbound rule for port 8080 (Windows/Mac). |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"90% of connection problems are 'the bot isn't running' or 'you typed the IP wrong.' It's never a mystery. It's always something embarrassing."</td></tr></table>

---

## Quick Reference

| Action | Command / Location |
|--------|-------------------|
| Start bot (server) | `./scripts/tradebot.sh --daemon` |
| Find server IP | `hostname -I \| awk '{print $1}'` |
| Open firewall | `sudo ufw allow 8080/tcp` |
| Set GUI connection | Settings → System → **WebConnect URL** |
| Default URL | `ws://localhost:8080/ws` |
| Remote URL format | `ws://<SERVER_IP>:8080/ws` |


> [!NOTE]
> **APRIL 2026 UI & VITALS UPDATE:**  
> Listen up, you degenerates. We just dropped a massive update to the UI and Nurse's Station. The tooltips now trigger when you hover over the *entire goddamn card*, so your fat thumbs can't miss them anymore. The Exit Logic tab is now a clean, idiot-proof single column. We also fixed the Nurse's Station connection tracker—no more lying to you that the bot is dead when it's actively retrying to connect. Read **47_UI_OVERHAUL_AND_VITALS.md** for the full breakdown before you touch the controls and blow your account.
