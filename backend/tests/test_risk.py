from app.domain import TradeIntent,AccountState,ExecutionMode
from app.services.risk import risk_engine

def test_rejects_oversized_trade():
    i=TradeIntent(intent_id='x',symbol='NVDA',side='BUY',qty=100,reference_price=190,strategy='Momentum',execution_mode=ExecutionMode.AUTOMATIC)
    d=risk_engine.evaluate(i,AccountState())
    assert d.status.value=='REJECTED'

def test_daily_loss_guard():
    i=TradeIntent(intent_id='x',symbol='AAPL',side='BUY',qty=1,reference_price=200,strategy='Momentum',execution_mode=ExecutionMode.AUTOMATIC)
    d=risk_engine.evaluate(i,AccountState(daily_pnl=-600))
    assert d.status.value=='REJECTED'
