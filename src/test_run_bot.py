import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from tradebot_sci.runtime.loop import run_bot

if __name__ == "__main__":
    print("Starting run_bot(iterations=1) verification...")
    try:
        run_bot(iterations=1)
        print("SUCCESS: run_bot(iterations=1) completed successfully without errors!")
    except Exception as e:
        print(f"FAILED: run_bot raised an exception: {e}")
        sys.exit(1)
