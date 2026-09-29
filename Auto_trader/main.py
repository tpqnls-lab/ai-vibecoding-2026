from decimal import Decimal
from typing import Literal

import asyncio
import json
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import Order, OrderRequest, Portfolio, Price
from .paper import PaperBroker

app = FastAPI(title="Toss Auto Trader", version="0.1.0")
broker = PaperBroker(initial_cash=Decimal(os.getenv("PAPER_INITIAL_CASH", "10000000")), state_file=Path(__file__).parent / "paper_state.json")
prices: dict[str, Price] = {}
mode: Literal["PAPER", "DRY_RUN"] = "PAPER"
AUTO_STRATEGY = {"min_score": 85, "take_profit": 0.15, "stop_loss": -0.05, "interval_seconds": 180}
AUTO_STRATEGY["stop_loss"] = Decimal("-0.04")
AUTO_STRATEGY["stop_loss_max"] = Decimal("-0.07")
AUTO_STRATEGY["take_profit"] = Decimal("0.08")
AUTO_STRATEGY["take_profit_max"] = Decimal("0.30")
AUTO_STRATEGY["max_positions"] = 5
FRONTEND = Path(__file__).parent / "static" / "index.html"
app.mount("/static", StaticFiles(directory=FRONTEND.parent), name="static")
TOSS_API = "https://openapi.tossinvest.com"
_access_token: str | None = None
_token_expires_at = 0.0
_market_task: asyncio.Task[None] | None = None
_auto_peaks: dict[str, Decimal] = {}
_auto_cooldowns: dict[str, float] = {}
_change_synced_at = 0.0
market_symbols = os.getenv("TOSS_SYMBOLS", "005930,000660,454910,028050,012330,000810,096770").replace(" ", "")


def load_dotenv() -> None:
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))


load_dotenv()


async def toss_token() -> str:
    global _access_token, _token_expires_at
    now = asyncio.get_running_loop().time()
    if _access_token and now < _token_expires_at:
        return _access_token
    client_id, client_secret = os.getenv("TOSS_CLIENT_ID"), os.getenv("TOSS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("TOSS_CLIENT_ID와 TOSS_CLIENT_SECRET가 필요합니다.")
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.post(f"{TOSS_API}/oauth2/token", data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret})
        response.raise_for_status()
        body = response.json()
    _access_token = body["access_token"]
    _token_expires_at = now + int(body.get("expires_in", 3600)) - 60
    return _access_token


async def sync_real_prices() -> None:
    global _change_synced_at
    while True:
        try:
            held_symbols = ",".join(broker.portfolio().positions.keys())
            symbols = ",".join(dict.fromkeys(filter(None, (market_symbols + "," + held_symbols).split(","))))
            token = await toss_token()
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.get(f"{TOSS_API}/api/v1/prices", params={"symbols": symbols}, headers={"Authorization": f"Bearer {token}"})
                response.raise_for_status()
                result = response.json().get("result", [])
            for item in result:
                value = Price(symbol=item["symbol"].upper(), price=Decimal(item["lastPrice"]), currency=item.get("currency", "KRW"), change_percent=Decimal(str(item.get("changePercent", item.get("changeRate", 0)))))
                prices[value.symbol] = value
            if asyncio.get_running_loop().time() - _change_synced_at >= 300:
                _change_synced_at = asyncio.get_running_loop().time()
                for symbol, value in list(prices.items()):
                    try:
                        async with httpx.AsyncClient(timeout=10, trust_env=False) as candle_client:
                            candle_response = await candle_client.get(f"{TOSS_API}/api/v1/candles", params={"symbol": symbol, "interval": "1d", "count": 2}, headers={"Authorization": f"Bearer {token}"})
                        candles = candle_response.json().get("result", {}).get("candles", [])
                        if candles:
                            previous_close = Decimal(candles[1 if len(candles) > 1 else 0]["closePrice"])
                            value.change_percent = (value.price - previous_close) / previous_close * 100
                    except (httpx.HTTPError, KeyError, ValueError, TypeError):
                        continue
        except (httpx.HTTPError, KeyError, RuntimeError, ValueError):
            pass  # Keep the last good quote visible during temporary API failures.
        await asyncio.sleep(float(os.getenv("TOSS_PRICE_INTERVAL", "2")))


