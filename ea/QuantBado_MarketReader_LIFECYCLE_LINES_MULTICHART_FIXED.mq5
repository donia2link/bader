#property strict
#property version   "1.30"

input string API_URL  = "http://api.quantbado.online/analyze";
input string USER_KEY = "test123";
input int    CandlesToSend = 50;
input int    UpdateSeconds = 5;

string lastResponse = "";
string ObjPrefix = "";

string BuildObjPrefix()
{
   return "QB_" + IntegerToString((int)ChartID()) + "_" + _Symbol + "_" + TimeframeToString(_Period) + "_";
}

string ObjName(string name)
{
   return ObjPrefix + name;
}

int OnInit()
{
   ObjPrefix = BuildObjPrefix();
   DeleteOldFixedObjects();
   EventSetTimer(UpdateSeconds);
   Print("QuantBado Market Reader started");
   SendMarketData();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");

   string objs[] = {
      "BG","Title","Line","Symbol","TF","Status","Signal",
      "Strength","Trend","Momentum","Support","Resistance","Notes",
      "LifeStatus","SignalID","Entry","SL","TP1","TP2","TP3","LifeReason",
      "LINE_ENTRY","LINE_SL","LINE_TP1","LINE_TP2","LINE_TP3","SIGNAL_LABEL"
   };

   for(int i = 0; i < ArraySize(objs); i++)
      ObjectDelete(0, ObjName(objs[i]));
}

void OnTimer()
{
   SendMarketData();
}

string TimeframeToString(ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      default: return IntegerToString((int)tf);
   }
}

void SendMarketData()
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);

   int copied = CopyRates(_Symbol, _Period, 0, CandlesToSend, rates);

   if(copied < 20)
   {
      Print("QuantBado: Not enough candles: ", copied);
      DrawDashboard("WAIT", "0", "unknown", "unknown", "-", "-", "-", "-", "-", "-", "-", "-", "No Signal", "", "Not enough candles", "ERROR", "Not enough candles");
      return;
   }

   string json = "{";
   json += "\"user_key\":\"" + USER_KEY + "\",";
   json += "\"symbol\":\"" + _Symbol + "\",";
   json += "\"timeframe\":\"" + TimeframeToString(_Period) + "\",";
   json += "\"candles\":[";

   for(int i = copied - 1; i >= 0; i--)
   {
      json += "{";
      json += "\"time\":" + IntegerToString((int)rates[i].time) + ",";
      json += "\"open\":" + DoubleToString(rates[i].open, _Digits) + ",";
      json += "\"high\":" + DoubleToString(rates[i].high, _Digits) + ",";
      json += "\"low\":" + DoubleToString(rates[i].low, _Digits) + ",";
      json += "\"close\":" + DoubleToString(rates[i].close, _Digits);
      json += "}";

      if(i > 0)
         json += ",";
   }

   json += "]}";

   char post[];
   char result[];
   string headers = "Content-Type: application/json\r\n";
   string resultHeaders;

   StringToCharArray(json, post, 0, WHOLE_ARRAY, CP_UTF8);
   if(ArraySize(post) > 0)
      ArrayResize(post, ArraySize(post) - 1);

   ResetLastError();

   int res = WebRequest(
      "POST",
      API_URL,
      headers,
      10000,
      post,
      result,
      resultHeaders
   );

   if(res == -1)
   {
      int err = GetLastError();
      Print("QuantBado WebRequest Error: ", err);
      Print("Allow this URL in MT5 WebRequest: http://quantbado.online");
      DrawDashboard("WAIT", "0", "unknown", "unknown", "-", "-", "-", "-", "-", "-", "-", "-", "No Signal", "", "WebRequest failed", "ERROR", "WebRequest failed: " + IntegerToString(err));
      return;
   }

   string response = CharArrayToString(result, 0, -1, CP_UTF8);
   lastResponse = response;

   string status = ExtractValue(response, "status");
   string signal = ExtractValue(response, "signal");
   string strength = ExtractValue(response, "strength");
   string trend = ExtractValue(response, "trend");
   string momentum = ExtractValue(response, "momentum");
   string support = ExtractValue(response, "support");
   string resistance = ExtractValue(response, "resistance");
   string notes = ExtractValue(response, "notes");
   string message = ExtractValue(response, "message");

   string entry = ExtractValue(response, "entry");
   string sl = ExtractValue(response, "sl");
   string tp1 = ExtractValue(response, "tp1");
   string tp2 = ExtractValue(response, "tp2");
   string tp3 = ExtractValue(response, "tp3");

   string signalStatus = ExtractNestedValue(response, "signal_lifecycle", "signal_status");
   string signalId = ExtractNestedValue(response, "signal_lifecycle", "signal_id");
   string lifecycleReason = ExtractNestedValue(response, "signal_lifecycle", "lifecycle_reason");

   if(status != "ok")
   {
      if(message == "")
         message = response;
      DrawDashboard("WAIT", "0", "unknown", "unknown", "-", "-", "-", "-", "-", "-", "-", "-", "No Signal", "", message, "ERROR", message);
      Print("QuantBado Server Error: ", response);
      return;
   }

   if(signal == "") signal = "WAIT";
   if(strength == "") strength = "0";
   if(trend == "") trend = "unknown";
   if(momentum == "") momentum = "unknown";
   if(support == "") support = "-";
   if(resistance == "") resistance = "-";
   if(notes == "") notes = "QuantBado active";

   if(entry == "") entry = "-";
   if(sl == "") sl = "-";
   if(tp1 == "") tp1 = "-";
   if(tp2 == "") tp2 = "-";
   if(tp3 == "") tp3 = "-";
   if(signalStatus == "") signalStatus = "No Signal";
   if(signalId == "") signalId = "-";
   if(lifecycleReason == "") lifecycleReason = "-";

   DrawDashboard(signal, strength, trend, momentum, support, resistance, entry, sl, tp1, tp2, tp3, notes, signalStatus, signalId, lifecycleReason, "OK", lifecycleReason);
   DrawSignalLines(signal, signalStatus, signalId, entry, sl, tp1, tp2, tp3);

   Print("QuantBado HTTP Status: ", res);
   Print("QuantBado Server Response: ", response);
}

