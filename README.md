# money-copilot-to-monarch

**English** · [简体中文](README.zh-CN.md)

An [agent skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) for
migrating personal finance history into [Monarch Money](https://www.monarchmoney.com/) from
Copilot Money, Mint, or Credit Karma. Your coding agent does the work; you answer the handful of
questions only you can answer.

Moving between budgeting apps is mostly a data problem, and the export you get is only half
the data. This covers both halves.

## The part that surprises everyone

**Transactions and balances are separate channels in Monarch.** Transactions drive categories
and budgets. *Balances* drive net worth — and they come from the account connection, not from
transactions. A newly linked account reports today's balance and nothing before it, so the net
worth chart reads $0 until the day you connected, and importing ten years of transactions does
not change that.

Nor can you work balances backward from today's figure: any missing transaction shifts every
earlier point by that amount and the errors compound. Reconstructing one checking account this
way put 16% of days at a negative balance — an account that had never once been overdrawn.

Monarch has a separate balance-history importer for exactly this. Feeding it means extracting
period-end balances from statement PDFs, which is what `extract_balances.py` does.

## What's here

```
SKILL.md                          the migration workflow and its traps
references/monarch-formats.md     Monarch's two importers, conflict modes, category behavior
references/source-exports.md      Copilot and Credit Karma export schemas and quirks
references/statement-layouts.md   statement layouts per institution, and how to add one
scripts/convert_transactions.py   config-driven source → Monarch transaction CSVs
scripts/extract_balances.py       statement PDFs → balance history, with reconciliation checks
scripts/audit_transactions.py     pre-import structural checks
scripts/make_plan.py              converted output → a checklist you work through
```

## Install

Clone into your agent's skills directory — for Claude Code that is:

```bash
git clone https://github.com/zxhderifish/money-copilot-to-monarch.git ~/.claude/skills/money-copilot-to-monarch
```

The scripts need `pdfplumber`:

```bash
python -m venv .venv && .venv/bin/pip install pdfplumber
```

## Usage

Describe what you are doing and the agent takes it from there:

> *"I exported my transactions out of Copilot — help me get them into Monarch."*
>
> *"My Monarch net worth chart is empty before August. Can we fix that?"*
>
> *"I have five years of Schwab and Fidelity statements sitting in a folder."*

It will read your exports, work out how your accounts and categories map onto the ones Monarch
already has, and ask you the things it genuinely cannot infer — which export you actually
reviewed, whether two similarly-named accounts are the same account. Expect a conversation
rather than a single command, because the decisions along the way are yours: imports into
Monarch cannot be undone.

What comes out is a set of CSVs and a checklist telling you what to create first and what order
to upload in. Nothing is uploaded for you.

### Running the scripts directly

The agent drives these, but they work standalone.

Balances, across a whole folder tree of statements:

```bash
python scripts/extract_balances.py ~/statements out/ --recursive
```

```
out/1234.csv  84 periods  2019-08-27 .. 2026-07-28
...
311 statements, 311 parsed, 314 checks, 0 failures
```

Transactions:

```bash
python scripts/convert_transactions.py --example > config.json   # edit, then
python scripts/convert_transactions.py config.json
python scripts/audit_transactions.py monarch_import --source transactions.csv --format copilot
```

Then the checklist:

```bash
python scripts/make_plan.py --transactions monarch_import/ --balances out/ \
                            --monarch-export Transactions.csv --out PLAN.md
```

## Why it reconciles everything

Statements are built to balance, and that is what makes extraction trustworthy: beginning +
credits − debits = ending; shares × price = value; per-account values sum to the portfolio
total; one period's opening balance is the previous period's close. A figure that reproduces a
total the document itself states is verified in a way a lone regex match never is.

Every layout here declares such an identity, and each run reports how many statements passed
it. When a check fails, read the statement before touching the parser — in practice the check
is wrong about as often as the data is.

## Statement coverage

Validated against 311 real statements: **all 311 parsed, 314 reconciliation checks, zero
failures.**

| Institution | Statement |
|---|---|
| Bank of America | Checking |
| Charles Schwab | Bank (Investor Checking), brokerage, stock plan / equity awards |
| Fidelity | Combined household, single account, year-end, HSA |
| Vanguard | Personal Investor (IRA, brokerage), retirement plan (401k) |

Institutions rework their statements every few years, so a five-year run of one account
typically spans several layouts — Schwab's brokerage statement alone has four. Adding a layout
is a short function plus a detect pattern; see `references/statement-layouts.md`. Files matching
no layout are listed at the end of every run, because a parser that silently skips looks exactly
like one that worked.

## On working with the person whose money this is

`SKILL.md` spends a section on this because it is where migrations go wrong. You can read the
data faster than they can, but nearly every question that matters is one only they can answer —
which export they actually reviewed, whether two similarly-named accounts are the same account,
which card they were using in 2021. Meanwhile nobody wants to be asked whether to drop
zero-amount rows.

So: ask the few things that need them, decide the rest, never block, and state inferences as
inferences with the evidence attached — because some will be wrong, and that is only catchable
if they can see what you concluded and why.

## Scope and caveats

- Monarch's import is **irreversible**. The skill's workflow is built around that: one file per
  account, smallest first, verify before continuing.
- Nothing here talks to any API or uploads anything. It reads files you already have and writes
  CSVs you upload yourself.
- Format details reflect what these apps did as of 2026. Check `references/monarch-formats.md`
  against Monarch's current help pages if something looks off.

## License

MIT
