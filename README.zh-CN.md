# money-copilot-to-monarch

[English](README.md) · **简体中文**

一个 [agent skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)，
用于把 Copilot Money、Mint 或 Credit Karma 的理财历史迁移到
[Monarch Money](https://www.monarchmoney.com/)。活由你的编程 agent 干，
你只需要回答那几个只有你能回答的问题。

换记账软件本质上是个数据问题，而你能导出的只是其中一半。这里覆盖两半。

## 最容易踩空的一点

**在 Monarch 里，交易和余额是两条独立的通道。** 交易驱动分类和预算；**余额驱动净资产** ——
而余额来自账户连接，不来自交易。新连上的账户只上报当天余额、不上报历史，所以净资产曲线
在连接日之前是一条 $0 的直线，导入十年交易也不会让它往前长一寸。

也别指望从今天的余额倒推回去：只要缺一笔交易，之前所有时点都会整体偏移那么多，误差层层累积。
我们用这个办法重建过一个支票账户，结果 **16% 的日子是负余额** —— 而那个账户从没透支过一次。

Monarch 为此提供了单独的余额历史导入。喂给它的数据得从对账单 PDF 里提取期末余额，
这正是 `extract_balances.py` 干的事。

## 包含什么

```
SKILL.md                          迁移流程与其中的坑
references/monarch-formats.md     Monarch 两个导入器、冲突模式、分类行为
references/source-exports.md      Copilot 与 Credit Karma 的导出字段和怪癖
references/statement-layouts.md   各机构的对账单版式，以及如何新增一种
scripts/convert_transactions.py   配置驱动的 源 → Monarch 交易 CSV 转换
scripts/extract_balances.py       对账单 PDF → 余额历史，自带核对
scripts/audit_transactions.py     导入前的结构性检查
scripts/make_plan.py              转换产物 → 一份可勾选的执行清单
```

## 安装

克隆到你的 agent 的 skills 目录 —— Claude Code 是这个位置：

```bash
git clone https://github.com/zxhderifish/money-copilot-to-monarch.git ~/.claude/skills/money-copilot-to-monarch
```

脚本依赖 `pdfplumber`：

```bash
python -m venv .venv && .venv/bin/pip install pdfplumber
```

## 用法

直接说你要干什么，剩下的交给 agent：

> *「我从 Copilot 导出了交易记录，帮我搬进 Monarch。」*
>
> *「我 Monarch 的净资产曲线在 8 月之前是空的，能补吗？」*
>
> *「我攒了五年的 Schwab 和 Fidelity 对账单，都在一个文件夹里。」*

它会读你的导出文件，算出你的账户和分类该怎么对应到 Monarch 里已有的那些，
然后问你那些它确实推不出来的事 —— 哪份数据是你真正 review 过的、
两个名字相近的账户是不是同一个。**这会是一段对话而不是一条命令**，
因为沿途的判断都是你的：Monarch 的导入不可撤销。

产出是一批 CSV 和一份执行清单，告诉你先建什么、按什么顺序上传。**不会替你上传任何东西。**

### 直接跑脚本

平时由 agent 调用，但它们也能独立运行。

提取余额，可以直接扫整棵对账单目录树：

```bash
python scripts/extract_balances.py ~/statements out/ --recursive
```

```
out/1234.csv  84 periods  2019-08-27 .. 2026-07-28
...
311 statements, 311 parsed, 314 checks, 0 failures
```

转换交易：

```bash
python scripts/convert_transactions.py --example > config.json   # 改完配置再跑
python scripts/convert_transactions.py config.json
python scripts/audit_transactions.py monarch_import --source transactions.csv --format copilot
```

再生成执行清单：

```bash
python scripts/make_plan.py --transactions monarch_import/ --balances out/ \
                            --monarch-export Transactions.csv --out PLAN.md
```

## 为什么每一步都要核对

对账单天生是要平账的，这正是提取可信的根据：期初 + 收入 − 支出 = 期末；股数 × 价格 = 市值；
各账户之和 = 组合总值；本期期初 = 上期期末。**一个能复现出文档自己声明的合计的数字，
其可信度和一次孤立的正则匹配完全不是一回事。**

这里每种版式都声明了这样一条等式，每次运行都会报告有多少份通过。核对失败时，
先去读对账单再去改解析器 —— 实际经验里，**错的是核对本身的概率，和错的是数据的概率差不多**。

## 对账单覆盖

已用 311 份真实对账单验证：**311 份全部解析，314 项核对，零失败。**

| 机构 | 对账单类型 |
|---|---|
| Bank of America | 支票账户 |
| Charles Schwab | 银行（Investor Checking）、券商、股权激励（Equity Awards） |
| Fidelity | 家庭合并、单账户、年终报告、HSA |
| Vanguard | Personal Investor（IRA、券商）、退休计划（401k） |

机构每隔几年就会改版对账单，所以一个账户五年的历史通常跨好几种版式 ——
光 Schwab 的券商对账单就有四种。新增一种版式只需要一个短函数加一条识别正则，
见 `references/statement-layouts.md`。**匹配不上任何版式的文件会在每次运行结束时列出来** ——
因为一个默默跳过的解析器，看起来和成功的一模一样。

## 关于和「钱的主人」协作

`SKILL.md` 里专门有一节讲这个，因为迁移就是在这里出岔子的。你读数据比对方快得多，
但几乎每个真正要紧的问题都只有对方能回答 —— 哪份导出是他们真正 review 过的、
两个名字相近的账户是不是同一个、2021 年那会儿刷的是哪张卡。
与此同时，没人想被问「零金额的行要不要丢掉」。

所以：**该问的问，其余自己定，永远不要卡住等答案**，并且把推论标成推论、附上依据 ——
因为总有些推论是错的，而对方只有看得见你的结论和理由，才可能纠正你。

## 适用范围与注意事项

- Monarch 的导入**不可撤销**。整个流程就是围着这一点设计的：一个账户一个文件、
  从最小的开始、确认无误再往下。
- 这里的代码**不连任何 API、不上传任何东西**。它读你已有的文件，写出由你自己上传的 CSV。
- 格式细节反映的是这些产品在 2026 年的状态。如果哪里对不上，
  拿 `references/monarch-formats.md` 和 Monarch 当前的帮助文档核一下。

## 许可

MIT