string ExtractValue(string json, string key)
{
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);

   if(start == -1)
      return "";

   start += StringLen(search);

   while(start < StringLen(json))
   {
      ushort c = StringGetCharacter(json, start);
      if(c != ' ' && c != '\"')
         break;
      start++;
   }

   int end = start;

   while(end < StringLen(json))
   {
      ushort c = StringGetCharacter(json, end);
      if(c == ',' || c == '}' || c == '\"')
         break;
      end++;
   }

   return StringSubstr(json, start, end - start);
}

string ExtractObject(string json, string objectKey)
{
   string search = "\"" + objectKey + "\":{";
   int start = StringFind(json, search);

   if(start == -1)
      return "";

   start += StringLen(search) - 1;

   int depth = 0;
   int end = start;

   while(end < StringLen(json))
   {
      ushort c = StringGetCharacter(json, end);

      if(c == '{')
         depth++;
      else if(c == '}')
      {
         depth--;
         if(depth == 0)
            return StringSubstr(json, start, end - start + 1);
      }

      end++;
   }

   return "";
}

string ExtractNestedValue(string json, string objectKey, string key)
{
   string obj = ExtractObject(json, objectKey);

   if(obj == "")
      return "";

   return ExtractValue(obj, key);
}

string Shorten(string text, int maxLen)
{
   if(StringLen(text) <= maxLen)
      return text;

   return StringSubstr(text, 0, maxLen - 3) + "...";
}

void DrawBackground()
{
   if(ObjectFind(0, ObjName("BG")) < 0)
   {
      ObjectCreate(0, ObjName("BG"), OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_XDISTANCE, 8);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_YDISTANCE, 18);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_XSIZE, 390);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_YSIZE, 465);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_BACK, false);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_COLOR, clrDarkSlateGray);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, ObjName("BG"), OBJPROP_BGCOLOR, clrBlack);
   }
}

