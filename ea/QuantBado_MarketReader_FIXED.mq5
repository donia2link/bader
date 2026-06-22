#property strict
#property version   "1.01"

input string API_URL  = "http://api.quantbado.online/analyze";
input string USER_KEY = "test123";
input int    CandlesToSend = 50;
input int    UpdateSeconds = 5;

string lastResponse = "";

int OnInit()
{
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
      "QB_BG","QB_Title","QB_Line","QB_Symbol","QB_TF","QB_Status","QB_Signal",
      "QB_Strength","QB_Trend","QB_Momentum","QB_Support","QB_Resistance","QB_Notes"
   };

   for(int i = 0; i < ArraySize(objs); i++)
      ObjectDelete(0, objs[i]);
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
      DrawDashboard("WAIT", "0", "unknown", "unknown", "-", "-", "Not enough candles", "ERROR");
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
      DrawDashboard("WAIT", "0", "unknown", "unknown", "-", "-", "WebRequest failed: " + IntegerToString(err), "ERROR");
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

   if(status != "ok")
   {
      if(message == "")
         message = response;
      DrawDashboard("WAIT", "0", "unknown", "unknown", "-", "-", message, "ERROR");
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

   DrawDashboard(signal, strength, trend, momentum, support, resistance, notes, "OK");
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

void DrawBackground()
{
   if(ObjectFind(0, "QB_BG") < 0)
   {
      ObjectCreate(0, "QB_BG", OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, "QB_BG", OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, "QB_BG", OBJPROP_XDISTANCE, 8);
      ObjectSetInteger(0, "QB_BG", OBJPROP_YDISTANCE, 18);
      ObjectSetInteger(0, "QB_BG", OBJPROP_XSIZE, 330);
      ObjectSetInteger(0, "QB_BG", OBJPROP_YSIZE, 285);
      ObjectSetInteger(0, "QB_BG", OBJPROP_BACK, false);
      ObjectSetInteger(0, "QB_BG", OBJPROP_COLOR, clrDarkSlateGray);
      ObjectSetInteger(0, "QB_BG", OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, "QB_BG", OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, "QB_BG", OBJPROP_BGCOLOR, clrBlack);
   }
}

void DrawLabel(string name, string text, int x, int y, int size, color clr)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial");
   }

   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
}

void DrawDashboard(string signal, string strength, string trend, string momentum, string support, string resistance, string notes, string status)
{
   DrawBackground();

   color signalColor = clrGold;
   if(signal == "BUY")
      signalColor = clrLime;
   else if(signal == "SELL")
      signalColor = clrTomato;

   color statusColor = (status == "OK") ? clrLime : clrTomato;

   DrawLabel("QB_Title", "QuantBado Market Reader", 18, 28, 13, clrDeepSkyBlue);
   DrawLabel("QB_Line", "-----------------------------", 18, 48, 10, clrGray);

   DrawLabel("QB_Symbol", "Symbol: " + _Symbol, 18, 68, 10, clrWhite);
   DrawLabel("QB_TF", "Timeframe: " + TimeframeToString(_Period), 18, 88, 10, clrWhite);
   DrawLabel("QB_Status", "Server: " + status, 18, 108, 10, statusColor);

   DrawLabel("QB_Signal", "Signal: " + signal, 18, 135, 14, signalColor);
   DrawLabel("QB_Strength", "Strength: " + strength + " / 100", 18, 160, 11, clrWhite);

   DrawLabel("QB_Trend", "Trend: " + trend, 18, 190, 10, clrWhite);
   DrawLabel("QB_Momentum", "Momentum: " + momentum, 18, 210, 10, clrWhite);

   DrawLabel("QB_Support", "Support: " + support, 18, 240, 10, clrLime);
   DrawLabel("QB_Resistance", "Resistance: " + resistance, 18, 260, 10, clrTomato);

   DrawLabel("QB_Notes", "Notes: " + notes, 18, 285, 9, clrSilver);
}

