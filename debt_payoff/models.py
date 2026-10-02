"""数据类型定义：债务、方案、策略与推演结果。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Strategy(Enum):
    """还款优先级策略。"""

    AVALANCHE = "avalanche"  # 雪崩法：年利率从高到低
    SNOWBALL = "snowball"    # 雪球法：初始本金从低到高


@dataclass(frozen=True)
class Debt:
    """单笔债务。金额单位为分，年利率单位为基点（100 基点 = 1%）。"""

    principal_cents: int
    annual_rate_bp: int
    min_payment_cents: int

    def __post_init__(self) -> None:
        if not isinstance(self.principal_cents, int) or self.principal_cents <= 0:
            raise ValueError("本金必须为正整数分")
        if not isinstance(self.annual_rate_bp, int) or self.annual_rate_bp < 0:
            raise ValueError("年利率必须为非负整数基点")
        if not isinstance(self.min_payment_cents, int) or self.min_payment_cents <= 0:
            raise ValueError("最低月供必须为正整数分")


@dataclass(frozen=True)
class Plan:
    """一个还款方案：多笔债务 + 一笔全局额外月供（分）。"""

    debts: tuple[Debt, ...]
    extra_payment_cents: int = 0

    def __post_init__(self) -> None:
        debts = tuple(self.debts)
        object.__setattr__(self, "debts", debts)
        if not debts:
            raise ValueError("方案至少包含一笔债务")
        for debt in debts:
            if not isinstance(debt, Debt):
                raise TypeError("debts 元素必须是 Debt")
        if not isinstance(self.extra_payment_cents, int) or self.extra_payment_cents < 0:
            raise ValueError("额外月供必须为非负整数分")


@dataclass(frozen=True)
class PayoffResult:
    """推演结果。永不结清时 paid_off 为 False，payoff_month 为 None。"""

    strategy: Strategy
    paid_off: bool
    payoff_month: int | None
    total_interest_cents: int
    total_paid_cents: int
