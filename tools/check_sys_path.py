import sys
import os
import tradebot_sci

print(f"Current Working Directory: {os.getcwd()}")
print(f"tradebot_sci file: {tradebot_sci.__file__}")
print("sys.path:")
for p in sys.path:
    print(f"  {p}")
