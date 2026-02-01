#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Load repo-local env defaults (quietly). This keeps CLI behavior predictable and
# also lets the GUI persist settings via .env for future runs.
set -a
[ -f "$ROOT_DIR/.env" ] && source "$ROOT_DIR/.env" >/dev/null 2>&1 || true
set +a

# In tmux, panes are spawned via a non-interactive shell (no .bashrc),
# so env vars like ${CHATGPT_KEY} won't exist unless we explicitly load them.
ENV_BOOTSTRAP="source \"$HOME/.bashrc\" >/dev/null 2>&1 || true; set -a; [ -f \"$ROOT_DIR/.env\" ] && source \"$ROOT_DIR/.env\" >/dev/null 2>&1; set +a"

list_profiles() {
  local path="config/settings_profiles.yaml"
  [[ -f "$path" ]] || return 1
  awk '
    BEGIN { in_section=0; out=""; }
    /^profiles:[[:space:]]*$/ { in_section=1; next }
    in_section==1 && /^[^[:space:]]/ { in_section=0 }
    in_section==1 && /^  [A-Za-z0-9_]+:[[:space:]]*$/ {
      key=$1
      sub(/:$/, "", key)
      if (out != "") out=out", "
      out=out key
    }
    END { print out }
  ' "$path"
}

profile_description() {
  local name="${1:-}"
  case "$name" in
    scalp)
      echo "Fast 1m/2s loop for quick demos; not recommended for live trading."
      ;;
    intraday)
      echo "US market-hours style profile (5m candles) with auto-flatten on close + PDT guard."
      ;;
    swing)
      echo "Slow 1h candles for higher-timeframe decisions (less noise, fewer cycles)."
      ;;
    crypto_247)
      echo "Crypto-only 24/7 loop (BTC/ETH/SOL) with PairSelector + maker-first + synthetic stops."
      ;;
    all_247)
      echo "Always-on universe (equity+forex+crypto; futures stubbed). Respects each symbol's market hours."
      ;;
    auto_schedule)
      echo "Auto switches: equities during US hours, crypto otherwise; Sabbath enabled by default."
      ;;
    *)
      echo "Custom profile (see config/settings_profiles.yaml)."
      ;;
  esac
}

stop_gui() {
  local gui_pid
  gui_pid="$(pgrep -f "python scripts/tradebot_gui.py" || true)"
  if [[ -n "$gui_pid" ]]; then
    echo "Stopping GUI (PID: $gui_pid)..."
    kill "$gui_pid"
    echo "GUI stopped."
    exit 0
  else
    echo "No running GUI found."
    exit 0
  fi
}


