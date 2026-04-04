---
title: First Time? Here's How to Set Up the Bot & Launch Your First Trade
category: guide
icon: rocket_launch
description: "Brand new? This walks you through everything \u2014 connecting your\
  \ broker, picking a profile, setting your risk, and pressing the start button for\
  \ the very first time. Step by step. No experience needed."
featured: true
---

# First Time? Read This Or Stay Poor

<table><tr><td width="170"><img src="RTFM/img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Okay, I downloaded the bot. Now what? Do I just... press 'Go'? Where's the 'Make Money' button?"</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"There is no 'Make Money' button. If there was a 'Make Money' button, you think I'd be sitting here EXPLAINING things to you? I'd be on a beach somewhere, pressing the button repeatedly like a crack addict with a Staples Easy Button.<br><br>No. This is real. And real things require a little bit of effort. Not a LOT of effort — we're not building a deck here — but enough effort that you need to actually READ something for once in your adult life. Sound good? Good. Let's go."</td></tr></table>

---

## 🔌 Step 1: Plug In Your Money (Brokers)

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"First things first: the bot needs access to a place where money lives. That place is called a BROKER. Think of it like this — the bot is a professional chef. The broker is the kitchen. You can't cook without a kitchen, and the bot can't trade without a broker.<br><br>Go to <b>Settings</b> (the gear icon — yeah, the one that looks like a gear, because it IS a gear) and click <b>Brokers</b>."</td></tr></table>

### 💱 Forex: OANDA (Start Here If You Have No Idea What You're Doing)

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"OANDA is the easiest broker on the planet. If you can order something on Amazon, you can set up OANDA. I'm not even exaggerating. My mother could do this, and my mother thinks 'the cloud' is an actual cloud."</td></tr></table>