void DrawLabel(string name, string text, int x, int y, int size, color clr)
{
   string obj = ObjName(name);

   if(ObjectFind(0, obj) < 0)
   {
      ObjectCreate(0, obj, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, obj, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, obj, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, obj, OBJPROP_YDISTANCE, y);
      ObjectSetString(0, obj, OBJPROP_FONT, "Arial");
   }

   ObjectSetString(0, obj, OBJPROP_TEXT, text);
   ObjectSetInteger(0, obj, OBJPROP_FONTSIZE, size);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, clr);
}

void DeleteOldFixedObjects()
{
   string oldObjs[] = {
      "QB_BG","QB_Title","QB_Line","QB_Symbol","QB_TF","QB_Status","QB_Signal",
      "QB_Strength","QB_Trend","QB_Momentum","QB_Support","QB_Resistance","QB_Notes",
      "QB_LifeStatus","QB_SignalID","QB_Entry","QB_SL","QB_TP1","QB_TP2","QB_TP3","QB_LifeReason",
      "QB_LINE_ENTRY","QB_LINE_SL","QB_LINE_TP1","QB_LINE_TP2","QB_LINE_TP3","QB_SIGNAL_LABEL"
   };

   for(int i = 0; i < ArraySize(oldObjs); i++)
      ObjectDelete(0, oldObjs[i]);
}

double ToDoubleSafe(string value)
{
   if(value == "" || value == "-" || value == "null")
      return 0.0;

   return StringToDouble(value);
}

void DrawQBLine(string name, double price, string text, color clr, ENUM_LINE_STYLE style)
{
   if(price <= 0)
      return;

   string obj = ObjName(name);

   if(ObjectFind(0, obj) < 0)
   {
      ObjectCreate(0, obj, OBJ_HLINE, 0, 0, price);
      ObjectSetInteger(0, obj, OBJPROP_BACK, false);
      ObjectSetInteger(0, obj, OBJPROP_SELECTABLE, true);
      ObjectSetInteger(0, obj, OBJPROP_WIDTH, 2);
   }

   ObjectSetDouble(0, obj, OBJPROP_PRICE, price);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, obj, OBJPROP_STYLE, style);
   ObjectSetString(0, obj, OBJPROP_TEXT, text + " " + DoubleToString(price, _Digits));
}

void DrawSignalLabel(string signal, string status, string signalId, double entryPrice)
{
   if(entryPrice <= 0)
      return;

   string obj = ObjName("SIGNAL_LABEL");

   if(ObjectFind(0, obj) < 0)
   {
      ObjectCreate(0, obj, OBJ_TEXT, 0, TimeCurrent(), entryPrice);
      ObjectSetInteger(0, obj, OBJPROP_ANCHOR, ANCHOR_LEFT);
      ObjectSetInteger(0, obj, OBJPROP_FONTSIZE, 9);
      ObjectSetString(0, obj, OBJPROP_FONT, "Arial");
      ObjectSetInteger(0, obj, OBJPROP_SELECTABLE, true);
   }

   string shortId = signalId;
   if(StringLen(shortId) > 8)
      shortId = StringSubstr(shortId, 0, 8);

   color clr = clrGold;
   if(signal == "BUY")
      clr = clrLime;
   else if(signal == "SELL")
      clr = clrTomato;

   ObjectMove(0, obj, 0, TimeCurrent(), entryPrice);
   ObjectSetString(0, obj, OBJPROP_TEXT, "QB " + signal + " | " + status + " | " + shortId);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, clr);
}

void DeleteSignalLines()
{
   string objs[] = {"LINE_ENTRY", "LINE_SL", "LINE_TP1", "LINE_TP2", "LINE_TP3", "SIGNAL_LABEL"};

   for(int i = 0; i < ArraySize(objs); i++)
   {
      string obj = ObjName(objs[i]);
      if(ObjectFind(0, obj) >= 0)
         ObjectDelete(0, obj);
   }
}

