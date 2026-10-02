"""逐月推演核心。

规则要点：
- 总月预算 = 初始所有最低月供之和 + 全局额外月供，全程固定。
- 每月先对所有未结清债务计息：期初本金 * 基点 / 120000，半分向上取整。
- 先支付每笔债务的约定最低月供（不超过计息后欠款），
  剩余预算按策略优先级继续偿还，同月可连续结清多笔。
- 永不结清判定：某月没有任何债务结清，且所有未结清债务的
  月末欠款都不低于其月初欠款，则此后欠款单调不减，永远无法结清。
"""

from __future__ import annotations

from .models import PayoffStatus, Plan, SimulationResult, Strategy

_BPS_DENOMINATOR = 120000  # 12 个月 * 10000 基点


def _monthly_interest_cents(principal_cents: int, annual_rate_bps: int) -> int:
    """期初本金乘年利率基点除以 120000，四舍五入到分，半分向上。"""
    numerator = principal_cents * annual_rate_bps
    return (2 * numerator + _BPS_DENOMINATOR) // (2 * _BPS_DENOMINATOR)


def _validate(plan: Plan) -> None:
    if not plan.debts:
        raise ValueError("方案至少需要一笔债务")
    for debt in plan.debts:
        if debt.principal_cents <= 0:
            raise ValueError("本金必须为正整数分")
        if debt.min_payment_cents <= 0:
            raise ValueError("最低月供必须为正整数分")
        if debt.annual_rate_bps < 0:
            raise ValueError("年利率必须为非负整数基点")
    if plan.extra_payment_cents < 0:
        raise ValueError("额外月供必须为非负整数分")


def _priority_order(plan: Plan, strategy: Strategy) -> list[int]:
    """返回按策略排序后的债务下标；并列保持输入顺序（稳定排序）。"""
    indices = list(range(len(plan.debts)))
    if strategy is Strategy.AVALANCHE:
        indices.sort(key=lambda i: -plan.debts[i].annual_rate_bps)
    elif strategy is Strategy.SNOWBALL:
        indices.sort(key=lambda i: plan.debts[i].principal_cents)
    else:
        raise ValueError(f"未知策略: {strategy!r}")
    return indices


def simulate(plan: Plan, strategy: Strategy) -> SimulationResult:
    """从同一初始状态按给定策略逐月推演。"""
    _validate(plan)

    debts = plan.debts
    count = len(debts)
    balances = [debt.principal_cents for debt in debts]
    settled = [False] * count
    total_budget = (
        sum(debt.min_payment_cents for debt in debts) + plan.extra_payment_cents
    )
    priority = _priority_order(plan, strategy)

    total_interest = 0
    total_paid = 0
    month = 0

    while True:
        month += 1
        start_balances = list(balances)
        settled_this_month = False

        # 1. 对所有未结清债务计息，利息计入欠款。
        for i in range(count):
            if settled[i]:
                continue
            interest = _monthly_interest_cents(balances[i], debts[i].annual_rate_bps)
            balances[i] += interest
            total_interest += interest

        # 2. 先支付每笔债务的约定最低月供（不超过计息后欠款）。
        budget = total_budget
        for i in range(count):
            if settled[i]:
                continue
            payment = min(debts[i].min_payment_cents, balances[i])
            balances[i] -= payment
            budget -= payment
            total_paid += payment
            if balances[i] == 0:
                settled[i] = True
                settled_this_month = True

        # 3. 剩余预算按策略优先级继续偿还，同月可连续结清多笔。
        for i in priority:
            if budget <= 0:
                break
            if settled[i]:
                continue
            payment = min(budget, balances[i])
            balances[i] -= payment
            budget -= payment
            total_paid += payment
            if balances[i] == 0:
                settled[i] = True
                settled_this_month = True

        # 4. 全部结清则返回；预算余额不算付款也不退款。
        if all(settled):
            return SimulationResult(
                status=PayoffStatus.PAID_OFF,
                months=month,
                total_interest_cents=total_interest,
                total_paid_cents=total_paid,
            )

        # 5. 永不结清判定：本月无债务结清，且所有未结清债务
        #    月末欠款均不低于月初欠款，则此后单调不减。
        if not settled_this_month and all(
            settled[i] or balances[i] >= start_balances[i] for i in range(count)
        ):
            return SimulationResult(
                status=PayoffStatus.NEVER_PAID_OFF,
                months=None,
                total_interest_cents=None,
                total_paid_cents=None,
            )
