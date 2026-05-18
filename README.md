# QuantBado Market Reader

Server-based MT5 Market Decision System.

## Current status

Working prototype.

## Main components

- FastAPI server
- MT5 Expert Advisor
- Market structure engine
- Momentum engine
- Liquidity engine
- Support/resistance engine
- Volatility engine
- Session engine
- Regime detector
- Market danger engine
- Decision fusion engine
- Signal lifecycle
- Persistent signal store
- Admin API

## Current versions

- API: v1.7.0
- Market Reader: v1.4
- MT5 EA: Lifecycle Lines MultiChart version

## Important

Do not commit secrets, user files, logs, or runtime signal files.

Protected by .gitignore:

- config/settings.json
- users/users.json
- logs/
- __pycache__/
- *.pyc
- *.ex5

## Next step

Signal Quality Tuning.