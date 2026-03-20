import sys
import os
import logging

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from tradebot_sci.ai.seasoned_trader import SeasonedTraderDaemon

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger("sys")

class MockAIClient:
    def raw_chat(self, messages, expect_json=True):
        print("\n========== SENTINEL AGGREGATOR PAYLOAD (SENT TO LLM) ==========\n")
        print(messages[1]["content"])
        print("\n===============================================================\n")
        
        return '''{
            "analysis": "Markets are heavily digesting recent macroeconomic prints. Fiat pairs are bleeding capital in trend sequences. Activating fallback bypass.",
            "proposed_interval_mins": 15,
            "trigger_kill_switch": false,
            "adjust_settings": { "RISK_PER_TRADE_PCT": "0.015", "SAFETY_DRAWDOWN_BREAKER_ENABLED": "true" },
            "bypass_strategy_routing": "session_momentum",
            "memory_note_for_next_cycle": "Increased risk slightly and restricted routing to Session Momentum to isolate the chop edge."
        }'''

if __name__ == "__main__":
    logger.info("Initializing Sentinel AI (Seasoned Trader) Debug Harness...")
    # Instantiate with mocked LLM to guarantee offline testing functionality without billing user
    daemon = SeasonedTraderDaemon(MockAIClient(), {"AI_MONETARY_PATH": "aggressive", "AI_PERSONALITY": "The Calculating Quant"})
    
    logger.info("Initiating AI Evaluation Cycle...")
    daemon._evaluate_and_adjust()
    
    logger.info("Verifying Persistent Scratchpad Memory Injection...")
    print("\n" + daemon.memory.get_contextual_memory() + "\n")
    
    logger.info("Sentinel AI Debug Harness Check: PASSED.")
