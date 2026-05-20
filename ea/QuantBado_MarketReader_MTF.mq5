//+------------------------------------------------------------------+
//| QuantBado Market Reader MTF                                      |
//| Multi-Timeframe EA: M1 + M5 + M15 + H1                           |
//| Sends candles to FastAPI /analyze-mtf                            |
//| Reader only - no trading orders                                  |
//+------------------------------------------------------------------+
#property strict
#property version   "2.4"
#property description "QuantBado Market Reader MTF - reader only"

input string InpServerUrl = "http://quantbado.online/analyze-mtf";
input string InpUserKey   = "test123";
input int    InpCandles   = 50;
input int    InpTimerSec  = 20;
input bool   InpShowPanel = true;

string g_lastResponse = "";
datetime g_lastRequestTime = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(InpTimerSec);

   Print("QuantBado MTF EA started.");
   Print("Server URL: ", InpServerUrl);
   Print("Symbol: ", _Symbol);
   Print("Reader only. No trading functions.");

   SendMTFRequest();

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

//+------------------------------------------------------------------+
//| Timer                                                            |
//+------------------------------------------------------------------+
void OnTimer()
{
   SendMTFRequest();
}

//+------------------------------------------------------------------+
//| Tick                                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   if(InpShowPanel)
      DrawPanel();
}

//+------------------------------------------------------------------+
//| Escape JSON string                                               |
//+------------------------------------------------------------------+
string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   return value;
}

//+------------------------------------------------------------------+
//| Timeframe to string                                              |
//+------------------------------------------------------------------+
string TFToString(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_M1)  return "M1";
   if(tf == PERIOD_M5)  return "M5";
   if(tf == PERIOD_M15) return "M15";
   if(tf == PERIOD_H1)  return "H1";
   return "UNKNOWN";
}

//+------------------------------------------------------------------+
//| Build candles JSON array                                         |
//+------------------------------------------------------------------+
bool BuildCandlesJson(ENUM_TIMEFRAMES tf, string &jsonOut)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);

   int copied = CopyRates(_Symbol, tf, 0, InpCandles, rates);

   if(copied < 40)
   {
      Print("Not enough candles for ", TFToString(tf), ". Copied: ", copied);
      return false;
   }

   jsonOut = "[";

   // Send oldest to newest
   for(int i = copied - 1; i >= 0; i--)
   {
      string candle = "{";
      candle += "\"time\":"  + IntegerToString((long)rates[i].time) + ",";
      candle += "\"open\":"  + DoubleToString(rates[i].open, _Digits) + ",";
      candle += "\"high\":"  + DoubleToString(rates[i].high, _Digits) + ",";
      candle += "\"low\":"   + DoubleToString(rates[i].low, _Digits) + ",";
      candle += "\"close\":" + DoubleToString(rates[i].close, _Digits);
      candle += "}";

      jsonOut += candle;

      if(i > 0)
         jsonOut += ",";
   }

   jsonOut += "]";
   return true;
}

//+------------------------------------------------------------------+
//| Build full request body                                          |
//+------------------------------------------------------------------+
bool BuildRequestBody(string &body)
{
   string m1, m5, m15, h1;

   bool okM1  = BuildCandlesJson(PERIOD_M1, m1);
   bool okM5  = BuildCandlesJson(PERIOD_M5, m5);
   bool okM15 = BuildCandlesJson(PERIOD_M15, m15);
   bool okH1  = BuildCandlesJson(PERIOD_H1, h1);

   if(!okM1 || !okM5 || !okM15 || !okH1)
   {
      Print("MTF request skipped. Missing candle data.");
      return false;
   }

   body = "{";
   body += "\"user_key\":\"" + JsonEscape(InpUserKey) + "\",";
   body += "\"symbol\":\"" + JsonEscape(_Symbol) + "\",";
   body += "\"candles_by_timeframe\":{";
   body += "\"M1\":"  + m1  + ",";
   body += "\"M5\":"  + m5  + ",";
   body += "\"M15\":" + m15 + ",";
   body += "\"H1\":"  + h1;
   body += "}";
   body += "}";

   return true;
}

