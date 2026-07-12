"""Centralized simulation fee and slippage rules."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationFeeConfig:
    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    sell_tax_rate: float = 0.0005
    slippage_bps: float = 2.0

    def validate(self) -> None:
        if self.commission_rate < 0 or self.minimum_commission < 0:
            raise ValueError("佣金费率和最低佣金不能为负数")
        if self.sell_tax_rate < 0 or self.slippage_bps < 0:
            raise ValueError("卖出税率和滑点不能为负数")

    def execution_price(self, open_price: float, side: str) -> float:
        """Apply adverse slippage to the next-session open price."""
        if open_price <= 0:
            raise ValueError("开盘价必须大于 0")
        direction = 1 if side == "BUY" else -1
        return open_price * (1 + direction * self.slippage_bps / 10_000)

    def fees(self, side: str, price: float, quantity: int) -> tuple[float, float]:
        notional = price * quantity
        commission = max(notional * self.commission_rate, self.minimum_commission)
        tax = notional * self.sell_tax_rate if side == "SELL" else 0.0
        return commission, tax