@app.post("/api/v1/market/refresh", response_model=list[Price])
async def refresh_prices(symbols: str) -> list[Price]:
    """Fetch selected symbols immediately using the server-side Toss token."""
    global market_symbols
    cleaned = ",".join(item.strip().upper() for item in symbols.split(",") if item.strip())
    if not cleaned:
        raise HTTPException(400, "조회할 종목코드를 입력하세요.")
    market_symbols = cleaned
    token = await toss_token()
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.get(f"{TOSS_API}/api/v1/prices", params={"symbols": cleaned}, headers={"Authorization": f"Bearer {token}"})
        if response.is_error:
            raise HTTPException(response.status_code, "토스증권 시세 조회에 실패했습니다.")
        result = response.json().get("result", [])
    for item in result:
        value = Price(symbol=item["symbol"].upper(), price=Decimal(item["lastPrice"]), currency=item.get("currency", "KRW"))
        prices[value.symbol] = value
    return list(prices.values())


@app.on_event("startup")
async def start_market_sync() -> None:
    global _market_task, mode
    mode = os.getenv("TRADING_MODE", "PAPER")  # type: ignore[assignment]
    if os.getenv("TOSS_CLIENT_ID") and os.getenv("TOSS_CLIENT_SECRET"):
        _market_task = asyncio.create_task(sync_real_prices())


@app.on_event("shutdown")
async def stop_market_sync() -> None:
    if _market_task:
        _market_task.cancel()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": mode}


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(FRONTEND)


@app.get("/api/v1/market/prices", response_model=list[Price])
def get_prices() -> list[Price]:
    return list(prices.values())

@app.get("/api/v1/recommendations")
async def recommendations(exclude: str = "") -> list[dict]:
    """Return a dynamic TOP 5 based on Toss ranking data."""
    try:
        token = await toss_token()
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            result = []
            for params in ({"marketCountry": "KR", "type": "TOP_GAINERS", "duration": "1d"}, {"marketCountry": "KR", "type": "MARKET_TRADING_AMOUNT", "duration": "1d"}, {"marketCountry": "KR", "type": "MARKET_TRADING_VOLUME", "duration": "1d"}):
                response = await client.get(f"{TOSS_API}/api/v1/rankings", params=params, headers={"Authorization": f"Bearer {token}"})
                if response.is_success:
                    result = response.json().get("result", [])
                    if result: break
        rows = result.get("items", result.get("rankings", result.get("data", []))) if isinstance(result, dict) else result
        excluded = {x.strip() for x in exclude.split(",") if x.strip()}
        ranked = []
        for item in rows:
            symbol = str(item.get("symbol", item.get("code", "")))
            quote = item.get("price", {}) if isinstance(item.get("price", {}), dict) else {}
            price = item.get("lastPrice", item.get("currentPrice", quote.get("lastPrice")))
            base_price = quote.get("basePrice", item.get("basePrice"))
            if not symbol or symbol in excluded or price is None: continue
            change = float(item.get("changePercent", item.get("changeRate", quote.get("changeRate", item.get("change", 0)))) or 0)
            if base_price:
                change = (float(price) - float(base_price)) / float(base_price) * 100
            value = float(item.get("tradingValue", item.get("tradingAmount", 0)) or 0)
            volume = float(item.get("volume", item.get("tradingVolume", 0)) or 0)
            # Avoid chasing abnormal one-day spikes.
            if change > 20 or change < -10: continue
            ranked.append({"symbol": symbol, "name": item.get("name", item.get("stockName", symbol)), "price": float(price), "change": change, "previous_price": float(base_price) if base_price else None, "score": round(change * 5 + (value > 0) * 2 + (volume > 0), 2)})
        ranked = sorted(ranked, key=lambda x: x["score"], reverse=True)[:5]
        if ranked:
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                name_response = await client.get(f"{TOSS_API}/api/v1/stocks", params={"symbols": ",".join(x["symbol"] for x in ranked)}, headers={"Authorization": f"Bearer {token}"})
                if name_response.is_success:
                    name_rows = name_response.json().get("result", [])
                    names = {str(x.get("symbol")): x.get("name", x.get("stockName")) for x in name_rows}
                    for item in ranked:
                        match = next((x for x in name_rows if str(x.get("symbol")) == item["symbol"]), {})
                        item["name"] = names.get(item["symbol"], item["name"])
                        item["sector"] = match.get("sector", match.get("industry", f"{match.get('market', '국내')} {match.get('securityType', '종목')}"))
        return ranked
    except (httpx.HTTPError, KeyError, ValueError, RuntimeError, TypeError):
        return []

