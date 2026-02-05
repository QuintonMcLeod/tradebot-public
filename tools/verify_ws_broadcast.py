import asyncio
import websockets
import json
import os
import sys

async def verify_broadcast():
    uri = os.getenv("GUI_WS_URL", "ws://localhost:8080/ws")
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected. Waiting for log messages...")
            
            # Whitelisted tags to check
            target_tags = ["[DECISION]", "[STRUCTURE]", "[SAFETY]", "[PHOENIX]", "[ENTRY]", "[HOLD]"]
            found_tags = set()
            
            # Listen for a few seconds or until we find some tags
            try:
                while len(found_tags) < len(target_tags):
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                        data = json.loads(message)
                        
                        if data.get("type") == "log":
                            log_msg = data.get("data", "")
                            for tag in target_tags:
                                if tag in log_msg:
                                    print(f"Found whitelisted tag: {tag}")
                                    found_tags.add(tag)
                        
                        if len(found_tags) > 0:
                            print(f"Progress: {len(found_tags)}/{len(target_tags)} tags found.")
                            
                    except asyncio.TimeoutError:
                        print("Timeout waiting for messages. Bot might be idle.")
                        break
            except Exception as e:
                print(f"Error during message reception: {e}")
                
            print("\nVerification Results:")
            for tag in target_tags:
                status = "✅ Found" if tag in found_tags else "❌ Not seen (might be idle)"
                print(f"{tag}: {status}")
                
    except Exception as e:
        print(f"Could not connect to WebSocket: {e}")
        print("Ensure the tradebot is running with the WS server enabled.")

if __name__ == "__main__":
    asyncio.run(verify_broadcast())
