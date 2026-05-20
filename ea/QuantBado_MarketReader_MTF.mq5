//+------------------------------------------------------------------+
//| QuantBado Market Reader MTF                                      |
//| M1 + M5 + M15 + H1 + H4                                          |
//| Sends candles to FastAPI /analyze-mtf                            |
//| Reader only - no trading orders                                  |
//+------------------------------------------------------------------+
#property strict
#property version   "2.8"
#property description "QuantBado MTF Reader - individual timeframe strategy panel - reader only"

input string InpServerUrl = "http://quantbado.online/analyze-mtf";
input string InpUserKey   = "test123";
input int    InpCandles   = 50;
input int    InpTimerSec  = 20;

input bool   InpShowPanel = true;
input bool   InpDrawLines = true;

input int    InpPanelX    = 10;
input int    InpPanelY    = 28;
input int    InpLineBars  = 8;

input string InpLineFrame = "BEST"; // BEST, M1, M5, M15, H1, H4, MTF

string g_lastResponse = "";
datetime g_lastRequestTime = 0;

string PREFIX = "QB_MTF_";

//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(InpTimerSec);

   Print("QuantBado MTF EA v2.8 started.");
   Print("Server URL: ", InpServerUrl);
   Print("Symbol: ", _Symbol);
   Print("Reader only. No trading functions.");

   SendMTFRequest();

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   ClearObjects();
   Comment("");
}

//+------------------------------------------------------------------+
void OnTimer()
{
   SendMTFRequest();
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(InpShowPanel)
      DrawPanel();

   if(InpDrawLines)
      DrawTradeLines();
}

//+------------------------------------------------------------------+
void ClearObjects()
{
   int total = ObjectsTotal(0, 0, -1);

   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, -1);

      if(StringFind(name, PREFIX) == 0)
         ObjectDelete(0, name);
   }
}

//+------------------------------------------------------------------+
string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   return value;
}

//+------------------------------------------------------------------+
string TFToString(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_M1)  return "M1";
   if(tf == PERIOD_M5)  return "M5";
   if(tf == PERIOD_M15) return "M15";
   if(tf == PERIOD_H1)  return "H1";
   if(tf == PERIOD_H4)  return "H4";
   return "UNKNOWN";
}

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
bool BuildRequestBody(string &body)
{
   string m1, m5, m15, h1, h4;

   bool okM1  = BuildCandlesJson(PERIOD_M1, m1);
   bool okM5  = BuildCandlesJson(PERIOD_M5, m5);
   bool okM15 = BuildCandlesJson(PERIOD_M15, m15);
   bool okH1  = BuildCandlesJson(PERIOD_H1, h1);
   bool okH4  = BuildCandlesJson(PERIOD_H4, h4);

   if(!okM1 || !okM5 || !okM15 || !okH1 || !okH4)
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
   body += "\"H1\":"  + h1  + ",";
   body += "\"H4\":"  + h4;
   body += "}";
   body += "}";

   return true;
}

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

   if(InpDrawLines)
      DrawTradeLines();
}

//+------------------------------------------------------------------+
//| JSON simple extraction                                           |
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

double ExtractJsonDouble(string json, string key)
{
   string v = ExtractJsonString(json, key);
   if(v == "")
      return 0.0;

   return StringToDouble(v);
}

string ExtractObject(string json, string key)
{
   string pattern = "\"" + key + "\":{";
   int pos = StringFind(json, pattern);

   if(pos < 0)
      return "";

   pos += StringLen(pattern) - 1;

   int depth = 0;
   int start = pos;

   for(int i = pos; i < StringLen(json); i++)
   {
      ushort ch = StringGetCharacter(json, i);

      if(ch == '{')
         depth++;

      if(ch == '}')
      {
         depth--;

         if(depth == 0)
            return StringSubstr(json, start, i - start + 1);
      }
   }

   return "";
}

string ExtractIndividualTF(string tf)
{
   string individual = ExtractObject(g_lastResponse, "individual_signals");

   if(individual == "")
      return "";

   return ExtractObject(individual, tf);
}

//+------------------------------------------------------------------+
//| Theme                                                            |
//+------------------------------------------------------------------+
bool IsDarkChart()
{
   long bg = ChartGetInteger(0, CHART_COLOR_BACKGROUND, 0);

   int r = (int)(bg & 0xFF);
   int g = (int)((bg >> 8) & 0xFF);
   int b = (int)((bg >> 16) & 0xFF);

   int brightness = (r + g + b) / 3;

   return brightness < 128;
}

color PanelBgColor()
{
   if(IsDarkChart())
      return C'5,12,18';

   return C'248,250,252';
}

color PanelTextColor()
{
   if(IsDarkChart())
      return clrWhite;

   return C'15,23,42';
}

color MutedTextColor()
{
   if(IsDarkChart())
      return C'160,170,180';

   return C'75,85,99';
}

color BorderColor()
{
   return C'37,99,235';
}

color HeaderColor()
{
   return C'0,80,150';
}

