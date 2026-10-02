"""debtpayoff 自动化测试。

包含一个独立编写的逐月核算参考实现，用于与库输出对照。
"""

from __future__ import annotations

import unittest

from debtpayoff import Debt, PayoffStatus, Plan, Strategy, simulate


def reference_simulate(plan: Plan, strategy: Strategy) -> dict:
    """独立逐月核算参考实现（直接按需求文字重写，不调用库代码）。"""
    balances = [d.principal_cents for d in plan.debts]
    alive = [True] * len(plan.debts)
    budget_total = sum(d.min_payment_cents for d in plan.debts) + plan.extra_payment_cents
    if strategy is Strategy.AVALANCHE:
        order = sorted(range(len(plan.debts)), key=lambda i: -plan.debts[i].annual_rate_bps)
    else:
        order = sorted(range(len(plan.debts)), key=lambda i: plan.debts[i].principal_cents)
    total_interest = 0
    total_paid = 0
    month = 0
    while True:
        month += 1
        start = list(balances)
        settled_this_month = False
        for i in range(len(plan.debts)):
            if not alive[i]:
                continue
            # 半分向上：floor(x + 0.5)
            num = balances[i] * plan.debts[i].annual_rate_bps
            interest = (2 * num + 120000) // 240000
            balances[i] += interest
            total_interest += interest
        budget = budget_total
        for i in range(len(plan.debts)):
            if not alive[i]:
                continue
            pay = min(plan.debts[i].min_payment_cents, balances[i])
            balances[i] -= pay
            budget -= pay
            total_paid += pay
        for i in order:
            if budget <= 0:
                break
            if not alive[i]:
                continue
            pay = min(budget, balances[i])
            balances[i] -= pay
            budget -= pay
            total_paid += pay
        for i in range(len(plan.debts)):
            if alive[i] and balances[i] == 0:
                alive[i] = False
                settled_this_month = True
        if not any(alive):
            return {"months": month, "interest": total_interest, "paid": total_paid}
        if not settled_this_month and all(
            (not alive[i]) or balances[i] >= start[i] for i in range(len(plan.debts))
        ):
            return {"months": None, "interest": None, "paid": None}


class SmallPlanMatchesReferenceTest(unittest.TestCase):
    """小额方案与独立逐月核算结果一致。"""

    def assert_matches_reference(self, plan: Plan):
        for strategy in (Strategy.AVALANCHE, Strategy.SNOWBALL):
            result = simulate(plan, strategy)
            expected = reference_simulate(plan, strategy)
            self.assertEqual(result.months, expected["months"], strategy)
            self.assertEqual(result.total_interest_cents, expected["interest"], strategy)
            self.assertEqual(result.total_paid_cents, expected["paid"], strategy)
            if result.status is PayoffStatus.PAID_OFF:
                principal = sum(d.principal_cents for d in plan.debts)
                self.assertEqual(
                    result.total_paid_cents,
                    principal + result.total_interest_cents,
                    "累计付款必须等于初始本金加累计利息",
                )

    def test_mixed_small_plan(self):
        plan = Plan(
            debts=(
                Debt(principal_cents=5000, annual_rate_bps=2400, min_payment_cents=100),
                Debt(principal_cents=300, annual_rate_bps=0, min_payment_cents=100),
                Debt(principal_cents=1250, annual_rate_bps=600, min_payment_cents=60),
            ),
            extra_payment_cents=500,
        )
        self.assert_matches_reference(plan)

    def test_half_cent_rounds_up(self):
        # 25 分本金、2400 基点 -> 月息 0.5 分，半分向上取整为 1 分。
        plan = Plan(
            debts=(Debt(principal_cents=25, annual_rate_bps=2400, min_payment_cents=10),),
            extra_payment_cents=0,
        )
        result = simulate(plan, Strategy.AVALANCHE)
        self.assertEqual(result.status, PayoffStatus.PAID_OFF)
        self.assertEqual(result.months, 3)
        self.assertEqual(result.total_interest_cents, 1)
        self.assertEqual(result.total_paid_cents, 26)

    def test_multiple_debts_settle_same_month(self):
        # 大额额外月供在同一月内连续结清两笔债务。
        plan = Plan(
            debts=(
                Debt(principal_cents=1000, annual_rate_bps=0, min_payment_cents=500),
                Debt(principal_cents=2000, annual_rate_bps=0, min_payment_cents=500),
            ),
            extra_payment_cents=10000,
        )
        for strategy in (Strategy.AVALANCHE, Strategy.SNOWBALL):
            result = simulate(plan, strategy)
            self.assertEqual(result.status, PayoffStatus.PAID_OFF)
            self.assertEqual(result.months, 1)
            self.assertEqual(result.total_interest_cents, 0)
            self.assertEqual(result.total_paid_cents, 3000)

    def test_min_payment_below_interest_negative_amortization(self):
        # 最低月供不足以覆盖利息：债务先增长，但最终仍结清。
        plan = Plan(
            debts=(
                Debt(principal_cents=1000, annual_rate_bps=0, min_payment_cents=1000),
                Debt(principal_cents=10000, annual_rate_bps=1200, min_payment_cents=50),
            ),
            extra_payment_cents=0,
        )
        self.assert_matches_reference(plan)
        result = simulate(plan, Strategy.AVALANCHE)
        self.assertEqual(result.status, PayoffStatus.PAID_OFF)
        # 第 1 月：债务1结清；债务2 计息 100 后只还 50，欠款升至 10050。
        # 第 2 月起每月还 1050：10050 -> 计息 101（100.5 半分向上）-> 9101 ...
        self.assertEqual(result.months, 12)
        self.assertEqual(result.total_interest_cents, 668)
        self.assertEqual(result.total_paid_cents, 11000 + 668)


