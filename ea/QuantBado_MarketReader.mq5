#property strict

input string API_URL  = "http://api.quantbado.online/analyze";
input string USER_KEY = "QB-USER-001";
input int CandlesToSend = 50;
input int UpdateSeconds = 5;

string lastResponse = "";

int OnInit()
{
   EventSetTimer(UpdateSeconds);
   Print("QuantBado Market Reader started");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");

   string objs[] = {
      "QB_Title","QB_Line","QB_Symbol","QB_TF","QB_Signal",
      "QB_Strength","QB_Trend","QB_Momentum","QB_Support",
      "QB_Resistance","QB_Notes"
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
      case PERIOD_M1: return "M1";
      case PERIOD_M5: return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1: return "H1";
      case PERIOD_H4: return "H4";
      case PERIOD_D1: return "D1";
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
      Print("Not enough candles: ", copied);
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

   StringToCharArray(json, post, 0, StringLen(json));

   ResetLastError();

   int res = WebRequest(
      "POST",
      API_URL,
      headers,
      5000,
      post,
      result,
      resultHeaders
   );

   if(res == -1)
   {
      int err = GetLastError();
      Print("WebRequest Error: ", err);
      Comment("QuantBado Error\nWebRequest failed: ", err);
      return;
   }

   string response = CharArrayToString(result, 0, -1, CP_UTF8);
   lastResponse = response;

   string signal = ExtractValue(response, "signal");
   string strength = ExtractValue(response, "strength");
   string trend = ExtractValue(response, "trend");
   string momentum = ExtractValue(response, "momentum");
   string support = ExtractValue(response, "support");
   string resistance = ExtractValue(response, "resistance");
   string notes = ExtractValue(response, "notes");

   DrawDashboard(signal, strength, trend, momentum, support, resistance, notes);

   Print("Server Response: ", response);
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

      if(c == ',' || c == '}')
         break;

      if(c == '\"')
         break;

      end++;
   }

   return StringSubstr(json, start, end - start);
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

void DrawDashboard(string signal, string strength, string trend, string momentum, string support, string resistance, string notes)
{
   color signalColor = clrWhite;

   if(signal == "BUY")
      signalColor = clrLime;
   else if(signal == "SELL")
      signalColor = clrRed;
   else
      signalColor = clrGold;

   DrawLabel("QB_Title", "QuantBado Market Reader", 15, 25, 13, clrDeepSkyBlue);
   DrawLabel("QB_Line", "-----------------------------", 15, 45, 10, clrGray);

   DrawLabel("QB_Symbol", "Symbol: " + _Symbol, 15, 65, 10, clrWhite);
   DrawLabel("QB_TF", "Timeframe: " + TimeframeToString(_Period), 15, 85, 10, clrWhite);

   DrawLabel("QB_Signal", "Signal: " + signal, 15, 115, 14, signalColor);
   DrawLabel("QB_Strength", "Strength: " + strength + " / 100", 15, 140, 11, clrWhite);

   DrawLabel("QB_Trend", "Trend: " + trend, 15, 170, 10, clrWhite);
   DrawLabel("QB_Momentum", "Momentum: " + momentum, 15, 190, 10, clrWhite);

   DrawLabel("QB_Support", "Support: " + support, 15, 220, 10, clrLime);
   DrawLabel("QB_Resistance", "Resistance: " + resistance, 15, 240, 10, clrTomato);

   DrawLabel("QB_Notes", "Notes: " + notes, 15, 270, 9, clrSilver);
}
