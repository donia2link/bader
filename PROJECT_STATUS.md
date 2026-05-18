# QuantBado Market Reader - Project Status

## Current Status

Project stage: Working prototype  
Estimated completion toward final production version: 65%

The system is currently operational as an MT5 Expert Advisor connected to a FastAPI server through the domain:

http://quantbado.online

The project is no longer just an indicator. It is now a server-based Market Decision System with lifecycle-based signal handling and MT5 visual output.

---

## Current Working Versions

### API

File:

C:\QuantProject\api\main.py

Current version:

v1.7.0

Status:

Working

Main features:

- FastAPI server
- Health endpoint
- Analyze endpoint
- Admin endpoints
- Admin key loaded from config/settings.json
- User key validation
- Symbol normalization
- Event logging
- Historical storage
- Test signal creation
- Active signal management

---

### Core Engine

File:

C:\QuantProject\engine\market_reader.py

Current version:

v1.4

Status:

Working

Main features:

- Receives candles from MT5
- Runs all analysis engines
- Uses fusion engine for final decision
- Creates signal lifecycle object
- Uses persistent signal store
- Keeps active signals stable until TP Hit, SL Hit, or Expired

---

## Working Engine Files

Located in:

C:\QuantProject\engine

Files completed:

- symbol_engine.py
- time_sync.py
- event_bus.py
- historical_storage.py
- market_structure_engine.py
- momentum_engine.py
- liquidity_engine.py
- support_resistance_engine.py
- volatility_engine.py
- session_engine.py
- regime_detector.py
- market_danger_engine.py
- fusion_engine.py
- signal_lifecycle.py
- signal_store.py
- market_reader.py

---

## Completed Analysis Engines

### Market Structure Engine

Detects:

- bullish_structure
- bearish_structure
- mixed_structure
- HH / HL / LH / LL logic
- BOS
- CHoCH
- structure_score
- structure_reason

Status: Working

---

### Momentum Engine

Detects:

- momentum strength
- momentum direction
- candle pressure
- impulse candle
- acceleration
- momentum_score
- momentum_reason

Status: Working

---

### Liquidity Engine

Detects:

- buy-side liquidity
- sell-side liquidity
- liquidity sweeps
- stop hunts
- fake breakout
- liquidity_score
- liquidity_reason

Status: Working

---

### Support and Resistance Engine

Detects:

- support
- resistance
- support_strength
- resistance_strength
- nearest_zone
- zone_risk
- sr_score
- sr_reason

Status: Working

---

### Volatility Engine

Detects:

- ATR
- ATR ratio
- volatility level
- expansion
- compression
- dead market
- volatility_score
- volatility_reason

Status: Working

---

### Session Engine

Detects:

- Asia session
- London session
- New York session
- London/New York overlap
- Dead hours
- session_score
- session_reason

Status: Working

---

### Regime Detector

Detects:

- bullish_trend
- bearish_trend
- range
- bullish_breakout
- bearish_breakout
- bullish_pullback
- bearish_pullback
- accumulation
- distribution
- regime_score
- regime_reason

Status: Working

---

### Market Danger Engine

Detects:

- whipsaw
- fake market
- manipulation risk
- long wick instability
- danger_level
- danger_score
- danger_reason

Status: Working

---

### Decision Fusion Engine

Combines:

- trend score
- momentum score
- structure score
- liquidity score
- support/resistance score
- volatility score
- session score
- regime score
- danger penalty
- risk penalty

Outputs:

- final_signal
- final_confidence
- final_risk
- fusion_score
- fusion_reason
- decision_blocks

Status: Working

---

## Signal System

### Signal Lifecycle

File:

C:\QuantProject\engine\signal_lifecycle.py

Supports statuses:

- No Signal
- Detected
- Waiting Confirmation
- Active
- In Profit
- TP Hit
- SL Hit
- Expired

Status: Working

---

### Persistent Signal Store

File:

C:\QuantProject\engine\signal_store.py

Stores active signals in:

C:\QuantProject\logs\active_signals.json

Signal key format:

user_key|symbol|timeframe

Behavior:

- If an active signal exists, the server tracks it instead of creating a new one.
- The same signal remains active until TP Hit, SL Hit, or Expired.
- If there is no active signal, a new signal is created only when final signal is BUY or SELL.

Status: Working

---

## MT5 Expert Advisor

Current EA version:

QuantBado_MarketReader_LIFECYCLE_LINES_MULTICHART_FIXED.mq5

Status:

Working and compiled without errors

Features:

- WebRequest to server
- Multi-chart safe object names
- Works on multiple symbols/timeframes
- Displays professional panel
- Reads signal_lifecycle object
- Displays Signal Status
- Displays Signal ID
- Displays Entry, SL, TP1, TP2, TP3
- Displays Lifecycle Reason
- Draws Entry line
- Draws SL line
- Draws TP1 line
- Draws TP2 line
- Draws TP3 line
- Draws signal label

