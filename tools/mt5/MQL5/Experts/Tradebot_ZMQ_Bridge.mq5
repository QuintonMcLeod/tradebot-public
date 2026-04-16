//+------------------------------------------------------------------+
//|                                       Tradebot_ZMQ_Bridge.mq5 |
//|                                  Copyright 2026, Tradebot SCI   |
//+------------------------------------------------------------------+
#property copyright "Tradebot SCI"
#property link      "https://github.com/tradebot-sci"
#property version   "1.00"

#include <Zmq/Zmq.mqh>

input int REP_PORT = 5555; // Port for receiving execution commands

Context *zmq_context;
Socket *req_rep_socket;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   Print("[MT5-ZMQ] Step 1: Starting EA Initialization...");

   Print("[MT5-ZMQ] Step 2: Creating Context...");
   zmq_context = new Context("TradebotSCI");
   
   Print("[MT5-ZMQ] Step 3: Creating Socket...");
   req_rep_socket = new Socket(*zmq_context, ZMQ_REP);
   
   string binding_address = "tcp://*:5555";
   Print("[MT5-ZMQ] Step 4: Binding Socket to ", binding_address, "...");
   if (!req_rep_socket.bind(binding_address))
     {
      Print("[MT5-ZMQ] Failed to bind to ZMQ Server on ", binding_address);
      return(INIT_FAILED);
     }
     
   Print("[MT5-ZMQ] Step 5: Setting Timer...");
   // Enable a timer to poll for ZMQ messages constantly
   EventSetMillisecondTimer(100);

   Print("[MT5-ZMQ] Successfully bound and initialized!");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   delete req_rep_socket;
   delete zmq_context;
   Print("[MT5-ZMQ] ZMQ Socket Closed.");
  }

//+------------------------------------------------------------------+
//| Timer event                                                      |
//+------------------------------------------------------------------+
void OnTimer()
  {
   // Check if we have incoming messages
   ZmqMsg request;
   if(req_rep_socket.recv(request, ZMQ_DONTWAIT))
     {
      string payload = request.getData();
      Print("[MT5-ZMQ] Received Msg: ", payload);
      
      string response = ProcessCommand(payload);
      
      ZmqMsg reply(response);
      req_rep_socket.send(reply);
     }
  }

//+------------------------------------------------------------------+
//| Process the incoming JSON string command                         |
//+------------------------------------------------------------------+
string ProcessCommand(string json_payload)
  {
   if (StringFind(json_payload, "\"action\": \"GET_ACCOUNT\"") >= 0)
     {
      double bal = AccountInfoDouble(ACCOUNT_BALANCE);
      double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
      return StringFormat("{\"status\":\"success\", \"account\":{\"balance\":%f, \"equity\":%f}}", bal, eq);
     }
     
   if (StringFind(json_payload, "\"action\": \"EXECUTE\"") >= 0)
     {
      return "{\"status\":\"success\", \"message\":\"Trade executed (simulated)\", \"ticket\": 12345}";
     }
     
   if (StringFind(json_payload, "\"action\": \"FLATTEN\"") >= 0)
     {
      return "{\"status\":\"success\", \"message\":\"Positions flattened\"}";
     }
     
   return "{\"status\":\"error\", \"message\":\"Unknown action\"}";
  }
//+------------------------------------------------------------------+