void DrawSignalLines(
   string signal,
   string signalStatus,
   string signalId,
   string entry,
   string sl,
   string tp1,
   string tp2,
   string tp3
)
{
   if(signalStatus == "No Signal" || signalStatus == "" || signal == "WAIT")
   {
      DeleteSignalLines();
      return;
   }

   double entryPrice = ToDoubleSafe(entry);
   double slPrice = ToDoubleSafe(sl);
   double tp1Price = ToDoubleSafe(tp1);
   double tp2Price = ToDoubleSafe(tp2);
   double tp3Price = ToDoubleSafe(tp3);

   if(entryPrice <= 0 || slPrice <= 0)
      return;

   DrawQBLine("LINE_ENTRY", entryPrice, "QB ENTRY", clrDodgerBlue, STYLE_SOLID);
   DrawQBLine("LINE_SL", slPrice, "QB SL", clrTomato, STYLE_SOLID);
   DrawQBLine("LINE_TP1", tp1Price, "QB TP1", clrLimeGreen, STYLE_DASH);
   DrawQBLine("LINE_TP2", tp2Price, "QB TP2", clrGreen, STYLE_DASH);
   DrawQBLine("LINE_TP3", tp3Price, "QB TP3", clrDarkGreen, STYLE_DASH);

   DrawSignalLabel(signal, signalStatus, signalId, entryPrice);
}


void DrawDashboard(
   string signal,
   string strength,
   string trend,
   string momentum,
   string support,
   string resistance,
   string entry,
   string sl,
   string tp1,
   string tp2,
   string tp3,
   string notes,
   string signalStatus,
   string signalId,
   string lifecycleReason,
   string status,
   string detailReason
)
{
   DrawBackground();

   color signalColor = clrGold;
   if(signal == "BUY")
      signalColor = clrLime;
   else if(signal == "SELL")
      signalColor = clrTomato;

   color statusColor = (status == "OK") ? clrLime : clrTomato;

   color lifeColor = clrSilver;
   if(signalStatus == "Active" || signalStatus == "In Profit")
      lifeColor = clrLime;
   else if(signalStatus == "SL Hit" || signalStatus == "Expired")
      lifeColor = clrTomato;
   else if(signalStatus == "Detected" || signalStatus == "Waiting Confirmation")
      lifeColor = clrGold;

   DrawLabel("Title", "QuantBado Market Reader", 18, 28, 13, clrDeepSkyBlue);
   DrawLabel("Line", "-------------------------------", 18, 48, 10, clrGray);

   DrawLabel("Symbol", "Symbol: " + _Symbol, 18, 68, 10, clrWhite);
   DrawLabel("TF", "Timeframe: " + TimeframeToString(_Period), 18, 88, 10, clrWhite);
   DrawLabel("Status", "Server: " + status, 18, 108, 10, statusColor);

   DrawLabel("Signal", "Signal: " + signal, 18, 135, 14, signalColor);
   DrawLabel("Strength", "Strength: " + strength + " / 100", 18, 160, 11, clrWhite);

   DrawLabel("LifeStatus", "Signal Status: " + signalStatus, 18, 185, 10, lifeColor);
   DrawLabel("SignalID", "Signal ID: " + signalId, 18, 205, 9, clrSilver);

   DrawLabel("Entry", "Entry: " + entry, 18, 230, 10, clrWhite);
   DrawLabel("SL", "SL: " + sl, 18, 250, 10, clrTomato);
   DrawLabel("TP1", "TP1: " + tp1, 18, 270, 10, clrLime);
   DrawLabel("TP2", "TP2: " + tp2, 18, 290, 10, clrLime);
   DrawLabel("TP3", "TP3: " + tp3, 18, 310, 10, clrLime);

   DrawLabel("Trend", "Trend: " + trend, 18, 340, 10, clrWhite);
   DrawLabel("Momentum", "Momentum: " + momentum, 18, 360, 10, clrWhite);

   DrawLabel("Support", "Support: " + support, 18, 385, 10, clrLime);
   DrawLabel("Resistance", "Resistance: " + resistance, 18, 405, 10, clrTomato);

   DrawLabel("Notes", "Notes: " + notes, 18, 430, 9, clrSilver);
   DrawLabel("LifeReason", "Reason: " + Shorten(lifecycleReason, 48), 18, 450, 9, clrSilver);
}