usage() {
  local profiles
  profiles="$(list_profiles 2>/dev/null || true)"
  if [[ -z "${profiles// /}" ]]; then
    profiles="(unable to read config/settings_profiles.yaml)"
  fi

  cat <<'EOF'
Tradebot SCI - tmux launcher

Usage:
  ./scripts/tradebot.sh [options]

This script builds the BOT_CMD and launches the tmux dashboard automatically.

Options:
  -p, --profile NAME          Profile name (default: auto_schedule)
                              Controls symbol universe + cadence + (optional) auto-schedule + sabbath rules.
  -m, --mode MODE             Bot mode: continuous|scheduled|iterations (default: continuous)
                              - continuous: run forever (best for 24/7 crypto or always-on sims)
                              - scheduled: run only inside configured session windows (then exits)
                              - iterations: run N loops then exit (good for testing/backtests)
  -i, --iterations N          Iterations when --mode iterations (default: 120)
                              One iteration = one scan/decision/execution cycle.
  -x, --execute-trades BOOL   true|false (default: false)
                              When true, the bot can place live orders (IBKR/alt broker depending on config).
  -b, --sabbath               Enable sabbath flag (passes --sabbath to the bot)
                              Blocks NEW entries during the sabbath window; exits/protection still run.
  -B, --no-sabbath            Explicitly disable Sabbath blocking (even if the profile enables it)

  -n, --session NAME          tmux session name (default: tradebot)
  -l, --log FILE              Log file to tail (default: logs/tradebot.log)

  -c, --commentary MODE       off|internal (default: internal)
                              - off: deterministic dashboard only
                              - internal: built-in AI commentary
  -t, --commentary-min SEC    Minimum seconds between commentary refreshes (default: 300)

  -e, --env KEY=VALUE         Extra env var (repeatable)
  -d, --dry-run               Print commands and exit
  -r, --restart                 Restart the bot process + commentary panes inside tmux (keeps session open)
  -G, --stop-gui                Stop the running desktop GUI wrapper (if any)

  -g, --gui                   Launch the desktop GUI wrapper (Qt). Opens/controls tmux dashboard.
  -D, --daemon                Start the bot in background (daemon) without any GUI.
  -s, --settings              Launch only the settings dialog (for debugging GUI settings)
  -k, --exit-all              Kill the tmux session and exit
  -h, --help                  Show help

Examples:
  ./scripts/tradebot.sh
  ./scripts/tradebot.sh -p intraday -m scheduled -x true
  ./scripts/tradebot.sh -p intraday -m iterations -i 300
  ./scripts/tradebot.sh --restart
  ./scripts/tradebot.sh --gui
  ./scripts/tradebot.sh --settings
  ./scripts/tradebot.sh --stop-gui
  ./scripts/tradebot.sh --exit-all

To restart the GUI from the CLI:
  ./scripts/tradebot.sh --stop-gui
  ./scripts/tradebot.sh --gui


What you get:
  - A tmux session with three windows:
    - view: left pane tails the log; right pane shows commentary (optional)
    - bot:  runs the python process (keeps the dashboard panes clean)
    - holdings: open positions + hold-guard timers (from [HOLDINGS] snapshots)
  - Log file default: logs/tradebot.log
EOF

  echo ""
  echo "Available profiles (from config/settings_profiles.yaml):"
  if [[ -z "${profiles// /}" || "$profiles" == "(unable to read config/settings_profiles.yaml)" ]]; then
    echo "  ${profiles}"
    return 0
  fi
  local -a profile_list
  IFS=',' read -r -a profile_list <<< "$profiles"
  local raw name
  for raw in "${profile_list[@]}"; do
    name="$(echo "$raw" | sed 's/^ *//;s/ *$//')"
    [[ -z "$name" ]] && continue
    echo "  - $name: $(profile_description "$name")"
  done
  echo ""
  echo "Modes explained:"
  echo "  - continuous: loops forever, still respecting per-symbol market hours; use for always-on runs."
  echo "  - scheduled: runs only inside schedule windows from config/settings_base.yaml:schedule.sessions."
  echo "  - iterations: runs N cycles then exits; a cycle = select symbol(s) -> decide -> execute/skip."
  echo ""
  echo "Sabbath explained:"
  echo "  - Sabbath blocks NEW entries during the configured window."
  echo "  - Safety still runs (local/synthetic stops and exits can still trigger)."
}

PROFILE_NAME="${PROFILE_NAME:-auto_schedule}"
MODE="${BOT_MODE:-continuous}"
ITERATIONS="${BOT_ITERATIONS:-120}"
EXECUTE_TRADES="${EXECUTE_TRADES:-false}"
TRADING_CONFIRMATION="${TRADING_CONFIRMATION:-}"
SABBATH="false"
NO_SABBATH="false"

SESSION_NAME="${SESSION_NAME:-tradebot}"
LOG_FILE="${TRADEBOT_LOG:-${LOG_FILE:-logs/tradebot.log}}"
MARKET_DATA_MODE="${MARKET_DATA_MODE:-}"
BROKER_MODE="${BROKER_MODE:-}"

COMMENTARY_MODE=""
COMMENTARY_MIN_SECONDS="${COMMENTARY_LLM_MIN_SECONDS:-300}"

DRY_RUN="false"
RESTART="false"
GUI="false"
SETTINGS="false"
EXIT_ALL="false"
STOP_GUI="false"
DAEMON="false"

EXTRA_ENVS=()
EXECUTE_TRADES_SET="false"
PROFILE_SET="false"
MODE_SET="false"
ITERATIONS_SET="false"
SABBATH_SET="false"
NO_SABBATH_SET="false"

case "${BOT_SABBATH:-}" in
  on|true|1|yes) SABBATH="true" ;;
  off|false|0|no) NO_SABBATH="true" ;;
  *) : ;;