color BuyColor()
{
   return C'0,210,100';
}

color SellColor()
{
   return C'230,57,70';
}

color WaitColor()
{
   return C'245,158,11';
}

color SignalColor(string signal)
{
   if(signal == "BUY")
      return BuyColor();

   if(signal == "SELL")
      return SellColor();

   return WaitColor();
}

color EntryColor()
{
   return C'0,145,255';
}

color SLColor()
{
   return C'230,57,70';
}

color TPColor()
{
   return C'0,170,85';
}

//+------------------------------------------------------------------+
//| Objects                                                          |
//+------------------------------------------------------------------+
void CreateRect(string name, int x, int y, int w, int h, color bg, color border)
{
   string obj = PREFIX + name;

   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, OBJ_RECTANGLE_LABEL, 0, 0, 0);

   ObjectSetInteger(0, obj, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, obj, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, obj, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, obj, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, obj, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, obj, OBJPROP_BGCOLOR, bg);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, border);
   ObjectSetInteger(0, obj, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, obj, OBJPROP_BACK, false);
   ObjectSetInteger(0, obj, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, obj, OBJPROP_HIDDEN, true);
}

void CreateLabel(string name, string text, int x, int y, color clr, int size = 9, bool bold = false)
{
   string obj = PREFIX + name;

   if(ObjectFind(0, obj) < 0)
      ObjectCreate(0, obj, OBJ_LABEL, 0, 0, 0);

   ObjectSetInteger(0, obj, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, obj, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, obj, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, obj, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, obj, OBJPROP_FONTSIZE, size);
   ObjectSetString(0, obj, OBJPROP_FONT, bold ? "Arial Bold" : "Arial");
   ObjectSetString(0, obj, OBJPROP_TEXT, text);
   ObjectSetInteger(0, obj, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, obj, OBJPROP_HIDDEN, true);
}

//+------------------------------------------------------------------+
//| Panel rows                                                       |
//+------------------------------------------------------------------+
string CleanSignal(string signal)
{
   if(signal == "")
      return "WAIT";

   return signal;
}

string CleanTrend(string trendDir)
{
   if(trendDir == "")
      return "FLAT";

   return trendDir;
}

string ShortQuality(string q)
{
   if(q == "")
      return "No Trade";

   return q;
}

void DrawFrameBox(string tf, int x, int y)
{
   string obj = ExtractIndividualTF(tf);

   string signal = CleanSignal(ExtractJsonString(obj, "signal"));
   string trendDir = CleanTrend(ExtractJsonString(obj, "trend_direction"));
   string quality = ShortQuality(ExtractJsonString(obj, "quality"));

   double entry = ExtractJsonDouble(obj, "entry");
   double sl = ExtractJsonDouble(obj, "sl");
   double target = ExtractJsonDouble(obj, "target");

   color bg = PanelBgColor();
   color border = SignalColor(signal);
   color txt = PanelTextColor();
   color muted = MutedTextColor();
   color sigClr = SignalColor(signal);

   CreateRect("BOX_" + tf, x, y, 255, 72, bg, border);

   CreateLabel("TF_" + tf, tf + " Trend: " + trendDir, x + 8, y + 6, sigClr, 10, true);
   CreateLabel("Q_" + tf, "Quality: " + quality, x + 8, y + 24, SignalColor(signal), 9, false);

   if(signal == "WAIT" || entry <= 0)
   {
      CreateLabel("E_" + tf, "Entry: Waiting setup", x + 8, y + 43, muted, 8, false);
      CreateLabel("T_" + tf, "TP / SL: --", x + 8, y + 58, muted, 8, false);
      return;
   }

   CreateLabel("E_" + tf, "Entry: " + signal + " " + DoubleToString(entry, _Digits), x + 8, y + 43, txt, 8, false);
   CreateLabel("T_" + tf, "TP: " + DoubleToString(target, _Digits) + " / SL: " + DoubleToString(sl, _Digits), x + 8, y + 58, txt, 8, false);
}

//+------------------------------------------------------------------+
void DrawPanel()
{
   int x = InpPanelX;
   int y = InpPanelY;
   int w = 270;
   int h = 430;

   string mtfSignal = ExtractJsonString(g_lastResponse, "signal");
   string confidence = ExtractJsonString(g_lastResponse, "confidence");
   string bias = ExtractJsonString(g_lastResponse, "bias");
   string version = ExtractJsonString(g_lastResponse, "mtf_version");

   if(mtfSignal == "")
      mtfSignal = "WAIT";

   if(confidence == "")
      confidence = "0";

   if(bias == "")
      bias = "-";

   if(version == "")
      version = "mtf";

   CreateRect("MAIN_BG", x, y, w, h, PanelBgColor(), BorderColor());
   CreateRect("HEADER", x, y, w, 48, HeaderColor(), HeaderColor());

   CreateLabel("TITLE", _Symbol + " MTF", x + 12, y + 6, clrWhite, 12, true);
   CreateLabel("TIME", TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), x + 12, y + 25, clrWhite, 8, false);

   CreateLabel("MTF_SIGNAL", "BIAS: " + mtfSignal + "  " + confidence + "%  " + bias, x + 150, y + 12, SignalColor(mtfSignal), 9, true);

   int rowY = y + 58;

   DrawFrameBox("H4", x + 8, rowY);
   rowY += 76;

   DrawFrameBox("H1", x + 8, rowY);
   rowY += 76;

   DrawFrameBox("M15", x + 8, rowY);
   rowY += 76;

   DrawFrameBox("M5", x + 8, rowY);
   rowY += 76;

   DrawFrameBox("M1", x + 8, rowY);

   CreateLabel("FOOT", version + " | Reader only", x + 12, y + h - 18, MutedTextColor(), 8, false);
}

