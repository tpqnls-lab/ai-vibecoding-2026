from decimal import Decimal
from typing import Literal

import asyncio
import json
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import Order, OrderRequest, Portfolio, Price
from .paper import PaperBroker

app = FastAPI(title="Toss Auto Trader", version="0.1.0")
broker = PaperBroker()
prices: dict[str, Price] = {}
mode: Literal["PAPER", "DRY_RUN"] = "PAPER"
AUTO_STRATEGY = {"min_score": 85, "take_profit": 0.15, "stop_loss": -0.05, "interval_seconds": 180}
FRONTEND = Path(__file__).parent / "static" / "index.html"
app.mount("/static", StaticFiles(directory=FRONTEND.parent), name="static")
TOSS_API = "https://openapi.tossinvest.com"
_access_token: str | None = None
_token_expires_at = 0.0
_market_task: asyncio.Task[None] | None = None
market_symbols = os.getenv("TOSS_SYMBOLS", "005930,000660").replace(" ", "")


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
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(f"{TOSS_API}/oauth2/token", data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret})
        response.raise_for_status()
        body = response.json()
    _access_token = body["access_token"]
    _token_expires_at = now + int(body.get("expires_in", 3600)) - 60
    return _access_token


async def sync_real_prices() -> None:
    while True:
        try:
            symbols = market_symbols
            token = await toss_token()
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{TOSS_API}/api/v1/prices", params={"symbols": symbols}, headers={"Authorization": f"Bearer {token}"})
                response.raise_for_status()
                result = response.json().get("result", [])
            for item in result:
                value = Price(symbol=item["symbol"].upper(), price=Decimal(item["lastPrice"]), currency=item.get("currency", "KRW"))
                prices[value.symbol] = value
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
    async with httpx.AsyncClient(timeout=10) as client:
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


@app.get("/api/v1/market/candles")
async def get_candles(symbol: str, interval: str = "1d") -> dict:
    """Proxy Toss candle data without exposing the OAuth token to the browser."""
    if interval not in {"1m", "1d"}:
        raise HTTPException(400, "Toss API는 1m 또는 1d 봉을 지원합니다.")
    token = await toss_token()
    candles: list[dict] = []
    before: str | None = None
    async with httpx.AsyncClient(timeout=10) as client:
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
    return broker.portfolio()


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
def evaluate_auto_trade(symbol: str, price: Decimal, score: int, budget_percent: Decimal = Decimal("40")) -> dict:
    """Evaluate one paper-trading decision using the configured strategy."""
    if mode != "PAPER":
        raise HTTPException(400, "자동매매는 현재 PAPER 모드에서만 실행됩니다.")
    if score < AUTO_STRATEGY["min_score"]:
        return {"action": "HOLD", "reason": "추천 점수가 기준 미만입니다.", "quantity": 0}
    cash = broker.portfolio().cash
    budget = cash * max(Decimal("0"), min(Decimal("100"), budget_percent)) / Decimal("100")
    quantity = int(budget // price)
    if quantity < 1:
        return {"action": "HOLD", "reason": "설정한 예산으로 1주를 매수할 수 없습니다.", "quantity": 0}
    order = broker.place(OrderRequest(symbol=symbol, side="BUY", quantity=Decimal(quantity), price=price), mode)
    return {"action": "BUY", "quantity": quantity, "order": order.model_dump(mode="json"), **AUTO_STRATEGY}