Important:

If the server returns WAIT / No Signal, no lines are drawn. Lines appear only when there is a BUY or SELL signal.

---

## Admin API

Admin endpoints are available through Swagger:

http://quantbado.online/docs

Current protected endpoints:

- POST /admin/active-signals
- POST /admin/clear-signals
- POST /admin/clear-final-signals
- POST /admin/test-signal

Admin key is loaded from:

C:\QuantProject\config\settings.json

Example settings file:

{
  "admin_key": "qb-admin-2026"
}

Status:

Working

Tested:

- Wrong admin key returns INVALID_ADMIN_KEY.
- Correct admin key works.
- Test signal can be created from Swagger.
- MT5 reads test signal and draws lines.

---

## Files That Must Not Be Uploaded to Public GitHub

Do not upload:

- C:\QuantProject\config\settings.json
- C:\QuantProject\users\users.json
- C:\QuantProject\logs\
- C:\QuantProject\engine\__pycache__\
- C:\QuantProject\api\__pycache__\
- *.pyc
- active_signals.json
- market_logs.jsonl
- historical_storage.jsonl
- events.jsonl

Reason:

These files may contain admin keys, user keys, user data, signal logs, or runtime state.

---

## GitHub Repository

Available GitHub repository:

donia2link/bader

Visibility:

Public

Important:

Because the repository is public, only safe source files should be uploaded.

Safe files to upload:

- api/main.py
- engine/*.py except runtime/cache files
- ea/*.mq5
- PROJECT_STATUS.md
- .gitignore
- requirements.txt
- README.md

Unsafe files to avoid:

- config/settings.json
- users/users.json
- logs/*
- __pycache__/*
- *.pyc

---

## What Has Been Tested

Tested successfully:

- FastAPI health endpoint
- MT5 WebRequest
- User key validation
- Symbol normalization
- Market analysis endpoint
- Historical storage
- Event bus
- Market structure engine
- Momentum engine
- Liquidity engine
- Support/resistance engine
- Volatility engine
- Session engine
- Regime detector
- Market danger engine
- Fusion engine
- Signal lifecycle object
- Persistent signal store
- Admin test signal
- Admin clear signals
- MT5 panel display
- MT5 multi-chart safety
- MT5 Entry/SL/TP line drawing
- Admin key protection
- Admin key moved outside code into settings.json

---

## Current Limitations

The system is working, but not final for real trading yet.

Main limitations:

- BUY/SELL logic may be too strict.
- WAIT may appear too often.
- Fusion thresholds need tuning.
- No full performance tracking yet.
- No backtest/replay system yet.
- No web dashboard yet.
- No Telegram alerts yet.
- No mobile dashboard yet.
- No production database yet.
- Admin key is file-based, not full authentication.
- Performance metrics are not calculated yet.
- Strategy has not been tested long enough on demo.

---

## Remaining Work

### Phase 1 - Project Backup and GitHub

- Create .gitignore
- Create requirements.txt
- Create README.md
- Push safe files to GitHub
- Keep secrets and logs out of GitHub

Status: Next step

---

### Phase 2 - Signal Quality Tuning

Goal:

Improve real signal quality and reduce unnecessary WAIT.

Planned changes:

- Add signal grade:
  - Strong BUY
  - Weak BUY
  - WAIT
  - Weak SELL
  - Strong SELL

- Add mode:
  - scalp
  - intraday
  - safe
  - aggressive

- Tune thresholds per timeframe:
  - M1
  - M5
  - M15
  - H1
  - H4

Status: Not started

---

### Phase 3 - Performance Engine

Planned metrics:

- Total signals
- Win rate
- Loss rate
- Profit factor
- Expectancy
- Average RR
- Max drawdown
- Best symbol
- Best timeframe
- TP1 hit count
- TP2 hit count
- TP3 hit count
- SL hit count

Status: Not started

---

### Phase 4 - Market Replay / Backtest

Goal:

Replay historical candle data through the same engines to test performance before live usage.

Status: Not started

---

### Phase 5 - Web Dashboard

Planned dashboards:

Simple Dashboard:

- BUY / SELL / WAIT
- Confidence
- Risk
- Entry
- SL
- TP
- Reason

Professional Dashboard:

- All engine results
- Scores
- Decision blocks
- Active signals
- Performance logs

Status: Not started

---

### Phase 6 - Telegram and Mobile Alerts

Planned alerts:

- New signal
- Signal active
- TP hit
- SL hit
- Expired
- High danger warning
- Server error

Status: Not started

---

## Next Immediate Step

Create .gitignore in:

C:\QuantProject\.gitignore

Then prepare safe GitHub upload.

After GitHub backup is complete, start Signal Quality Tuning.

Recommended next coding task:

fusion_engine.py v0.2

Add:

- signal_grade
- trade_mode
- weaker/stronger decision levels
- more practical thresholds