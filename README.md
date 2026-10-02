# debtpayoff：债务偿还推演库

纯 Python 库，由上层直接调用，无接口层；输入与推演结果只保存在进程内。
用于比较**雪崩法**与**雪球法**的还款成本，能正确区分
「暂时负摊销但最终结清」与「永远无法结清」两种情形。

## 数据约定

- 金额单位：分（本金、最低月供为正整数；额外月供为非负整数）
- 利率单位：基点（非负整数，100 基点 = 1%）
- 月息 = 期初本金 × 基点 ÷ 120000，四舍五入到分，恰好半分向上取整
- 总月预算 = 初始所有最低月供之和 + 全局额外月供，全程固定；
  债务结清后腾出的资金继续偿还其他债务
- 每月先计息再付款：先付每笔债务的约定最低月供（不超过计息后欠款），
  剩余预算按策略优先级偿还，同月可连续结清多笔；
  全部结清后的预算余额不算付款也不退款
- 雪崩法按年利率从高到低，雪球法按初始本金从低到高；
  并列按输入顺序，优先级在方案开始时固定

## 使用示例

```python
from debtpayoff import Debt, PayoffStatus, Plan, Strategy, simulate

plan = Plan(
    debts=(
        Debt(principal_cents=500000, annual_rate_bps=2400, min_payment_cents=10000),
        Debt(principal_cents=100000, annual_rate_bps=600,  min_payment_cents=5000),
    ),
    extra_payment_cents=2000,
)

for strategy in (Strategy.AVALANCHE, Strategy.SNOWBALL):
    result = simulate(plan, strategy)
    if result.status is PayoffStatus.PAID_OFF:
        print(strategy.value, "结清月:", result.months,
              "累计利息:", result.total_interest_cents)
    else:
        print(strategy.value, "永不结清")
```

## API

- `Debt(principal_cents, annual_rate_bps, min_payment_cents)`：单笔债务
- `Plan(debts, extra_payment_cents)`：还款方案（`debts` 为 `Debt` 元组）
- `simulate(plan, strategy) -> SimulationResult`：逐月推演
- `SimulationResult`：
  - `status`：`PayoffStatus.PAID_OFF` 或 `PayoffStatus.NEVER_PAID_OFF`
  - `months`：结清月序号（第 1 月起计；永不结清时为 `None`）
  - `total_interest_cents` / `total_paid_cents`：累计利息 / 累计付款
    （永不结清时为 `None`）
- 已结清方案满足：累计付款 = 初始本金之和 + 累计利息
- 非法输入（非正本金/最低月供、负利率/额外月供、空方案）抛出 `ValueError`

## 运行测试

```bash
python3 -m unittest discover -s tests -v
```

测试包含独立编写的逐月核算参考实现，与库输出逐案对照，覆盖：
半分向上舍入、同月连续结清多笔、最低月供不足以覆盖利息（暂时负摊销）、
月供恰好只够利息导致的永不结清、两种策略优先级差异及并列时的输入顺序。