//+------------------------------------------------------------------+
//| Send request                                                     |
//+------------------------------------------------------------------+
void SendMTFRequest()
{
   string body;

   if(!BuildRequestBody(body))
      return;

   char post[];
   char result[];
   string headers = "Content-Type: application/json\r\n";
   string resultHeaders = "";

   // IMPORTANT:
   // Do not use WHOLE_ARRAY here.
   // WHOLE_ARRAY adds null/extra bytes and FastAPI returns 422 JSON decode error.
   int bodyLen = StringLen(body);
   ArrayResize(post, bodyLen);
   StringToCharArray(body, post, 0, bodyLen, CP_UTF8);

   ResetLastError();

   int status = WebRequest(
      "POST",
      InpServerUrl,
      headers,
      15000,
      post,
      result,
      resultHeaders
   );

   g_lastRequestTime = TimeCurrent();

   if(status == -1)
   {
      int err = GetLastError();
      g_lastResponse = "WebRequest failed. Error: " + IntegerToString(err);
      Print(g_lastResponse);
      return;
   }

   g_lastResponse = CharArrayToString(result, 0, -1, CP_UTF8);

   Print("MTF WebRequest status: ", status);
   Print("MTF Response: ", g_lastResponse);

   if(InpShowPanel)
      DrawPanel();
}

//+------------------------------------------------------------------+
//| Extract simple JSON value                                        |
//+------------------------------------------------------------------+
string ExtractJsonString(string json, string key)
{
   string pattern = "\"" + key + "\":";
   int pos = StringFind(json, pattern);

   if(pos < 0)
      return "";

   pos += StringLen(pattern);

   while(pos < StringLen(json) && StringGetCharacter(json, pos) == ' ')
      pos++;

   if(pos >= StringLen(json))
      return "";

   if(StringGetCharacter(json, pos) == '"')
   {
      pos++;
      int endPos = StringFind(json, "\"", pos);
      if(endPos > pos)
         return StringSubstr(json, pos, endPos - pos);
   }
   else
   {
      int endComma = StringFind(json, ",", pos);
      int endBrace = StringFind(json, "}", pos);

      int endPos = endComma;
      if(endPos < 0 || (endBrace > 0 && endBrace < endPos))
         endPos = endBrace;

      if(endPos > pos)
         return StringSubstr(json, pos, endPos - pos);
   }

   return "";
}

//+------------------------------------------------------------------+
//| Draw simple panel                                                |
//+------------------------------------------------------------------+
void DrawPanel()
{
   string signal     = ExtractJsonString(g_lastResponse, "signal");
   string confidence = ExtractJsonString(g_lastResponse, "confidence");
   string bias       = ExtractJsonString(g_lastResponse, "bias");
   string entryTf    = ExtractJsonString(g_lastResponse, "entry_timeframe");
   string entry      = ExtractJsonString(g_lastResponse, "entry");
   string sl         = ExtractJsonString(g_lastResponse, "sl");
   string tp1        = ExtractJsonString(g_lastResponse, "tp1");
   string tp2        = ExtractJsonString(g_lastResponse, "tp2");
   string tp3        = ExtractJsonString(g_lastResponse, "tp3");
   string reason     = ExtractJsonString(g_lastResponse, "reason");
   string mtfVersion = ExtractJsonString(g_lastResponse, "mtf_version");

   if(signal == "")
      signal = "WAIT";

   string text = "";
   text += "QuantBado MTF Reader\n";
   text += "Symbol: " + _Symbol + "\n";
   text += "Server: " + InpServerUrl + "\n";
   text += "Last request: " + TimeToString(g_lastRequestTime, TIME_SECONDS) + "\n";
   text += "------------------------------\n";
   text += "Signal: " + signal + "\n";
   text += "Confidence: " + confidence + "\n";
   text += "Bias: " + bias + "\n";
   text += "Entry TF: " + entryTf + "\n";
   text += "Entry: " + entry + "\n";
   text += "SL: " + sl + "\n";
   text += "TP1: " + tp1 + "\n";
   text += "TP2: " + tp2 + "\n";
   text += "TP3: " + tp3 + "\n";
   text += "Reason: " + reason + "\n";
   text += "Version: " + mtfVersion + "\n";
   text += "------------------------------\n";
   text += "Reader only. No orders.";

   Comment(text);
}
//+------------------------------------------------------------------+