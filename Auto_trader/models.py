from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Price(BaseModel):
    symbol: str
    price: Decimal = Field(gt=0)
    currency: str = "KRW"
    change_percent: Decimal = Decimal("0")


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)


class Order(BaseModel):
    id: int
    client_order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    price: Decimal
    status: Literal["FILLED", "REJECTED"]
    mode: Literal["PAPER", "DRY_RUN"]
    created_at: str = ""
    symbol_name: str = ""


class Portfolio(BaseModel):
    cash: Decimal
    positions: dict[str, Decimal]
    realized_pnl: Decimal
    holdings: list[dict] = []
    total_invested: Decimal = Decimal("0")
    total_market_value: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    total_pnl_percent: Decimal = Decimal("0")
    total_assets: Decimal = Decimal("0")
