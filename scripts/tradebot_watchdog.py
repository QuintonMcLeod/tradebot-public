#!/usr/bin/env python3
"""
Automated Log-Monitoring Watchdog for Tradebot SCI

Checks for recent [DECISION] logs in tradebot.log. Alerts if no trading activity
is detected for a specified duration (default 2 hours).

Usage:
  python scripts/tradebot_watchdog.py [--log PATH] [--hours HOURS]
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def parse_iso_time(ts_str):
    """Parse ISO 8601 timestamp safely."""
    try:
        # handle Z ending
        if ts_str.endswith('Z'):
            ts_str = ts_str[:-1]
        return datetime.fromisoformat(ts_str)
    except Exception as e:
        return None

def check_log_activity(log_path, max_hours_idle=2.0):
    if not os.path.exists(log_path):
        logging.error(f"Log file not found: {log_path}")
        return False
        
    now = datetime.now()
    threshold_time = now - timedelta(hours=max_hours_idle)
    
    last_decision_time = None
    last_execute_time = None
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if "[DECISION]" in line:
                    # Attempt to extract timestamp if it's JSON formatted
                    if line.startswith('{"timestamp"'):
                        import json
                        try:
                            data = json.loads(line)
                            ts = parse_iso_time(data.get("timestamp", ""))
                            if ts:
                                last_decision_time = ts
                                action = data.get("message", "").split("action=")[-1].split(" ")[0]
                                if "ENTER" in action.upper() or "SCALE" in action.upper() or "EXIT" in action.upper():
                                    last_execute_time = ts
                        except json.JSONDecodeError:
                            pass
                    else:
                        # Best effort for raw text logs
                        last_decision_time = now # Just assume recent if we found the line but can't parse timestamp
    except Exception as e:
        logging.error(f"Error reading log: {e}")
        return False

    if last_decision_time:
        idle_hours = (now - last_decision_time).total_seconds() / 3600
        logging.info(f"Last decision was {idle_hours:.2f} hours ago.")
        
        if idle_hours > max_hours_idle:
            logging.warning(f"ALERT: Tradebot has been silent for over {max_hours_idle} hours! Last decision at {last_decision_time.isoformat()}")
            return False
            
        if last_execute_time:
            exec_idle_hours = (now - last_execute_time).total_seconds() / 3600
            logging.info(f"Last execution (trade/exit) was {exec_idle_hours:.2f} hours ago.")
            if exec_idle_hours > max_hours_idle * 2:
                logging.warning(f"ALERT: Bot is making decisions but no trades executed in {exec_idle_hours:.2f} hours. Strategy might be too strict.")
        else:
            logging.warning(f"ALERT: Bot is making HOLD decisions, but NO executions found in the current log.")
            
        return True
    else:
        logging.warning(f"ALERT: No [DECISION] logs found in {log_path} at all. Bot may not be running or logging correctly.")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watchdog for Tradebot SCI logs.")
    parser.add_argument('--log', type=str, default=os.path.expanduser('~/.config/tradebot-sci/logs/tradebot.log'), help='Path to tradebot.log')
    parser.add_argument('--hours', type=float, default=2.0, help='Maximum idle hours before alerting')
    parser.add_argument('--loop', action='store_true', help='Run continuously in a loop')
    args = parser.parse_args()
    
    if args.loop:
        logging.info(f"Starting watchdog daemon monitoring {args.log} every 1 hour.")
        while True:
            check_log_activity(args.log, max_hours_idle=args.hours)
            time.sleep(3600)  # Sleep for 1 hour
    else:
        check_log_activity(args.log, max_hours_idle=args.hours)
