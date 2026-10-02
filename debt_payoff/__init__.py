"""债务偿还推演库：比较雪崩法与雪球法的还款成本。"""
from .models import Debt, PayoffResult, Plan, Strategy
from .simulator import compare_strategies, simulate

__all__ = [
    "Debt",
    "Plan",
    "PayoffResult",
    "Strategy",
    "simulate",
    "compare_strategies",
]
