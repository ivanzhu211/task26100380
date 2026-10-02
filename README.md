# debt_payoff 债务偿还推演库

纯进程内 Python 库，用于比较**雪崩法**与**雪球法**的还款成本。无接口层、无持久化，输入与结果仅保存在内存中。

## 规则

- 方案含多笔债务：本金（正整数分）、年利率（非负整数基点，100 基点 = 1%）、约定最低月供（正整数分）；另有一笔全局额外月供（非负整数分）。
- 总月预算固定 = 全部最低月供之和 + 额外月供；债务结清后预算不变，腾出的资金同月流向下一笔。
- 第 1 月即计息并付款：期初本金 × 基点 ÷ 120000，四舍五入到分（半分向上），利息计入欠款后付款。
- 每月先付各笔最低月供（不超过计息后欠款），剩余预算按策略优先级偿还，同月可连续结清多笔。
- 雪崩法按年利率降序、雪球法按初始本金升序；并列按输入顺序；优先级在方案开始时固定。
- 暂时负摊销（某笔先越还越多）但最终能还清的方案给出准确结果；永远无法全部结清的方案返回“永不结清”。

## 使用

```python
from debt_payoff import Debt, Plan, Strategy, simulate, compare_strategies

plan = Plan(
    debts=(
        Debt(principal_cents=100_000, annual_rate_bp=1200, min_payment_cents=5_000),
        Debt(principal_cents=50_000,  annual_rate_bp=600,  min_payment_cents=3_000),
    ),
    extra_payment_cents=2_000,
)

result = simulate(plan, Strategy.AVALANCHE)
if result.paid_off:
    print(result.payoff_month, result.total_interest_cents, result.total_paid_cents)
else:
    print("永不结清")

both = compare_strategies(plan)  # {Strategy.AVALANCHE: ..., Strategy.SNOWBALL: ...}
```

`PayoffResult` 字段：`paid_off`、`payoff_month`（结清月序号，永不结清为 `None`）、`total_interest_cents`、`total_paid_cents`。已结清方案恒满足 `total_paid_cents = 初始本金之和 + total_interest_cents`。

## 测试

```bash
python3 -m pytest tests/ -q
```