@app.get("/api/v1/stock-names")
async def stock_names(symbols: str) -> dict[str, str]:
    token = await toss_token()
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.get(f"{TOSS_API}/api/v1/stocks", params={"symbols": symbols}, headers={"Authorization": f"Bearer {token}"})
    if not response.is_success: return {}
    rows = response.json().get("result", [])
    return {str(x.get("symbol")): x.get("name", x.get("stockName", str(x.get("symbol")))) for x in rows}


@app.get("/api/v1/market/candles")
async def get_candles(symbol: str, interval: str = "1d") -> dict:
    """Proxy Toss candle data without exposing the OAuth token to the browser."""
    if interval not in {"1m", "1d"}:
        raise HTTPException(400, "Toss API는 1m 또는 1d 봉을 지원합니다.")
    token = await toss_token()
    candles: list[dict] = []
    before: str | None = None
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        for _ in range(5):
            params = {"symbol": symbol.upper(), "interval": interval, "count": 200}
            if before:
                params["before"] = before
            response = await client.get(f"{TOSS_API}/api/v1/candles", params=params, headers={"Authorization": f"Bearer {token}"})
            if response.is_error:
                raise HTTPException(response.status_code, "실제 봉 데이터를 가져오지 못했습니다.")
            result = response.json().get("result", {})
            page = result.get("candles", [])
            candles.extend(page)
            before = result.get("nextBefore")
            if not before or not page:
                break
    return {"result": {"candles": candles, "nextBefore": before}}


@app.put("/api/v1/market/prices/{symbol}", response_model=Price)
def set_price(symbol: str, price: Decimal, currency: str = "KRW") -> Price:
    value = Price(symbol=symbol.upper(), price=price, currency=currency)
    prices[value.symbol] = value
    return value


@app.websocket("/ws/market")
async def market_stream(websocket: WebSocket) -> None:
    """Stream the current paper-market snapshot to the dashboard."""
    await websocket.accept()
    try:
        while True:
            payload = {
                "prices": [price.model_dump(mode="json") for price in prices.values()],
                "portfolio": get_portfolio().model_dump(mode="json"),
                "mode": mode,
            }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return


@app.get("/api/v1/portfolio", response_model=Portfolio)
def get_portfolio() -> Portfolio:
    portfolio = broker.portfolio()
    for holding in portfolio.holdings:
        quote = prices.get(holding["symbol"])
        current = quote.price if quote else holding["average_price"]
        quantity, cost = holding["quantity"], holding["average_price"]
        pnl = (current - cost) * quantity
        holding.update(current_price=current, invested_value=cost * quantity, market_value=current * quantity, pnl=pnl,
                       pnl_percent=(pnl / (cost * quantity) * 100) if cost else Decimal("0"))
    portfolio.total_invested = sum((h["average_price"] * h["quantity"] for h in portfolio.holdings), Decimal("0"))
    portfolio.total_market_value = sum((h["current_price"] * h["quantity"] for h in portfolio.holdings), Decimal("0"))
    portfolio.total_pnl = portfolio.total_market_value - portfolio.total_invested
    portfolio.total_pnl_percent = (portfolio.total_pnl / portfolio.total_invested * 100) if portfolio.total_invested else Decimal("0")
    portfolio.total_assets = portfolio.cash + portfolio.total_market_value
    return portfolio


@app.get("/api/v1/orders", response_model=list[Order])
def get_orders() -> list[Order]:
    return broker.orders()


@app.post("/api/v1/orders", response_model=Order)
def create_order(request: OrderRequest) -> Order:
    if mode == "PAPER" and request.symbol not in prices:
        # The recommendation screen may have a quote before the background
        # market sync has completed. In paper mode it is safe to register the
        # submitted quote as the paper execution price.
        prices[request.symbol] = Price(symbol=request.symbol, price=request.price, currency="KRW")
    return broker.place(request, mode)


@app.post("/api/v1/mode/{new_mode}")
def set_mode(new_mode: Literal["PAPER", "DRY_RUN"]) -> dict[str, str]:
    global mode
    mode = new_mode
    return {"mode": mode}


@app.get("/api/v1/auto-trading/config")
def auto_trading_config() -> dict:
    return {"mode": mode, **AUTO_STRATEGY}


