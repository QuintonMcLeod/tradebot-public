import zmq, json, time

ctx = zmq.Context()
sock = ctx.socket(zmq.REP)
sock.bind("tcp://*:5556")  # Wait, MT5 is already listening on 5555. Let's bind to 5556 and change bot config to 5556 for testing!

print("Mock MT5 listening on 5556")
while True:
    try:
        msg = sock.recv().decode()
        req = json.loads(msg)
        print("Received:", req)
        
        if req.get("action") == "GET_HISTORY":
            deals = [
                {"symbol": "EURUSD", "profit": 150.50, "volume": 1.0, "time": int(time.time()) - 86400, "comment": "Prop trade 1"},
                {"symbol": "GBPUSD", "profit": -50.00, "volume": 0.5, "time": int(time.time()) - 40000, "comment": "Prop trade 2"}
            ]
            resp = {"status": "success", "deals": deals}
            sock.send(json.dumps(resp).encode())
        elif req.get("action") == "GET_ACCOUNT":
            resp = {"status": "success", "account": {"balance": 100000, "equity": 100000}}
            sock.send(json.dumps(resp).encode())
        else:
            sock.send(b'{"status":"error", "message":"Unknown action"}')
    except Exception as e:
        print("Error:", e)
        time.sleep(1)
