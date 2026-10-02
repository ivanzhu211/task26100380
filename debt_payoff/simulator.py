"""推演引擎：从同一初始状态按策略逐月模拟还款。"""
from __future__ import annotations

from .models import PayoffResult, Plan, Strategy

_BP_PER_YEAR_MONTHS = 120000  # 10000 基点/100% × 12 个月


def _interest_cents(balance_cents: int, annual_rate_bp: int) -> int:
    """期初本金 × 年利率基点 ÷ 120000，四舍五入到分，半分向上。"""
    product = balance_cents * annual_rate_bp
    quotient, remainder = divmod(product, _BP_PER_YEAR_MONTHS)
    if remainder * 2 >= _BP_PER_YEAR_MONTHS:
        quotient += 1
    return quotient


def _priority_order(plan: Plan, strategy: Strategy) -> list[int]:
    """方案开始时固定的偿债优先级（输入下标序列），并列按输入顺序。"""
    indices = range(len(plan.debts))
    if strategy is Strategy.AVALANCHE:
        return sorted(indices, key=lambda i: -plan.debts[i].annual_rate_bp)
    return sorted(indices, key=lambda i: plan.debts[i].principal_cents)


def simulate(plan: Plan, strategy: Strategy) -> PayoffResult:
    """按给定策略推演一个方案，返回结清结果或“永不结清”。"""
    debts = plan.debts
    count = len(debts)
    balances = [d.principal_cents for d in debts]
    settled = [False] * count
    order = _priority_order(plan, strategy)
    budget = sum(d.min_payment_cents for d in debts) + plan.extra_payment_cents

    month = 0
    total_interest = 0
    total_paid = 0

    while True:
        month += 1
        opening = list(balances)

        # 1) 对所有未结清债务计息，利息加入欠款。
        for i in range(count):
            if not settled[i]:
                interest = _interest_cents(balances[i], debts[i].annual_rate_bp)
                balances[i] += interest
                total_interest += interest

        # 2) 先给每笔未结清债务支付约定最低月供（不超过计息后欠款）。
        remaining = budget
        cleared_this_month = False
        for i in range(count):
            if not settled[i]:
                pay = min(debts[i].min_payment_cents, balances[i])
                balances[i] -= pay
                remaining -= pay
                total_paid += pay
                if balances[i] == 0:
                    settled[i] = True
                    cleared_this_month = True

        # 3) 剩余预算按策略优先级继续偿还，同月可连续结清多笔。
        for i in order:
            if remaining <= 0:
                break
            if settled[i]:
                continue
            pay = min(remaining, balances[i])
            balances[i] -= pay
            remaining -= pay
            total_paid += pay
            if balances[i] == 0:
                settled[i] = True
                cleared_this_month = True

        if all(settled):
            return PayoffResult(
                strategy=strategy,
                paid_off=True,
                payoff_month=month,
                total_interest_cents=total_interest,
                total_paid_cents=total_paid,
            )

        # 4) 永不结清判定：本月没有任何债务结清，且每笔未结清债务的
        #    欠款都未减少。此后付款构成不变、利息不减，僵局永续。
        #    若本月有债务结清，下月付款构成会变化，不能据此判定。
        if not cleared_this_month and all(
            balances[i] >= opening[i] for i in range(count) if not settled[i]
        ):
            return PayoffResult(
                strategy=strategy,
                paid_off=False,
                payoff_month=None,
                total_interest_cents=total_interest,
                total_paid_cents=total_paid,
            )


def compare_strategies(plan: Plan) -> dict[Strategy, PayoffResult]:
    """对同一方案分别用雪崩法和雪球法推演，返回两个字结果。"""
    return {strategy: simulate(plan, strategy) for strategy in Strategy}
