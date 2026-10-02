"""debt_payoff 自动化测试。

小额方案的期望值均为独立逐月手工核算结果：
- 月息 = 期初本金 × 年利率基点 ÷ 120000，半分向上取整；
- 每月先付各笔最低月供，剩余预算按策略优先级偿还；
- 总月预算 = 全部最低月供之和 + 额外月供，结清后预算不变。
"""
import pytest

from debt_payoff import Debt, Plan, Strategy, compare_strategies, simulate

BOTH = [Strategy.AVALANCHE, Strategy.SNOWBALL]


def manual_schedule(plan, order):
    """独立逐月核算：返回 (结清月, 累计利息, 累计付款)，永不结清返回 None。"""
    balances = [d.principal_cents for d in plan.debts]
    done = [False] * len(plan.debts)
    budget = sum(d.min_payment_cents for d in plan.debts) + plan.extra_payment_cents
    interest_total = paid_total = 0
    for month in range(1, 100000):
        opening = list(balances)
        for i, d in enumerate(plan.debts):
            if not done[i]:
                interest = (balances[i] * d.annual_rate_bp + 60000) // 120000
                balances[i] += interest
                interest_total += interest
        remaining = budget
        cleared = False
        for i, d in enumerate(plan.debts):
            if not done[i]:
                pay = min(d.min_payment_cents, balances[i])
                balances[i] -= pay
                remaining -= pay
                paid_total += pay
                if balances[i] == 0:
                    done[i] = cleared = True
        for i in order:
            if remaining <= 0:
                break
            if not done[i]:
                pay = min(remaining, balances[i])
                balances[i] -= pay
                remaining -= pay
                paid_total += pay
                if balances[i] == 0:
                    done[i] = cleared = True
        if all(done):
            return month, interest_total, paid_total
        if not cleared and all(
            balances[i] >= opening[i] for i in range(len(plan.debts)) if not done[i]
        ):
            return None
    raise AssertionError("推演未收敛")


def check_against_manual(plan, strategy):
    result = simulate(plan, strategy)
    if strategy is Strategy.AVALANCHE:
        order = sorted(range(len(plan.debts)), key=lambda i: -plan.debts[i].annual_rate_bp)
    else:
        order = sorted(range(len(plan.debts)), key=lambda i: plan.debts[i].principal_cents)
    expected = manual_schedule(plan, order)
    if expected is None:
        assert not result.paid_off
        assert result.payoff_month is None
    else:
        month, interest, paid = expected
        assert result.paid_off
        assert result.payoff_month == month
        assert result.total_interest_cents == interest
        assert result.total_paid_cents == paid
    return result


# --- 小额方案：与独立逐月核算一致 -------------------------------------------

# D1：本金 1000 分、12000 基点（10%/月）、最低月供 500
# D2：本金 800 分、6000 基点（5%/月）、最低月供 300；额外月供 200
SMALL_PLAN = Plan((Debt(1000, 12000, 500), Debt(800, 6000, 300)), 200)


def test_small_plan_avalanche_matches_manual():
    r = check_against_manual(SMALL_PLAN, Strategy.AVALANCHE)
    assert (r.payoff_month, r.total_interest_cents, r.total_paid_cents) == (3, 207, 2007)


def test_small_plan_snowball_matches_manual():
    r = check_against_manual(SMALL_PLAN, Strategy.SNOWBALL)
    assert (r.payoff_month, r.total_interest_cents, r.total_paid_cents) == (3, 219, 2019)


def test_half_cent_rounds_up():
    # 5 分 × 60000 基点 ÷ 120000 = 2.5 分 → 向上取整为 3 分
    r = simulate(Plan((Debt(5, 60000, 10),), 0), Strategy.AVALANCHE)
    assert (r.payoff_month, r.total_interest_cents, r.total_paid_cents) == (1, 3, 8)
    # 3 分 × 60000 基点 ÷ 120000 = 1.5 分 → 2 分
    r = simulate(Plan((Debt(3, 60000, 10),), 0), Strategy.AVALANCHE)
    assert r.total_interest_cents == 2
    # 4 分 × 60000 基点 ÷ 120000 = 2.0 分 → 恰好 2 分，不进位
    r = simulate(Plan((Debt(4, 60000, 10),), 0), Strategy.AVALANCHE)
    assert r.total_interest_cents == 2


