"""类型定义：债务输入与推演结果。所有金额单位为分，利率单位为基点。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Strategy(Enum):
    """还款策略。"""

    AVALANCHE = "avalanche"  # 雪崩法：年利率从高到低
    SNOWBALL = "snowball"    # 雪球法：初始本金从低到高


class PayoffStatus(Enum):
    """推演结局。"""

    PAID_OFF = "paid_off"        # 有限月内全部结清
    NEVER_PAID_OFF = "never"     # 永远无法全部结清


@dataclass(frozen=True)
class Debt:
    """单笔债务输入。

    principal_cents: 初始本金（正整数分）
    annual_rate_bps: 年利率（非负整数基点，100 基点 = 1%）
    min_payment_cents: 约定最低月供（正整数分）
    """

    principal_cents: int
    annual_rate_bps: int
    min_payment_cents: int


@dataclass(frozen=True)
class Plan:
    """一个还款方案：多笔债务 + 一笔全局额外月供（非负整数分）。"""

    debts: tuple[Debt, ...]
    extra_payment_cents: int


@dataclass(frozen=True)
class SimulationResult:
    """推演结果。

    status: 结清 / 永不结清
    months: 结清月序号（未结清时为 None）
    total_interest_cents: 累计利息（未结清时为 None）
    total_paid_cents: 累计付款（未结清时为 None）
    """

    status: PayoffStatus
    months: int | None
    total_interest_cents: int | None
    total_paid_cents: int | None