1. Go to [oanda.com](https://www.oanda.com) and make a **live** account. Choose **fxTrade** (not fxTrade Practice).
2. Once you're in, go to Account Settings → **Manage API Access** → Generate a Personal Access Token.
3. In the bot: **Settings** → **Brokers** → **OANDA** section:
   - **Account ID**: Your sub-account number (looks like `101-001-XXXXXXX-XXX`)
   - **API Key**: That huge ugly string of letters and numbers you just generated
   - **Environment**: `live`
4. Click **Save**. If you see `[INFO] Connected to OANDA (live)` in the logs, congratulations — you didn't screw it up. ✅

<table><tr><td width="170"><img src="RTFM/img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wait — live? I don't wanna risk real money yet! Can't I use a practice account?"</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"I hear you, and I respect the caution. But here's the thing nobody tells you: OANDA's practice account API is broken. Not 'kinda broken' — BROKEN broken. It can't pull the candle data the bot needs to look at charts and do math. It's like hiring a financial advisor and then blindfolding them. Useless.<br><br>Use a LIVE account for the connection. If you're scared of losing real money — and you SHOULD be a little scared, fear is healthy — just toggle on the bot's built-in <b>Paper Trading</b> mode. Settings → turn off 'Execute Trades.' Now the bot uses OANDA's real data but trades with Monopoly money. Best of both worlds. Real charts, fake risk."</td></tr></table>

### 🪙 Crypto: Gemini / Coinbase / Kraken

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If crypto is your thing, go to your exchange and generate API keys. Here's the ONE thing I need you to hear:<br><br><b>Only enable 'Trading' permissions.</b> Do NOT — and I mean do NOT — enable 'Withdrawals.' The bot doesn't need the ability to wire your money somewhere. If you enable withdrawals, you're basically giving a stranger the keys to your house and saying 'I trust you, take whatever you want.' Don't be that person.<br><br>In the bot: <b>Settings</b> → <b>Brokers</b> → <b>CCXT</b>. Pick your exchange, paste the Key and Secret, hit <b>Save</b>. Done."</td></tr></table>

### 📉 Stocks & Futures: Interactive Brokers (IBKR)

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"IBKR is for the big dogs. It's the most powerful broker out there, but setting it up is like assembling IKEA furniture — technically possible, emotionally draining, and you'll question your life choices halfway through.<br><br>You need their TWS (Trader Workstation) software running on your computer at the same time as the bot. It's like having a clingy ex — it always has to be there or nothing works.<br><br>Host: <code>127.0.0.1</code>, Port: <code>7497</code> for paper, <code>7496</code> for live. Full walkthrough is in <code>RTFM/08_API_SETUP.md</code> if you're about that life."</td></tr></table>

---

## 🧠 Step 2: The AI Brain (Optional But Worth It)

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Go to <b>Settings</b> → <b>Intelligence</b> tab.<br><br>Let me be clear about something: the AI does NOT place trades. The math engine does that. The AI is like a sports commentator — it watches what's happening, explains the market conditions, and gives color commentary so you don't feel like you're staring at numbers in a vacuum. It also double-checks the bot's work, like a teacher grading homework.<br><br>Pick a provider. Gemini is cheap and good. DeepSeek is even cheaper and surprisingly not terrible. OpenAI is the luxury option — it's like paying for first class when coach gets you there just as fast, but hey, some people like the legroom.<br><br>Paste your API key, pick a model, leave Temperature at <b>0.3</b> unless you want the AI to start writing poetry instead of market analysis."</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/skeptic.png" width="150"></td><td><b>SKEPTIC</b>:<br>"What if I don't have an API key? What if I can't afford one?"</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Then don't use one. The bot trades with pure math. No AI required. You just won't get the fancy commentary on the dashboard. It's like driving without the radio — the car still drives, you just don't get background music."</td></tr></table>

---

## 📊 Step 3: Build Your Profile (Your Battle Plan)

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"A 'Profile' is basically an instruction manual you hand to the bot before sending it to war. It says: what to trade, when to trade it, and how aggressive to be. Think of it like giving a hitman a target list and a set of rules. Except legal. And with currency pairs instead of people.<br><br>You're going to need to make one. Don't panic — it takes about two minutes. Click <b>Profile</b> in the left nav bar, then hit <b>'+ New Profile'</b> at the top of the sidebar. Give it a name (lowercase, underscores — like <code>my_first_setup</code>). Once it's created, you'll see two things:"</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"<b>🤖 AI Optimize</b> (top of the page): See that shiny button at the top? Just click it. It uses our own AI system (relayed through GhostSpotter.com) — you do NOT need your own API key for this. It reads your symbols, figures out what you're trading, and automatically configures your strategies, safety shields, and risk settings for you. One click. Done. If you want to do things yourself, just add your symbols manually instead.<br><br><b>📊 Trading Symbols</b>: Below the AI Optimize button, this is your shopping list. You'll see a directory of symbols organized by category — Crypto, Forex & Metals, Equities & ETFs, Futures. Just click the ones you want to trade and they'll light up teal. If you're on OANDA (forex), the symbols use underscores (<code>EUR_USD</code>). Crypto uses no underscores (<code>BTCUSD</code>). You can also type custom symbols into the text box and press Enter.<br><br>Start with 3-5 symbols. Don't add 20 symbols on a $500 account — the bot won't have enough capital to trade them all and the Leverage Sentry will block everything."</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wait, so there's no pre-made profiles? I have to build my own?"</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yes. And that's on PURPOSE. A pre-made profile would be like handing you someone else's prescription glasses — technically glasses, but they don't fit YOUR eyes. Your account size, your risk tolerance, your schedule, the symbols your broker supports — all of that is different from the next person. Building your own profile takes 2 minutes and guarantees the bot is actually trading what YOU want, how YOU want it. Trust me, it's better this way.<br><br>Oh, and one more thing: everything auto-saves as you make changes. You'll see a little 'Saving...' indicator at the top that turns into 'All changes saved.' No save button to forget to click. You're welcome."</td></tr></table>

---

## ⚙️ Step 4: Risk Management (The 'Don't Blow Up Your Account' Section)

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Alright, listen. I need you to pay attention right now like your rent depends on it. Because it might.<br><br>Risk management is the difference between 'I'm building wealth' and 'I'm calling my mom for gas money.' It's not sexy. It's not exciting. It's the financial equivalent of wearing a seatbelt. Nobody WANTS to wear a seatbelt, but everybody's glad they did when the crash happens."</td></tr></table>

Go to **Settings** (gear icon) → **Strategy** tab → scroll to **Global Risk Limits**.

<table><tr><td width="170"><img src="RTFM/img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Here are the critical settings, translated into language that doesn't require a finance degree:"</td></tr></table>

| Setting | What It Actually Means | Safe | Reckless |
|---|---|---|---|
| **Default Risk %** | "How much of my whole pile of money am I okay losing on ONE single trade?" | 1-2% | 5%+ |
| **Max Exposure %** | "How much of my money can be at risk RIGHT NOW across ALL trades combined?" | 10% | 50% |
| **Daily Loss Limit %** | "If I lose THIS much today, shut everything down so I don't spiral." | 5% | Not setting one at all |
| **Risk Reward Ratio** | "For every dollar I risk, how many dollars do I want to win?" | 2.0 | Less than 1.0 |

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Let me make this real. You have $4,000 in your account. You set risk to 2%.<br><br>The bot risks <b>$80</b> on a trade. If it wins at 2:1, you make <b>$160</b>. If it loses, you lose $80. If you lose FOUR trades in a row — which happens, markets are unpredictable — you're down $320. That's 8%. That stings, but you survive. You trade tomorrow. Life goes on.<br><br>Now imagine you set risk to 10% because some guru on TikTok told you to 'be aggressive.' Same $4,000. Same four-trade losing streak. Except now you lost <b>$1,600</b>. Forty percent of your account is gone. Your hands are shaking. Your significant other is asking why you look like you saw a ghost. You're Googling 'how to recover from 40% drawdown' at 2 AM.<br><br>The answer, by the way, is that you need a 67% gain just to get back to EVEN. The math of recovery is brutally unfair. The deeper the hole, the harder it is to climb out. So don't dig the hole in the first place. Keep your risk at 1-2% and sleep like a baby."</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Baby, my third husband gambled away our vacation fund in Vegas because he 'felt lucky.' Luck is not a strategy. Math is a strategy. Listen to the math."</td></tr></table>

---

## 🗡️ Step 5: The Strategy (What Is The Bot Actually Doing?)

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Okay, here's the part where people's eyes glaze over. Don't let your eyes glaze over. I will reach through this screen.<br><br>The bot has multiple 'strategies' — different playbooks for different market conditions. Trending market? One playbook. Choppy market? Different playbook. Market going sideways like a crab? Another playbook.<br><br>But here's the beautiful part: <b>you don't have to pick.</b><br><br>Just use <b>Meta-SCI</b>. That's the default. Meta-SCI is like hiring a coaching staff instead of one coach. It runs ALL the strategies at the same time, scores them from 0 to 100, and only lets the BEST one take the shot. If none of them score high enough? It does nothing. It sits on its hands. It says 'Nah, the market looks like trash right now, I'm not touching it.'<br><br>That 'doing nothing' part? That's the most valuable thing the bot does. Because YOU would have forced a trade. You KNOW you would have. You would have seen a candle that 'looked promising' and thrown money at it like a drunk guy at a strip club. The bot doesn't do that. The bot has standards."</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"So I just... leave it on Meta-SCI and don't touch it?"</td></tr></table>

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"YES. That's it. That's the whole thing. Leave it on Meta-SCI. Stop overthinking. You're not a hedge fund manager. You're a person who downloaded a bot. Let the bot be the smart one. That's literally why it exists."</td></tr></table>

---

## ▶️ Step 6: Turn It On

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"You connected your broker. You built a profile. You set your risk to something that isn't financially suicidal. Time to let the machine eat."</td></tr></table>

1. **Select your profile** from the sidebar.
2. The bot starts scanning. Immediately. No warm-up period.
3. Watch the **Decisions** panel — it tells you what the bot thinks about each symbol in real time.
4. When the math lines up, the bot pulls the trigger automatically.
5. Your open trades show up in **Holdings** with live profit/loss.

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Here's what the decisions look like in plain English:<br><br><code>ENTER_LONG</code> = 'I see an opportunity to buy.'<br><code>ENTER_SHORT</code> = 'I see an opportunity to sell.'<br><code>HOLD</code> = 'I'm already in a trade and I'm keeping it.'<br><code>STAND_ASIDE</code> = 'The market looks like garbage right now. I'm not touching it.'<br><br>That last one — STAND_ASIDE — you're going to see it A LOT. And every time you see it, I want you to say 'Thank you.' Because that's the bot saving you from a bad trade. That's the bot being smarter than you. Embrace it."</td></tr></table>

---

## 🛡️ Step 7: The Bodyguards (Safety Features)

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The bot comes with bodyguards. You didn't hire them. You don't pay them. They just showed up and they're not leaving. Here's who they are:"</td></tr></table>

- **Position Lock**: Once the bot buys something, it LOCKS that position. If the market dips 5 minutes later and another signal screams "SELL!", the bot ignores it. No flip-flopping. No whipsawing. No burning cash on broker fees because the bot can't make up its mind. One trade, one direction, until it's done.

- **Leverage Sentry**: If you try to open too many huge trades at once, this guard physically blocks the door. It doesn't care about your feelings. It cares about your account not getting margin called.

- **Daily Loss Limit**: If you're having a BAD day and losses pile up, the bot shuts down ALL trading for the rest of the day. It stops you from doing what every losing trader does — doubling down in a panic. The bot goes, "Nope. We're done. Go watch TV. Come back tomorrow."

- **Sabbath Mode**: Weekend markets are a ghost town run by bots and manipulation. The bot automatically pauses real trading and switches to simulation from Friday sunset to Sunday. Even the bot observes a day of rest.

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"One critical thing: <b>DO NOT manually close trades</b> that the bot opened. If you do, Position Lock gets confused. It thinks the trade is still open. Now it won't enter new trades for that symbol. It's like telling your babysitter you'll be home at 9, then sneaking in at 7 and rearranging the furniture. The babysitter doesn't know what's happening. Leave the bot alone. Let it manage its own exits."</td></tr></table>

---

## 🧪 Step 8: The Time Machine (Backtesting)

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Before you throw real money at a custom profile you built with your bare hands, test it on historical data first. This is called 'backtesting.' It's like a dress rehearsal for your money.<br><br>Open a terminal and run:"</td></tr></table>

```bash
# Test the last 7 days of Forex
poetry run python tools/run_forex_backtest.py
```

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"It spits out a scoreboard. The two numbers you care about:<br><br><b>Win Rate</b>: Above 50% = good. Below 50% = your strategy needs work.<br><b>Profit Factor</b>: Above 1.5 = making money. Below 1.0 = you're donating to the market.<br><br>Now here's the part where I have to be the responsible adult: <b>backtests are not crystal balls.</b> They show you what WOULD have happened. They don't promise what WILL happen. But they're a hell of a lot better than guessing."</td></tr></table>

---

## 💡 The "I'm Begging You" Checklist

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"I'm going to give you the cheat codes. The things that separate the people who make money from the people who blow up their accounts and blame the bot. Write these down. Tattoo them on your arm. I don't care. Just remember them."</td></tr></table>

1. **Paper trade first.** Toggle off 'Execute Trades.' Use fake money for at least a week. If you can't be profitable with Monopoly money, what makes you think you'll be profitable with your mortgage payment?

2. **Leave it alone.** Stop closing trades early because you got scared of a red candle. You hired a robot to remove human emotion from the equation. Let the robot do its job. You don't hire a plumber and then stand behind him telling him how to hold the wrench.

3. **Read the logs.** If the bot isn't trading, the logs will tell you exactly why. It's usually something like `Score 42.1 below threshold 55.0`. Translation: "The market looks like crap and I'm protecting your capital by doing absolutely nothing." That's not a bug. That's a FEATURE.

4. **Scale slowly.** You won three trades in a row? Great. Don't immediately double your risk because you feel invincible. The market will humble you. It humbles EVERYONE. It humbled hedge funds, Wall Street veterans, and people way smarter than both of us combined. You are not the exception.

<table><tr><td width="170"><img src="RTFM/img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Baby, the tortoise beat the hare. And the tortoise wasn't even trying that hard. He was just consistent. Be the tortoise. The hare is broke and out of breath somewhere."</td></tr></table>

---

## 🆘 Something Broke? (Troubleshooting)

| What Happened | What To Do |
|---|---|
| **Bot won't start** | No broker plugged in. Go to Settings → Brokers and add your credentials. |
| **"Another instance running"** | Delete `logs/tradebot.lock` and restart. The bot thinks it's already running. It's not. It's just confused. |
| **Bot scans but never trades** | Either your capital is too low for the position size, or your ICC score threshold is too high. Lower the threshold or add more capital. |
| **"Leverage Sentry" blocking everything** | You're trying to open more trades than your account can handle. Add capital, reduce positions, or lower your risk %. |
| **Decisions say "No signals found"** | That's NORMAL. The bot is being picky. Good. You WANT a picky bot. |
| **API 401 errors** | Your API key expired or you typed it wrong. Regenerate it and paste it again. |
| **Bot trades then immediately closes** | Stop loss is too tight. The market breathed and the bot panicked. Widen your stops or increase the timeframe. |

---

## 📖 Want to Keep Learning?

<table><tr><td width="170"><img src="RTFM/img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you actually read this far, I'm genuinely impressed. Most people gave up at Step 1. You didn't. That tells me something about you. Here's the deeper stuff if you want it:"</td></tr></table>

| Document | What You'll Learn |
|---|---|
| `RTFM/01_PHILOSOPHY.md` | Why this bot exists (spoiler: late-stage capitalism) |
| `RTFM/06_PANIC_BUTTON.md` | How to flatten everything if the world is ending |
| `RTFM/09_FEET_WET_STRATEGY.md` | Deep dive into every strategy and when to use them |
| `RTFM/30_BARE_HANDS.md` | Why manual trading is a bloodsport and you're unarmed |
| `RTFM/43_ALLERGIC_TO_MONEY.md` | The speech that will either change your life or hurt your feelings |

<table><tr><td width="170"><img src="RTFM/img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"The journey of a thousand trades begins with a single profile. You have read the manual. Now press the button. The market awaits no one."</em></td></tr></table>

*Last updated: March 2026 | Trade by SCI v2.x*