class TemporaryNegativeAmortizationTest(unittest.TestCase):
    """某笔债务先增长，靠其他债务结清释放的预算最终还清。"""

    def test_grows_then_paid_off(self):
        plan = Plan(
            debts=(
                Debt(principal_cents=2000, annual_rate_bps=0, min_payment_cents=1000),
                Debt(principal_cents=50000, annual_rate_bps=2400, min_payment_cents=500),
            ),
            extra_payment_cents=0,
        )
        result = simulate(plan, Strategy.AVALANCHE)
        self.assertEqual(result.status, PayoffStatus.PAID_OFF)
        self.assertIsNotNone(result.months)
        # 与参考实现一致
        expected = reference_simulate(plan, Strategy.AVALANCHE)
        self.assertEqual(result.months, expected["months"])
        self.assertEqual(result.total_interest_cents, expected["interest"])
        # 债务2 月息 1000 > 最低月供 500，前两个月确实越还越多：
        # 50000 -> 50500 -> 51005，第 3 月起预算 1500 才开始下降。
        self.assertGreater(result.months, 2)


class NeverPaidOffTest(unittest.TestCase):
    """永不结清与暂时负摊销须正确区分。"""

    def test_payment_exactly_covers_interest_never_settles(self):
        # 月供恰好只够利息：本金永远不变。
        plan = Plan(
            debts=(Debt(principal_cents=100000, annual_rate_bps=1200, min_payment_cents=1000),),
            extra_payment_cents=0,
        )
        result = simulate(plan, Strategy.AVALANCHE)
        self.assertEqual(result.status, PayoffStatus.NEVER_PAID_OFF)
        self.assertIsNone(result.months)
        self.assertIsNone(result.total_interest_cents)
        self.assertIsNone(result.total_paid_cents)

    def test_payment_below_interest_never_settles(self):
        plan = Plan(
            debts=(Debt(principal_cents=100000, annual_rate_bps=1200, min_payment_cents=500),),
            extra_payment_cents=0,
        )
        self.assertEqual(simulate(plan, Strategy.AVALANCHE).status, PayoffStatus.NEVER_PAID_OFF)

    def test_temporary_negative_amortization_still_pays_off(self):
        # 同样最低月供低于利息，但其他债务结清后释放预算，最终能还清。
        plan = Plan(
            debts=(
                Debt(principal_cents=1000, annual_rate_bps=0, min_payment_cents=1000),
                Debt(principal_cents=100000, annual_rate_bps=1200, min_payment_cents=500),
            ),
            extra_payment_cents=0,
        )
        result = simulate(plan, Strategy.AVALANCHE)
        self.assertEqual(result.status, PayoffStatus.PAID_OFF)
        self.assertIsNotNone(result.months)


class StrategyPriorityTest(unittest.TestCase):
    """两种策略从同一初始状态推演，优先级不同导致成本不同。"""

    def test_avalanche_and_snowball_differ(self):
        plan = Plan(
            debts=(
                Debt(principal_cents=5000, annual_rate_bps=2400, min_payment_cents=100),
                Debt(principal_cents=1000, annual_rate_bps=0, min_payment_cents=100),
            ),
            extra_payment_cents=500,
        )
        avalanche = simulate(plan, Strategy.AVALANCHE)
        snowball = simulate(plan, Strategy.SNOWBALL)
        self.assertEqual(avalanche.status, PayoffStatus.PAID_OFF)
        self.assertEqual(snowball.status, PayoffStatus.PAID_OFF)
        # 雪崩法先还高息债务，总利息不高于雪球法。
        self.assertLess(avalanche.total_interest_cents, snowball.total_interest_cents)
        for result in (avalanche, snowball):
            self.assertEqual(result.total_paid_cents, 6000 + result.total_interest_cents)

    def test_ties_keep_input_order(self):
        # 并列时按输入顺序：同利率时雪崩法先还排在前面的债务。
        plan = Plan(
            debts=(
                Debt(principal_cents=100, annual_rate_bps=1200, min_payment_cents=50),
                Debt(principal_cents=900, annual_rate_bps=1200, min_payment_cents=50),
            ),
            extra_payment_cents=50,
        )
        result = simulate(plan, Strategy.AVALANCHE)
        # 第 1 月：各计息 1 分，最低月供后 51 / 851，额外 50 全给第一笔 -> 1。
        # 第 2 月：第一笔计息 0 后还 1 结清；之后预算流向第二笔。
        expected = reference_simulate(plan, Strategy.AVALANCHE)
        self.assertEqual(result.months, expected["months"])
        self.assertEqual(result.total_interest_cents, expected["interest"])


class ValidationTest(unittest.TestCase):
    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            simulate(Plan(debts=(), extra_payment_cents=0), Strategy.AVALANCHE)
        with self.assertRaises(ValueError):
            simulate(
                Plan(debts=(Debt(0, 1200, 100),), extra_payment_cents=0),
                Strategy.AVALANCHE,
            )
        with self.assertRaises(ValueError):
            simulate(
                Plan(debts=(Debt(100, 1200, 0),), extra_payment_cents=0),
                Strategy.AVALANCHE,
            )
        with self.assertRaises(ValueError):
            simulate(
                Plan(debts=(Debt(100, -1, 100),), extra_payment_cents=0),
                Strategy.AVALANCHE,
            )
        with self.assertRaises(ValueError):
            simulate(
                Plan(debts=(Debt(100, 1200, 100),), extra_payment_cents=-1),
                Strategy.AVALANCHE,
            )


if __name__ == "__main__":
    unittest.main()