def test_multiple_debts_cleared_same_month():
    # 额外月供 500：第 2 月剩余预算在同月内连续结清 D2 与 D1
    plan = Plan((Debt(1000, 12000, 500), Debt(800, 6000, 300)), 500)
    r = check_against_manual(plan, Strategy.SNOWBALL)
    assert (r.payoff_month, r.total_interest_cents, r.total_paid_cents) == (2, 202, 2002)


def test_min_payment_below_interest_within_plan():
    # D2 最低月供 100 < 月息 200，计入方案后仍靠 D1 结清释放的预算还清
    plan = Plan((Debt(5000, 600, 200), Debt(20000, 1200, 100)), 0)
    r = check_against_manual(plan, Strategy.AVALANCHE)
    assert r.paid_off
    assert r.payoff_month == 174


# --- 暂时负摊销 vs 永不结清 --------------------------------------------------

def test_temporary_negative_amortization_eventually_pays_off():
    # D2 单独存在时永不结清（最低月供 100 < 月息 200）
    alone = simulate(Plan((Debt(20000, 1200, 100),), 0), Strategy.AVALANCHE)
    assert not alone.paid_off
    # 与 D1 同方案时，D1 结清后释放的预算让 D2 最终还清
    plan = Plan((Debt(5000, 600, 200), Debt(20000, 1200, 100)), 0)
    for strategy in BOTH:
        r = simulate(plan, strategy)
        assert r.paid_off
        assert r.total_paid_cents == 25000 + r.total_interest_cents


def test_payment_exactly_covers_interest_never_pays_off():
    # 月供恰好只够利息：欠款恒定，永不结清
    plan = Plan((Debt(100000, 1200, 1000),), 0)
    for strategy in BOTH:
        r = simulate(plan, strategy)
        assert not r.paid_off
        assert r.payoff_month is None


def test_growing_balance_never_pays_off():
    # 月供低于利息：欠款越还越多，永不结清
    plan = Plan((Debt(100000, 1200, 999),), 0)
    for strategy in BOTH:
        assert not simulate(plan, strategy).paid_off
    # 额外月供补上后恰好只够利息，仍永不结清
    plan = Plan((Debt(100000, 1200, 999),), 1)
    assert not simulate(plan, Strategy.AVALANCHE).paid_off


# --- 不变量与策略行为 -------------------------------------------------------

@pytest.mark.parametrize(
    "plan",
    [
        Plan((Debt(1000, 12000, 500), Debt(800, 6000, 300)), 200),
        Plan((Debt(5000, 600, 200), Debt(20000, 1200, 100)), 0),
        Plan((Debt(100, 0, 1), Debt(999983, 9999, 1234), Debt(500, 30000, 7)), 42),
        Plan((Debt(1, 1, 1),), 0),
    ],
)
def test_paid_total_equals_principal_plus_interest(plan):
    for strategy in BOTH:
        r = simulate(plan, strategy)
        if r.paid_off:
            principal = sum(d.principal_cents for d in plan.debts)
            assert r.total_paid_cents == principal + r.total_interest_cents


def test_priority_ties_keep_input_order():
    low = Debt(1000, 0, 50)
    high = Debt(1000, 1200, 50)
    # 雪球法本金并列：输入顺序决定谁先还，利息不同
    assert simulate(Plan((low, high), 100), Strategy.SNOWBALL).total_interest_cents == 78
    assert simulate(Plan((high, low), 100), Strategy.SNOWBALL).total_interest_cents == 40
    # 雪崩法按利率排序：与输入顺序无关
    assert simulate(Plan((low, high), 100), Strategy.AVALANCHE).total_interest_cents == 40
    assert simulate(Plan((high, low), 100), Strategy.AVALANCHE).total_interest_cents == 40


def test_compare_strategies_returns_both():
    results = compare_strategies(SMALL_PLAN)
    assert set(results) == set(Strategy)
    assert results[Strategy.AVALANCHE].total_interest_cents <= results[Strategy.SNOWBALL].total_interest_cents


def test_zero_rate_pays_off_without_interest():
    r = simulate(Plan((Debt(1000, 0, 300),), 0), Strategy.AVALANCHE)
    assert (r.payoff_month, r.total_interest_cents, r.total_paid_cents) == (4, 0, 1000)


# --- 参数校验 ----------------------------------------------------------------

def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        Debt(0, 1200, 100)
    with pytest.raises(ValueError):
        Debt(1000, -1, 100)
    with pytest.raises(ValueError):
        Debt(1000, 1200, 0)
    with pytest.raises(ValueError):
        Plan((), 0)
    with pytest.raises(ValueError):
        Plan((Debt(1000, 1200, 100),), -1)
