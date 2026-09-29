from decimal import Decimal
from threading import Lock
from pathlib import Path
import json
from datetime import datetime

from .models import Order, OrderRequest, Portfolio


class PaperBroker:
    def __init__(self, initial_cash: Decimal = Decimal("10000000"), state_file: Path | None = None) -> None:
        self._state_file = state_file
        self._cash = initial_cash
        self._positions: dict[str, Decimal] = {}
        self._costs: dict[str, Decimal] = {}
        self._realized_pnl = Decimal("0")
        self._orders: list[Order] = []
        self._next_id = 1
        self._lock = Lock()
        self._load()

    def _load(self) -> None:
        if not self._state_file or not self._state_file.exists(): return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._cash = Decimal(data["cash"])
            self._positions = {k: Decimal(v) for k, v in data.get("positions", {}).items()}
            self._costs = {k: Decimal(v) for k, v in data.get("costs", {}).items()}
            self._realized_pnl = Decimal(data.get("realized_pnl", "0"))
            self._orders = [Order.model_validate(o) for o in data.get("orders", [])]
            self._next_id = max([o.id for o in self._orders], default=0) + 1
        except (OSError, ValueError, KeyError):
            pass

    def _save(self) -> None:
        data = {"cash": str(self._cash), "positions": {k: str(v) for k,v in self._positions.items()}, "costs": {k: str(v) for k,v in self._costs.items()}, "realized_pnl": str(self._realized_pnl), "orders": [o.model_dump(mode="json") for o in self._orders]}
        if self._state_file:
            self._state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def portfolio(self) -> Portfolio:
        with self._lock:
            return Portfolio(cash=self._cash, positions=self._positions.copy(), realized_pnl=self._realized_pnl,
                holdings=[{"symbol": s, "quantity": q, "average_price": self._costs.get(s, Decimal("0"))}
                          for s, q in self._positions.items() if q > 0])

    def orders(self) -> list[Order]:
        with self._lock:
            return self._orders.copy()

    def place(self, request: OrderRequest, mode: str = "PAPER") -> Order:
        with self._lock:
            amount = request.quantity * request.price
            position = self._positions.get(request.symbol, Decimal("0"))
            if request.side == "BUY":
                if mode == "PAPER" and amount > self._cash:
                    status = "REJECTED"
                else:
                    status = "FILLED"
                    if mode == "PAPER":
                        self._cash -= amount
                        new_quantity = position + request.quantity
                        self._positions[request.symbol] = new_quantity
                        self._costs[request.symbol] = ((self._costs.get(request.symbol, Decimal("0")) * position) + amount) / new_quantity
            else:
                status = "FILLED" if mode == "DRY_RUN" or position >= request.quantity else "REJECTED"
                if status == "FILLED" and mode == "PAPER":
                    self._cash += amount
                    remaining = position - request.quantity
                    if remaining:
                        self._positions[request.symbol] = remaining
                    else:
                        self._positions.pop(request.symbol, None)
                        self._costs.pop(request.symbol, None)
            order = Order(id=self._next_id, client_order_id=f"paper-{self._next_id}", **request.model_dump(), status=status, mode=mode,
                          created_at=datetime.now().astimezone().isoformat(timespec="seconds"))
            self._next_id += 1
            self._orders.append(order)
            self._save()
            return order
