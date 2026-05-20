//+------------------------------------------------------------------+
//| QuantBado Market Reader MTF                                      |
//| Multi-Timeframe EA: M1 + M5 + M15 + H1                           |
//| Sends candles to FastAPI /analyze-mtf                            |
//| Reader only - no trading orders                                  |
//+------------------------------------------------------------------+
#property strict
#property version   "2.7"
#property description "QuantBado MTF Reader - strategy quality panel + short entry/exit levels - reader only"

input string InpServerUrl = "http://quantbado.online/analyze-mtf";
input string InpUserKey   = "test123";
input int    InpCandles   = 50;
input int    InpTimerSec  = 20;

input bool   InpShowPanel = true;
input bool   InpDrawLines = true;

input int    InpPanelX    = 230;
input int    InpPanelY    = 28;
input int    InpLineBars  = 8;

string g_lastResponse = "";
datetime g_lastRequestTime = 0;

string PREFIX = "QB_MTF_";

//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(InpTimerSec);

   Print("QuantBado MTF EA v2.7 started.");
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
//| JSON helpers                                                     |
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

//+------------------------------------------------------------------+
//| Strategy quality helpers                                         |
//+------------------------------------------------------------------+
string QualityLabel(double confidence, string signal)
{
   if(signal == "WAIT")
      return "NO TRADE";

   if(confidence >= 85)
      return "A+ HIGH";

   if(confidence >= 70)
      return "B GOOD";

   if(confidence >= 55)
      return "C WEAK";

   return "LOW";
}

color QualityColor(double confidence, string signal)
{
   if(signal == "WAIT")
      return C'245,158,11';

   if(confidence >= 85)
      return C'0,200,83';

   if(confidence >= 70)
      return C'37,99,235';

   if(confidence >= 55)
      return C'245,158,11';

   return C'230,57,70';
}

string LevelStatusText(string signal, double entry, double sl, double tp1, double tp2, double tp3)
{
   if(signal == "WAIT" || entry <= 0)
      return "Waiting for aligned MTF setup";

   if(signal == "BUY")
   {
      if(!(sl < entry && entry < tp1 && tp1 < tp2 && tp2 < tp3))
         return "Invalid BUY levels";
      return "BUY levels OK";
   }

   if(signal == "SELL")
   {
      if(!(tp3 < tp2 && tp2 < tp1 && tp1 < entry && entry < sl))
         return "Invalid SELL levels";
      return "SELL levels OK";
   }

   return "No valid signal";
}

//+------------------------------------------------------------------+
//| Theme helpers                                                    |
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
      return C'18,22,28';

   return C'250,250,250';
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
      return C'170,178,190';

   return C'75,85,99';
}

color BorderColor()
{
   if(IsDarkChart())
      return C'30,144,255';

   return C'37,99,235';
}

color SignalColor(string signal)
{
   if(signal == "BUY")
      return C'0,190,90';

   if(signal == "SELL")
      return C'225,55,70';

   return C'245,158,11';
}

color EntryColor()
{
   return C'0,145,255';
}

color SLColor()
{
   return C'225,55,70';
}

color TPColor()
{
   return C'0,165,85';
}

//+------------------------------------------------------------------+
//| Object helpers                                                   |
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
//| Draw panel                                                       |
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
   string maxTp      = ExtractJsonString(g_lastResponse, "max_tp_hit");
   string reason     = ExtractJsonString(g_lastResponse, "reason");
   string mtfVersion = ExtractJsonString(g_lastResponse, "mtf_version");

   if(signal == "")
      signal = "WAIT";

   double conf = StringToDouble(confidence);

   if(confidence == "")
      confidence = "0";

   if(bias == "")
      bias = "-";

   if(entryTf == "")
      entryTf = "-";

   if(maxTp == "")
      maxTp = "none";

   if(mtfVersion == "")
      mtfVersion = "mtf";

   if(reason == "")
      reason = "Waiting for MTF response";

   if(StringLen(reason) > 42)
      reason = StringSubstr(reason, 0, 42) + "...";

   double dEntry = StringToDouble(entry);
   double dSL = StringToDouble(sl);
   double dTP1 = StringToDouble(tp1);
   double dTP2 = StringToDouble(tp2);
   double dTP3 = StringToDouble(tp3);

   string quality = QualityLabel(conf, signal);
   string levelStatus = LevelStatusText(signal, dEntry, dSL, dTP1, dTP2, dTP3);

   int x = InpPanelX;
   int y = InpPanelY;
   int w = 320;
   int h = 245;

   color bg = PanelBgColor();
   color txt = PanelTextColor();
   color muted = MutedTextColor();
   color border = BorderColor();
   color sigClr = SignalColor(signal);
   color qClr = QualityColor(conf, signal);

   CreateRect("PANEL_BG", x, y, w, h, bg, border);
   CreateRect("HEADER_BG", x, y, w, 40, border, border);

   CreateLabel("TITLE", "QuantBado MTF Strategy", x + 12, y + 9, clrWhite, 10, true);
   CreateLabel("SUB", _Symbol + " | M1 M5 M15 H1", x + 172, y + 11, clrWhite, 8, false);

   CreateLabel("SIG_L", "SIGNAL", x + 12, y + 55, muted, 8, false);
   CreateLabel("SIG_V", signal, x + 78, y + 48, sigClr, 18, true);

   CreateLabel("Q_L", "QUALITY", x + 178, y + 55, muted, 8, false);
   CreateLabel("Q_V", quality, x + 240, y + 52, qClr, 10, true);

   CreateLabel("CONF", "Conf: " + confidence + "   Bias: " + bias + "   Entry TF: " + entryTf, x + 12, y + 82, txt, 9, false);
   CreateLabel("MAXTP", "Max TP: " + maxTp + "   Status: " + levelStatus, x + 12, y + 103, muted, 8, false);

   CreateLabel("ENTRY", "ENTRY   " + entry, x + 12, y + 130, EntryColor(), 9, true);
   CreateLabel("SL",    "SL      " + sl,    x + 12, y + 151, SLColor(), 9, true);

   CreateLabel("TP1",   "TP1     " + tp1,   x + 168, y + 130, TPColor(), 9, true);
   CreateLabel("TP2",   "TP2     " + tp2,   x + 168, y + 151, TPColor(), 9, true);
   CreateLabel("TP3",   "TP3     " + tp3,   x + 168, y + 172, TPColor(), 9, true);

   CreateLabel("REASON_L", "Reason", x + 12, y + 202, muted, 8, false);
   CreateLabel("REASON", reason, x + 62, y + 202, txt, 8, false);

   CreateLabel("VERSION", mtfVersion, x + 12, y + 224, muted, 8, false);
   CreateLabel("TIME", "Last: " + TimeToString(g_lastRequestTime, TIME_SECONDS), x + 210, y + 224, muted, 8, false);
}

//+------------------------------------------------------------------+
//| Trade line helpers                                               |
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
   string signal = ExtractJsonString(g_lastResponse, "signal");

   double entry = ExtractJsonDouble(g_lastResponse, "entry");
   double sl    = ExtractJsonDouble(g_lastResponse, "sl");
   double tp1   = ExtractJsonDouble(g_lastResponse, "tp1");
   double tp2   = ExtractJsonDouble(g_lastResponse, "tp2");
   double tp3   = ExtractJsonDouble(g_lastResponse, "tp3");

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