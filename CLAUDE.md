# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A Claude Skill, not an application. `SKILL.md` is the product — it is what gets loaded into
context and it carries the judgment: what the traps are, when to ask the user, what order to do
things in. The scripts under `scripts/` are bundled resources the skill reaches for.

That inverts the usual priority. A change to `SKILL.md` alters behavior far more than a change
to any script, so review it with the same care you would give code.

## No build, no test suite

There is nothing to compile and no tests to run, because the only meaningful validation is
running a script against real statements — which are financial records and cannot live in this
repo. `.gitignore` blocks `*.csv`, `*.pdf` and `config.json` for that reason; keep it that way.

Validation therefore means: point a script at a folder of real statements and read the counts it
prints.

```bash
python -m venv .venv && .venv/bin/pip install pdfplumber   # the only dependency

.venv/bin/python scripts/extract_balances.py ~/statements out/ --recursive --verbose
```

A run that says `311 statements, 311 parsed, 314 checks, 0 failures` is a pass. A run that
parses everything but performs zero checks is not — see below.

## The design invariant: every layout reconciles

`extract_balances.py` is the heart of this repo, and the thing that makes it trustworthy is that
no figure is taken on the strength of a regex alone. Statements are built to balance, and each
layout must reproduce one of those identities:

- beginning + credits − debits = ending
- shares × price = value
- per-account values sum to the stated portfolio total
- one period's opening balance = the previous period's close

A layout that extracts a number without checking it against something the document itself states
is a defect, not a shortcut. If you add one and cannot find an identity to check, say so
explicitly rather than letting it pass silently.

The corollary matters just as much: **when a check fails, read the statement before changing the
parser.** In practice the check is wrong about as often as the data is — a "mismatch" turned out
to be a cash line the total legitimately included, and a run of "chain breaks" turned out to be a
comparison column that meant prior-year-end rather than prior-month.

## Adding a statement layout

This is the main way the repo grows. Institutions rework their statements every few years, so
one account's five-year history usually spans several layouts.

A `Layout` is three things:

```python
Layout(name, detect, read)
```

- `detect` — a regex specific enough to this issuer *and* era that it will not claim another
  layout's files. `LAYOUTS` is tried in order.
- `read(lines, filename) -> Reading | list[Reading] | None` — returns `None` if the layout turns
  out not to handle the file (the loop then tries the next one), a list when one PDF covers
  several accounts, and calls `_reconcile()` to attach the check.

Statement dates often come from the filename rather than the text; `_date_from_filename` handles
the common spellings. `money()` treats accounting parentheses as negative and a bare dash as an
empty column — that last one matters, because a dash followed by a number means "nothing this
period, and here is the year-to-date figure", and reading the number breaks the reconciliation.

Unparsed files are listed at the end of every run rather than skipped, because a parser that
silently drops a file looks exactly like one that worked.

## The other scripts

- `convert_transactions.py` — config-driven. `--example` prints a starter config; the shape is
  documented in the module docstring. The account map is keyed `"Display Name|mask"` because
  neither part is unique on its own: aggregators collapse several cards under one display name,
  and issuers reuse the last four digits across products.
- `audit_transactions.py` — structural checks plus a row-for-row comparison against the source,
  meant to run before any import.
- `make_plan.py` — turns converted output into a checklist. Comparing against a Monarch export is
  what makes its "create these first" lists real; without one it can only list files.

## Docs to keep in step

- `README.md` and `README.zh-CN.md` are a matched pair, cross-linked at the top. A change to one
  needs the same change in the other.
- `references/` is loaded by the skill on demand: `monarch-formats.md` (Monarch's two importers),
  `source-exports.md` (Copilot and Credit Karma schemas), `statement-layouts.md` (per-institution
  layouts). When you add a layout to the script, describe it there too — the reference is what a
  human reads when a new statement will not parse.