esac

	while [[ $# -gt 0 ]]; do
	  case "$1" in
	    -p|--profile) PROFILE_NAME="${2:-}"; PROFILE_SET="true"; shift 2 ;;
	    -m|--mode) MODE="${2:-}"; MODE_SET="true"; shift 2 ;;
	    -i|--iterations) ITERATIONS="${2:-}"; ITERATIONS_SET="true"; shift 2 ;;
	    -x|--execute-trades) EXECUTE_TRADES="${2:-}"; EXECUTE_TRADES_SET="true"; shift 2 ;;
	    -b|--sabbath) SABBATH="true"; SABBATH_SET="true"; shift ;;
	    -B|--no-sabbath) NO_SABBATH="true"; NO_SABBATH_SET="true"; shift ;;

    -n|--session) SESSION_NAME="${2:-}"; shift 2 ;;
    -l|--log) LOG_FILE="${2:-}"; shift 2 ;;

    -c|--commentary) COMMENTARY_MODE="${2:-}"; shift 2 ;;
    -t|--commentary-min) COMMENTARY_MIN_SECONDS="${2:-}"; shift 2 ;;

	    -e|--env) EXTRA_ENVS+=("${2:-}"); shift 2 ;;
	    -d|--dry-run) DRY_RUN="true"; shift ;;
	    -r|--restart) RESTART="true"; shift ;;
	    -G|--stop-gui) STOP_GUI="true"; shift ;;
	    -g|--gui) GUI="true"; shift ;;
	    -D|--daemon) DAEMON="true"; shift ;;
	    -s|--settings) SETTINGS="true"; shift ;;
	    -k|--exit-all) EXIT_ALL="true"; shift ;;
	    -h|--help) usage; exit 0 ;;
	    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
	  esac
	done

if [[ "$STOP_GUI" == "true" ]]; then
  stop_gui
fi

if [[ -z "$PROFILE_NAME" ]]; then
  echo "ERROR: --profile is required" >&2
  exit 2
fi

case "$MODE" in
  continuous|scheduled|iterations) ;;
  *) echo "ERROR: invalid --mode '$MODE' (expected continuous|scheduled|iterations)" >&2; exit 2 ;;
esac

if [[ "$EXIT_ALL" == "true" ]]; then
  if command -v tmux >/dev/null 2>&1; then
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
    echo "Killed tmux session: $SESSION_NAME"
    exit 0
  fi
  echo "tmux not installed; nothing to kill." >&2
  exit 0
fi

BOT_ARGS=()
case "$MODE" in
  continuous) BOT_ARGS+=(--continuous) ;;
  scheduled) BOT_ARGS+=(--scheduled) ;;
  iterations) BOT_ARGS+=(--iterations "$ITERATIONS") ;;
esac
if [[ "$SABBATH" == "true" && "$NO_SABBATH" == "true" ]]; then
  echo "ERROR: --sabbath and --no-sabbath are mutually exclusive" >&2
  exit 2
fi
if [[ "$SABBATH" == "true" ]]; then
  BOT_ARGS+=(--sabbath)
elif [[ "$NO_SABBATH" == "true" ]]; then
  BOT_ARGS+=(--no-sabbath)
fi

BOT_CMD="PROFILE_NAME=$PROFILE_NAME PYTHONPATH=src EXECUTE_TRADES=$EXECUTE_TRADES TRADING_CONFIRMATION=YES MARKET_DATA_MODE=${MARKET_DATA_MODE:-} BROKER_MODE=${BROKER_MODE:-} poetry run python scripts/run_dev_bot.py ${BOT_ARGS[*]}"

export SESSION_NAME
export LOG_FILE
export COMMENTARY_LLM_MIN_SECONDS="$COMMENTARY_MIN_SECONDS"

# Safety clamp: prevent accidental runaway LLM calls.
if [[ "${COMMENTARY_LLM_MIN_SECONDS:-0}" =~ ^[0-9]+$ ]]; then
  if (( COMMENTARY_LLM_MIN_SECONDS < 60 )); then
    export COMMENTARY_LLM_MIN_SECONDS=60
  fi
fi

if [[ -n "$COMMENTARY_MODE" ]]; then
  export COMMENTARY_LLM="$COMMENTARY_MODE"
fi

for kv in "${EXTRA_ENVS[@]}"; do
  if [[ "$kv" != *=* ]]; then
    echo "ERROR: --env must be KEY=VALUE (got '$kv')" >&2
    exit 2
  fi
  export "${kv?}"
done

export BOT_CMD

