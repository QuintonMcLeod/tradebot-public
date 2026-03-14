# 41. Remote Setup — Running the Core on One Machine and the GUI on Another

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wait — I can run the bot on one computer and watch it from a completely different one?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yes. And it takes about 90 seconds to set up.<br><br>The bot has two halves — a <b>brain</b> and a <b>face</b>. The brain is the Python engine that does the actual trading. The face is the Electron GUI — the pretty dashboard you stare at. They don't need to be on the same computer. They talk to each other over a WebSocket connection on port 8080. That's it."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Think of it like a kitchen and a dining room, baby. One computer is the kitchen — that's where the cooking happens. The other computer is the dining room — that's where you sit and watch. You don't need to be in the kitchen to enjoy the meal. You just need the waiter to know where the kitchen is."</td></tr></table>

---

## Step 1: Start the Bot on the Server Machine

On the computer that will run the engine, launch the bot the same way you always do — just make sure the WebSocket port isn't blocked by your firewall:

```bash
./scripts/tradebot.sh -p forex_continuous --gui
```

Or headless (no GUI on the server side):

```bash
./scripts/tradebot.sh --daemon -p forex_continuous
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's it for the server. The bot automatically starts a WebSocket server on port 8080 and broadcasts everything — candles, trades, state, holdings — to anyone who connects. It's already doing this. You don't need to configure anything extra."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The GUI will reconnect automatically. One field. One change. Done. You're now watching a bot that's running on a completely different machine. Any OS. Same room or different continent — the WebSocket doesn't care."</td></tr></table>

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
| Start bot (server) | `./scripts/tradebot.sh --daemon -p forex_continuous` |
| Find server IP | `hostname -I \| awk '{print $1}'` |
| Open firewall | `sudo ufw allow 8080/tcp` |
| Set GUI connection | Settings → System → **WebConnect URL** |
| Default URL | `ws://localhost:8080/ws` |
| Remote URL format | `ws://<SERVER_IP>:8080/ws` |