@app.post("/api/v1/auto-trading/evaluate")
async def evaluate_auto_trade(symbol: str, price: Decimal, score: int, budget_percent: Decimal = Decimal("40")) -> dict:
    """Evaluate one paper-trading decision using the configured strategy."""
    if mode != "PAPER":
        raise HTTPException(400, "자동매매는 현재 PAPER 모드에서만 실행됩니다.")
    if _auto_cooldowns.get(symbol.upper(), 0) > time.time():
        return {"action": "HOLD", "reason": "손절 후 재매수 대기 중입니다.", "quantity": 0}
    portfolio = broker.portfolio()
    if symbol.upper() in portfolio.positions:
        return {"action": "HOLD", "reason": "이미 보유 중인 종목입니다.", "quantity": 0}
    if len(portfolio.positions) >= AUTO_STRATEGY["max_positions"]:
        return {"action": "HOLD", "reason": "최대 보유 종목 수에 도달했습니다.", "quantity": 0}
    try:
        token = await toss_token()
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.get(f"{TOSS_API}/api/v1/candles", params={"symbol": symbol.upper(), "interval": "1m", "count": 20}, headers={"Authorization": f"Bearer {token}"})
        candles = response.json().get("result", {}).get("candles", []) if response.is_success else []
        if len(candles) < 5:
            return {"action": "HOLD", "reason": "차트 데이터가 부족해 매수하지 않았습니다.", "quantity": 0}
        closes = [Decimal(x["closePrice"]) for x in reversed(candles)]
        volumes = [Decimal(x.get("volume", "0")) for x in reversed(candles)]
        short_avg = sum(closes[-5:]) / Decimal("5")
        avg_volume = sum(volumes[:-5]) / Decimal(str(max(1, len(volumes) - 5)))
        if closes[-1] < short_avg or volumes[-1] < avg_volume:
            return {"action": "HOLD", "reason": "상승 추세 또는 체결량 조건을 충족하지 못했습니다.", "quantity": 0}
    except (httpx.HTTPError, KeyError, ValueError, TypeError, RuntimeError):
        return {"action": "HOLD", "reason": "실시간 차트·체결량을 확인하지 못해 매수하지 않았습니다.", "quantity": 0}
    prices[symbol.upper()] = Price(symbol=symbol.upper(), price=price, currency="KRW")
    if score < AUTO_STRATEGY["min_score"]:
        return {"action": "HOLD", "reason": "추천 점수가 기준 미만입니다.", "quantity": 0}
    cash = broker.portfolio().cash
    budget = cash * max(Decimal("0"), min(Decimal("100"), budget_percent)) / Decimal("100")
    quantity = int(budget // price)
    if quantity < 1:
        return {"action": "HOLD", "reason": "설정한 예산으로 1주를 매수할 수 없습니다.", "quantity": 0}
    order = broker.place(OrderRequest(symbol=symbol, side="BUY", quantity=Decimal(quantity), price=price), mode)
    return {"action": "BUY", "quantity": quantity, "order": order.model_dump(mode="json"), **AUTO_STRATEGY}

@app.post("/api/v1/auto-trading/manage")
def manage_auto_positions() -> dict:
    """Sell all positions that hit the configured stop-loss or take-profit."""
    sold = []
    for holding in broker.portfolio().holdings:
        quote = prices.get(holding["symbol"])
        if not quote: continue
        change = (quote.price - holding["average_price"]) / holding["average_price"]
        peak = max(_auto_peaks.get(holding["symbol"], holding["average_price"]), quote.price)
        _auto_peaks[holding["symbol"]] = peak
        peak_change = (peak - holding["average_price"]) / holding["average_price"]
        volatile_stop = change <= AUTO_STRATEGY["stop_loss_max"]
        trailing_exit = peak_change >= Decimal("0.08") and quote.price <= peak * Decimal("0.95")
        max_profit_exit = change >= AUTO_STRATEGY["take_profit_max"]
        if change <= AUTO_STRATEGY["stop_loss"] or volatile_stop or trailing_exit or max_profit_exit:
            order = broker.place(OrderRequest(symbol=holding["symbol"], side="SELL", quantity=holding["quantity"], price=quote.price), mode)
            sold.append(order.model_dump(mode="json"))
            _auto_peaks.pop(holding["symbol"], None)
            if change <= AUTO_STRATEGY["stop_loss"]:
                _auto_cooldowns[holding["symbol"]] = time.time() + 900
    return {"sold": sold, "stop_loss": AUTO_STRATEGY["stop_loss"], "take_profit": AUTO_STRATEGY["take_profit"]}