restart_tmux() {
  if ! command -v tmux >/dev/null 2>&1; then
    echo "ERROR: tmux not installed; cannot restart." >&2
    exit 2
  fi
  if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "ERROR: tmux session '$SESSION_NAME' not found; start it first with ./scripts/tradebot.sh" >&2
    exit 2
  fi

	  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
	  printf "%s [INFO] tradebot_sci.runtime.loop - [RESTART] requested via scripts/tradebot.sh\n" "$(date '+%Y-%m-%d %H:%M:%S')" >>"$LOG_FILE" || true

	  # CRITICAL: Re-source .env to pick up changes made by the GUI/User since the script started.
	  # Otherwise, we restart with the stale environment variables of the running shell.
	  set -a
	  [ -f "$ROOT_DIR/.env" ] && source "$ROOT_DIR/.env" >/dev/null 2>&1 || true
	  set +a

	  # Preserve the last run configuration from tmux unless the user explicitly overrides it.
	  local any_override="false"
	  if [[ "$PROFILE_SET" == "true" || "$MODE_SET" == "true" || "$ITERATIONS_SET" == "true" || "$SABBATH_SET" == "true" || "$NO_SABBATH_SET" == "true" || "$EXECUTE_TRADES_SET" == "true" ]]; then
	    any_override="true"
	  fi

	  if [[ -z "$TRADING_CONFIRMATION" ]]; then
	    TRADING_CONFIRMATION="$(tmux show-environment -t "$SESSION_NAME" TRADING_CONFIRMATION 2>/dev/null | sed -n 's/^TRADING_CONFIRMATION=//p' || true)"
	    if [[ -z "$TRADING_CONFIRMATION" && -f "$(dirname "$LOG_FILE")/.trading_confirmation" ]]; then
	      TRADING_CONFIRMATION="$(cat "$(dirname "$LOG_FILE")/.trading_confirmation")"
	    fi
	    export TRADING_CONFIRMATION
	  fi

	  local saved_bot_cmd=""
	  saved_bot_cmd="$(tmux show-environment -t "$SESSION_NAME" TRADEBOT_BOT_CMD 2>/dev/null | sed -n 's/^TRADEBOT_BOT_CMD=//p' || true)"
	  if [[ "$any_override" != "true" && -n "$saved_bot_cmd" ]]; then
	    BOT_CMD="$saved_bot_cmd"
	    if echo "$BOT_CMD" | grep -q "EXECUTE_TRADES=true"; then
	      EXECUTE_TRADES="true"
	    elif echo "$BOT_CMD" | grep -q "EXECUTE_TRADES=false"; then
	      EXECUTE_TRADES="false"
	    fi
	  else
	    # If the user didn't explicitly set -x/--execute-trades, preserve the current session's setting.
	    if [[ "$EXECUTE_TRADES_SET" != "true" ]]; then
	      local saved_exec=""
	      saved_exec="$(tmux show-environment -t "$SESSION_NAME" TRADEBOT_EXECUTE_TRADES 2>/dev/null | sed -n 's/^TRADEBOT_EXECUTE_TRADES=//p' || true)"
	      if [[ -n "$saved_exec" ]]; then
	        EXECUTE_TRADES="$saved_exec"
	        BOT_CMD="PROFILE_NAME=$PROFILE_NAME PYTHONPATH=src EXECUTE_TRADES=$EXECUTE_TRADES TRADING_CONFIRMATION=YES MARKET_DATA_MODE=${MARKET_DATA_MODE:-} BROKER_MODE=${BROKER_MODE:-} poetry run python scripts/run_dev_bot.py ${BOT_ARGS[*]}"
	      fi
	    fi
	  fi

	  # Bot pane (Window 1: bot)
	  tmux respawn-pane -k -t "$SESSION_NAME:bot.0" "cd \"$ROOT_DIR\" && $ENV_BOOTSTRAP; $BOT_CMD" 2>/dev/null \
	    || tmux respawn-pane -k -t "$SESSION_NAME:1.0" "cd \"$ROOT_DIR\" && $ENV_BOOTSTRAP; $BOT_CMD"

	  # Persist for future restarts.
	  tmux set-environment -t "$SESSION_NAME" TRADEBOT_BOT_CMD "$BOT_CMD" 2>/dev/null || true
	  tmux set-environment -t "$SESSION_NAME" TRADEBOT_EXECUTE_TRADES "$EXECUTE_TRADES" 2>/dev/null || true
          tmux set-environment -t "$SESSION_NAME" TRADING_CONFIRMATION "$TRADING_CONFIRMATION" 2>/dev/null || true
          tmux set-environment -t "$SESSION_NAME" EXCHANGE_PROVIDER "${EXCHANGE_PROVIDER:-}" 2>/dev/null || true
          tmux set-environment -t "$SESSION_NAME" ALTERNATIVE_MARKET_DATA "${ALTERNATIVE_MARKET_DATA:-}" 2>/dev/null || true
          tmux set-environment -t "$SESSION_NAME" ALTERNATIVE_BROKER "${ALTERNATIVE_BROKER:-}" 2>/dev/null || true
          tmux set-environment -t "$SESSION_NAME" MARKET_DATA_MODE "${MARKET_DATA_MODE:-}" 2>/dev/null || true
          tmux set-environment -t "$SESSION_NAME" BROKER_MODE "${BROKER_MODE:-}" 2>/dev/null || true

	  # Holdings window (Window 2: holdings)
	  if tmux list-windows -t "$SESSION_NAME" -F "#{window_name}" 2>/dev/null | grep -qx "holdings"; then
	    tmux respawn-pane -k -t "$SESSION_NAME:holdings.0" "cd \"$ROOT_DIR\" && $ENV_BOOTSTRAP; printf '\\033[2J\\033[H' && PYTHONPATH=src poetry run python tools/holdings_tail.py --log \"$LOG_FILE\" --follow --interval 3" 2>/dev/null || true
	  else
	    tmux new-window -d -t "$SESSION_NAME" -n holdings "cd \"$ROOT_DIR\" && $ENV_BOOTSTRAP; printf '\\033[2J\\033[H' && PYTHONPATH=src poetry run python tools/holdings_tail.py --log \"$LOG_FILE\" --follow --interval 3" 2>/dev/null || true
	  fi

  local did_respawn_commentary="false"
  if tmux select-window -t "$SESSION_NAME:view" 2>/dev/null || tmux select-window -t "$SESSION_NAME:0" 2>/dev/null; then
    # Ensure we have a 3-pane layout in the view window: left-top=log, left-bottom=candles, right=commentary.
    # Identify panes by geometry so indexes don't matter.
    mapfile -t panes < <(
      tmux list-panes -t "$SESSION_NAME:view" -F "#{pane_id}|#{pane_left}|#{pane_top}" 2>/dev/null \
        || tmux list-panes -t "$SESSION_NAME:0" -F "#{pane_id}|#{pane_left}|#{pane_top}"
    )

    right_pane=""
    left_top_pane=""
    left_bottom_pane=""
    min_left=999999
    max_left=-1

    for row in "${panes[@]}"; do
      IFS='|' read -r pid plef ptop <<<"$row"
      [[ -z "$pid" ]] && continue
      [[ "$plef" -lt "$min_left" ]] && min_left="$plef"
      [[ "$plef" -gt "$max_left" ]] && { max_left="$plef"; right_pane="$pid"; }
      : "$ptop" >/dev/null
    done

    # If this is a single-pane view window, split horizontally first to create the right commentary pane.
    if [[ "${#panes[@]}" -lt 2 ]]; then
      left_top_pane="$(IFS='|' read -r pid _ _ <<<"${panes[0]:-}"; echo "$pid")"
      right_pane="$(tmux split-window -t "$left_top_pane" -h -P -F "#{pane_id}" 2>/dev/null || true)"
      panes=()
      mapfile -t panes < <(tmux list-panes -t "$SESSION_NAME:view" -F "#{pane_id}|#{pane_left}|#{pane_top}" 2>/dev/null || tmux list-panes -t "$SESSION_NAME:0" -F "#{pane_id}|#{pane_left}|#{pane_top}")
      min_left=999999
      max_left=-1
      right_pane=""
      for row in "${panes[@]}"; do
        IFS='|' read -r pid plef ptop <<<"$row"
        [[ "$plef" -lt "$min_left" ]] && min_left="$plef"
        [[ "$plef" -gt "$max_left" ]] && { max_left="$plef"; right_pane="$pid"; }
        : "$ptop" >/dev/null
      done
    fi

    # Find left column panes and select top/bottom by pane_top.
    left_top_pane=""
    left_bottom_pane=""
    left_top_val=999999
    left_bottom_val=-1
    for row in "${panes[@]}"; do
      IFS='|' read -r pid plef ptop <<<"$row"
      [[ "$plef" != "$min_left" ]] && continue
      if [[ "$ptop" -lt "$left_top_val" ]]; then
        left_top_val="$ptop"
        left_top_pane="$pid"
      fi
      if [[ "$ptop" -gt "$left_bottom_val" ]]; then
        left_bottom_val="$ptop"
        left_bottom_pane="$pid"
      fi
    done

    # If there's only one pane in the left column, split it vertically to create the bottom-left candles pane.
    if [[ -n "$left_top_pane" && "$left_top_pane" == "$left_bottom_pane" ]]; then
      left_bottom_pane="$(tmux split-window -t "$left_top_pane" -v -P -F "#{pane_id}" 2>/dev/null || true)"
    fi

    # Respawn log + candles.
    if [[ -n "$left_top_pane" ]]; then
      tmux respawn-pane -k -t "$left_top_pane" "cd \"$ROOT_DIR\" && $ENV_BOOTSTRAP; printf '\\033[2J\\033[H' && (PYTHONPATH=src poetry run python tools/log_tail_ui.py --log \"$LOG_FILE\" --follow --interval 0.5 || tail -F \"$LOG_FILE\")" 2>/dev/null || true
    fi
    if [[ -n "$left_bottom_pane" ]]; then
        # Bottom-left: candles (IBKR or CCXT)
        local candles_cmd="PYTHONPATH=src poetry run python tools/candles_launcher.py --log \"$LOG_FILE\" --follow --interval 15 --rotate-seconds 30 --refresh-seconds 15 --render rich"
                tmux respawn-pane -k -t "$left_bottom_pane" "cd \"$ROOT_DIR\" && $ENV_BOOTSTRAP; printf '\\033[2J\\033[H' && $candles_cmd" 2>/dev/null || true
    fi

    # Commentary pane (right pane)
    if [[ -n "$right_pane" ]]; then
      local commentary_cmd
      commentary_cmd="PYTHONPATH=src poetry run python \"tools/commentary_tail.py\" --log \"$LOG_FILE\" --follow --interval 3"
      if [[ -z "${COMMENTARY_LLM:-}" ]]; then
        commentary_cmd="COMMENTARY_LLM=internal $commentary_cmd"
      elif [[ "${COMMENTARY_LLM:-off}" != "off" ]]; then
        commentary_cmd="COMMENTARY_LLM=\"${COMMENTARY_LLM}\" $commentary_cmd"
      fi
      tmux respawn-pane -k -t "$right_pane" "cd \"$ROOT_DIR\" && $ENV_BOOTSTRAP; printf '\\033[2J\\033[H' && $commentary_cmd" 2>/dev/null || true
      did_respawn_commentary="true"
    fi
  fi

  if [[ "$did_respawn_commentary" != "true" ]]; then
    # Commentary pane fallback (older 2-pane layouts)
    local commentary_cmd
    commentary_cmd="PYTHONPATH=src poetry run python \"tools/commentary_tail.py\" --log \"$LOG_FILE\" --follow --interval 3"
    if [[ -z "${COMMENTARY_LLM:-}" ]]; then
      commentary_cmd="COMMENTARY_LLM=internal $commentary_cmd"
    elif [[ "${COMMENTARY_LLM:-off}" != "off" ]]; then
      commentary_cmd="COMMENTARY_LLM=\"${COMMENTARY_LLM}\" $commentary_cmd"
    fi
    tmux respawn-pane -k -t "$SESSION_NAME:view.1" "$commentary_cmd" 2>/dev/null \
      || tmux respawn-pane -k -t "$SESSION_NAME:0.1" "$commentary_cmd" 2>/dev/null \
      || true
  fi

  echo "Restarted tmux session '$SESSION_NAME' (bot + commentary)."
}