//+------------------------------------------------------------------+
//| Lines                                                            |
//+------------------------------------------------------------------+
void DeleteTradeLines()
{
   string tags[] = {"ENTRY","SL","TP1","TP2","TP3"};

   for(int i = 0; i < ArraySize(tags); i++)
   {
      ObjectDelete(0, PREFIX + "LINE_" + tags[i]);
      ObjectDelete(0, PREFIX + "TEXT_" + tags[i]);
   }
}

string PickLineObject()
{
   string wanted = InpLineFrame;

   if(wanted == "MTF")
      return g_lastResponse;

   if(wanted == "BEST")
   {
      string frames[] = {"M1", "M5", "M15", "H1", "H4"};

      for(int i = 0; i < ArraySize(frames); i++)
      {
         string obj = ExtractIndividualTF(frames[i]);
         string sig = ExtractJsonString(obj, "signal");
         double entry = ExtractJsonDouble(obj, "entry");

         if((sig == "BUY" || sig == "SELL") && entry > 0)
            return obj;
      }

      return g_lastResponse;
   }

   string tfObj = ExtractIndividualTF(wanted);

   if(tfObj != "")
      return tfObj;

   return g_lastResponse;
}

void DrawShortLevel(string tag, double price, color clr, string label)
{
   if(price <= 0)
      return;

   datetime t1 = iTime(_Symbol, PERIOD_CURRENT, 0);
   int sec = PeriodSeconds(PERIOD_CURRENT);

   if(sec <= 0)
      sec = 60;

   datetime t2 = t1 + (sec * InpLineBars);

   string lineName = PREFIX + "LINE_" + tag;
   string textName = PREFIX + "TEXT_" + tag;

   if(ObjectFind(0, lineName) < 0)
      ObjectCreate(0, lineName, OBJ_TREND, 0, t1, price, t2, price);

   ObjectSetInteger(0, lineName, OBJPROP_TIME, 0, t1);
   ObjectSetDouble(0, lineName, OBJPROP_PRICE, 0, price);
   ObjectSetInteger(0, lineName, OBJPROP_TIME, 1, t2);
   ObjectSetDouble(0, lineName, OBJPROP_PRICE, 1, price);
   ObjectSetInteger(0, lineName, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, lineName, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, lineName, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, lineName, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, lineName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, lineName, OBJPROP_HIDDEN, true);

   if(ObjectFind(0, textName) < 0)
      ObjectCreate(0, textName, OBJ_TEXT, 0, t2, price);

   ObjectSetInteger(0, textName, OBJPROP_TIME, 0, t2);
   ObjectSetDouble(0, textName, OBJPROP_PRICE, 0, price);
   ObjectSetInteger(0, textName, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, textName, OBJPROP_FONTSIZE, 8);
   ObjectSetString(0, textName, OBJPROP_FONT, "Arial Bold");
   ObjectSetString(0, textName, OBJPROP_TEXT, " " + label + " " + DoubleToString(price, _Digits));
   ObjectSetInteger(0, textName, OBJPROP_ANCHOR, ANCHOR_LEFT);
   ObjectSetInteger(0, textName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, textName, OBJPROP_HIDDEN, true);
}

//+------------------------------------------------------------------+
void DrawTradeLines()
{
   string obj = PickLineObject();

   string signal = ExtractJsonString(obj, "signal");

   double entry = ExtractJsonDouble(obj, "entry");
   double sl    = ExtractJsonDouble(obj, "sl");
   double tp1   = ExtractJsonDouble(obj, "tp1");
   double tp2   = ExtractJsonDouble(obj, "tp2");
   double tp3   = ExtractJsonDouble(obj, "tp3");

   if(signal == "" || signal == "WAIT" || entry <= 0)
   {
      DeleteTradeLines();
      return;
   }

   DrawShortLevel("ENTRY", entry, EntryColor(), "ENTRY");
   DrawShortLevel("SL", sl, SLColor(), "SL");
   DrawShortLevel("TP1", tp1, TPColor(), "TP1");
   DrawShortLevel("TP2", tp2, TPColor(), "TP2");
   DrawShortLevel("TP3", tp3, TPColor(), "TP3");
}
//+------------------------------------------------------------------+