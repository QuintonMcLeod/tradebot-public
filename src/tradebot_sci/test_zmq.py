import zmq, json
ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.connect("tcp://localhost:5555")
sock.setsockopt(zmq.RCVTIMEO, 5000)
try:
    sock.send(json.dumps({"action": "GET_HISTORY", "days": 30}).encode())
    print(sock.recv().decode())
except Exception as e:
    print(e)