if [[ "$DRY_RUN" == "true" ]]; then
  echo "SESSION_NAME=$SESSION_NAME"
  echo "LOG_FILE=$LOG_FILE"
  [[ -n "${COMMENTARY_LLM:-}" ]] && echo "COMMENTARY_LLM=$COMMENTARY_LLM"
  echo "COMMENTARY_LLM_MIN_SECONDS=$COMMENTARY_LLM_MIN_SECONDS"
  for kv in "${EXTRA_ENVS[@]}"; do echo "ENV $kv"; done
  echo "BOT_CMD=$BOT_CMD"
  [[ "$GUI" == "true" ]] && echo "GUI=true"
  echo "./scripts/run_tmux_dashboard.sh"
  exit 0
fi


if [[ "$GUI" == "true" ]] || [[ "$DAEMON" == "true" ]]; then
  # Desktop GUI Mode or Daemon Mode (No Tmux)
  if [[ "$DAEMON" == "true" ]]; then
       echo "Starting in Daemon Mode..."
  else
       echo "Starting in GUI mode (Client Only / Daemon Backend)..."
  fi

  # 1. Kill existing bot if requested by --restart, or just warn?
  # Let's check if running.
  EXISTING_PID=$(pgrep -f "run_dev_bot\.py" | grep -v "$$" || true)
  if [[ -n "$EXISTING_PID" ]]; then
      if [[ "$RESTART" == "true" ]]; then
          echo "Stopping existing bot (PID $EXISTING_PID)..."
          kill "$EXISTING_PID" 2>/dev/null || true
          sleep 2
      else
          echo "Bot is already running (PID $EXISTING_PID). Using existing instance."
      fi
  fi

  # 2. Start Bot if not running
  EXISTING_PID=$(pgrep -f "run_dev_bot\.py" | grep -v "$$" || true)
  if [[ -z "$EXISTING_PID" ]]; then
      echo "Launching Backend Bot..."
      
      # Ensure LOG_FILE dir exists
      mkdir -p "$(dirname "$LOG_FILE")"
      
      # Prepare Environment
      export EXCHANGE_PROVIDER="${EXCHANGE_PROVIDER:-}"
      export ALTERNATIVE_MARKET_DATA="${ALTERNATIVE_MARKET_DATA:-}"
      export ALTERNATIVE_BROKER="${ALTERNATIVE_BROKER:-}"
      
      # Run in background, redirect output to a separate debug log if needed, 
      # but the bot's internal logging handles the main log file.
      # We use nohup to ensure it persists after script exit if needed.
      nohup bash -c "$BOT_CMD" > "$(dirname "$LOG_FILE")/bot_stdout.log" 2>&1 &
      B_PID=$!
      echo "Bot started (PID $B_PID)."
      echo "Logs: $LOG_FILE"
      
      if [[ "$DAEMON" == "true" ]]; then
          echo "Daemon mode active. Bot is running in background. Exiting script."
          exit 0
      fi

      # Wait briefly for startup
      sleep 2
  fi

  if [[ "$DAEMON" == "true" ]]; then
      echo "Bot is already running. Daemon mode exiting."
      exit 0
  fi

  # 3. Launch Electron (Only if GUI is true, which is implicit here if DAEMON is false due to the OR condition above)

  # 3. Launch Electron
  echo "Launching Electron GUI..."
  cd src/tradebot_sci/electron_gui
  
  if [[ ! -d "node_modules" ]]; then
      echo "ERROR: GUI dependencies not found in src/tradebot_sci/electron_gui/node_modules" >&2
      echo "Please run: cd src/tradebot_sci/electron_gui && npm install" >&2
      exit 2
  fi

  if command -v npm >/dev/null 2>&1; then
      npm start -- --no-sandbox
      
      echo "Electron GUI closed."
      EXISTING_PID=$(pgrep -f "run_dev_bot\.py" | grep -v "$$" || true)
      if [[ -n "$EXISTING_PID" ]]; then
          echo "The backend bot (PID $EXISTING_PID) is still running."
          echo "To stop it: kill $EXISTING_PID"
      fi
      exit 0
  else
      echo "ERROR: npm not found; cannot launch Electron GUI." >&2
      exit 2
  fi
fi

if [[ "$SETTINGS" == "true" ]]; then
  # Launch only the settings dialog for debugging.
  if command -v poetry >/dev/null 2>&1; then
    exec env PYTHONPATH=src poetry run python scripts/tradebot_gui.py --settings
  fi
  echo "ERROR: poetry not found; cannot launch settings dialog." >&2
  echo "Install deps with: poetry install --with gui" >&2
  exit 2
fi

if [[ "$RESTART" == "true" ]]; then
  restart_tmux
  exit 0
fi

# Export provider settings for dashboard script
export EXCHANGE_PROVIDER="${EXCHANGE_PROVIDER:-}"
export ALTERNATIVE_MARKET_DATA="${ALTERNATIVE_MARKET_DATA:-}"
export ALTERNATIVE_BROKER="${ALTERNATIVE_BROKER:-}"

exec ./scripts/run_tmux_dashboard.sh
