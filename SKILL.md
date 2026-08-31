---
name: money-copilot-to-monarch
description: Migrate personal finance history into Monarch Money from Copilot Money, Mint, or Credit Karma — converting transaction exports to Monarch's CSV format, mapping accounts and categories onto what Monarch already has, and rebuilding net worth history by extracting balances from brokerage and bank statement PDFs. Use this whenever someone mentions moving between budgeting or personal-finance apps, importing transactions or balances into Monarch, a net worth chart that is flat or empty before a certain date, reconciling a financial CSV export, or pulling account balances out of statement PDFs — including when they only describe the symptom ("my history didn't come over", "Monarch shows zero before August") rather than naming the migration.
---

# Migrating financial history into Monarch

Someone leaving Copilot, Mint, or Credit Karma wants their history to survive the move. The
export they have is transactions. What they usually mean by "my history" is both their
categorized spending *and* their net worth curve — and those travel through two different
doors.

## The one thing that surprises everyone

**Transactions and balances are separate channels in Monarch.**

- Transactions drive categories, budgets, cash flow.
- **Balances drive net worth**, and they come from the account connection, not from transactions.

A newly connected account reports today's balance and nothing before it. So the net worth
chart reads $0 until the day the account was linked, and importing years of transactions does
not change that. Monarch has a separate balance-history importer for this, fed from statements.

**You cannot derive balances by running transactions backward from today's balance.** It looks
like it should work and it does not: any missing transaction shifts every earlier point by that
amount, and the errors compound. In one real migration, reconstructing a checking account this
way put 16% of days at a negative balance — an account whose statements showed it had never
once been overdrawn. Reconstruction was accurate only for the period where the transaction
feed happened to be complete. You cannot know in advance which
period that is, which is exactly why the method is unusable.

Tell the user this early. It reframes the job from "convert one CSV" to "convert one CSV
**and** harvest statements", and the second half is usually the larger effort.

## Order of work

1. **Export from Monarch first.** Even a nearly-empty account. The export names every account
   and category exactly as Monarch spells them, which is what the importer matches on. Guessing
   these names is the most common way to end up with duplicate accounts.
2. Inventory accounts on both sides and build the mapping.
3. Convert transactions and verify.
4. Import transactions, smallest file first.
5. Harvest balance history from statements, verify, import.

## Account identity: the key is name + last-4, never either alone

Aggregators collapse several cards under one display name. In one real export, `Platinum Card®`
covered two Amex cards and `Ultimate Rewards®` covered three Chase cards — 1,643 transactions
that would have been merged into two accounts. Meanwhile Amex reuses the same last-4 across
different products, so the mask alone is not unique either.

Monarch names accounts `Display Name (...1234)`. Match source accounts to Monarch accounts by
last-4 and confirm the count lines up:

```
Copilot "Ultimate Rewards®" 5678  →  Monarch "CREDIT CARD (...5678)"
```

If the overlap counts match Monarch's existing counts almost exactly, the mapping is right.
That agreement is a stronger signal than name similarity.

### An export only proves presence, never absence

A transactions export lists accounts that *have transactions*. An account with a zero balance
and no activity is invisible in it. Concluding "this account isn't in Monarch" from a
transactions export is wrong, and it is easy to do twice in one session. Ask for the account
list from the accounts page instead.

## Sign conventions differ, and getting this backwards inverts everything

| Source | Expense | Income |
|---|---|---|
| **Copilot** | positive | negative |
| **Mint / Credit Karma** | unsigned magnitude + a `Transaction Type` column (`debit`/`credit`) | same |
| **Monarch** | **negative** | **positive** |

## Categories: the user's own review is the reference, not the app's guesses

An aggregator's auto-categorization is often bad in ways that survive migration. Mint filed 38
Amazon purchases under "Home & garden", and put a Korean game studio under "Donations".

If the user reviewed one source regularly, that source's merchant→category pairs are the
authority. Build a lookup from it and use it to override the other source. Ask which data they
actually curated — do not assume the newer export is the better one.

Two failure modes worth naming:

**Shadow taxonomies.** Mint's group headings (`Auto & transport`, `Bills & utilities`,
`Business services`, `Fees & charges`) are not Monarch categories. Importing them verbatim
creates a second, parallel set sitting next to Monarch's real ones — `Fees & charges` beside
`Financial Fees`, both collecting transactions. Resolve group headings per merchant into real
categories instead.

**Reading the wrong column.** Credit Karma has both `Description` and `Original Description`.
Rows showing plain `Google` are `GOOGLE *Honkai Star Ra` (a game) or `GOOGLE *Google Photos`
(storage) underneath. Match rules against the most detailed column available.

## Import mechanics

Monarch offers **Prioritize CSV** (delete existing transactions inside the file's date range and
replace), **Prioritize Monarch** (only fill gaps), and **Import all** (duplicates likely).

The deletion window is the span of *the file you upload*, applied per account. One combined file
spanning 2018–2026 therefore clears that whole range for every account it touches — including
periods your data doesn't actually cover. **Splitting per account scopes the blast radius to
each account's own dates.**

Imports cannot be undone. Upload the smallest file first and check three things before
continuing: amounts point the right way, categories resolved (not all "Uncategorized"), dates
land in the expected range.

Leave an account out of the CSV entirely when Monarch's data for it is richer — importing four
cash transfers over an investment account's real trade history is a net loss.

## Harvesting balance history

`scripts/extract_balances.py` handles the statement side. Read
`references/statement-layouts.md` for the layouts it ships with and how to add one.

Two things govern this work.

**Verify every figure against arithmetic the document itself states.** Statements are built to
reconcile: beginning + credits − debits = ending; shares × price = value; per-account values sum
to the portfolio total; one period's opening balance equals the previous period's close. An
extraction that reproduces a stated total is trustworthy in a way that a lone regex match never
is. Report the check count, not just the row count — "84 statements, 84 reconciled, 83 chain
links intact" is a claim someone can act on.

When a check fails, read the statement before touching the parser. Two real examples: a
"mismatch" was the parser ignoring a cash line the stated total legitimately included, and ten
"chain breaks" were the comparison column being prior-year-end on annual statements rather than
prior-month. Both times the data was fine and the check was wrong.

**Expect layout drift.** Institutions rework statements every few years, so a five-year run
holds two to four layouts. Schwab's brokerage statement has three; Fidelity's has three plus a
combined multi-account variant; Vanguard switched from full account numbers to masked ones in
2024. Make the extractor print every file it could not parse rather than silently skipping —
a quiet skip looks identical to success.

**Combined statements** cover a whole household in one PDF, keyed by account number. Split them
by the last four digits, and verify the per-account values sum to the stated portfolio total.

### Where the effort is worth spending

Sort accounts by share of net worth before harvesting. Investment accounts usually dominate —
when brokerages hold the overwhelming majority of net worth, perfecting a checking account's
curve barely moves the chart. Statements also tend to be quarterly for retirement plans
and monthly for banks; quarterly points are plenty for a multi-year chart.

## Working with the user

Migration is a long collaboration, and the split of labour is unusual: you can read the data
far faster, but almost every question that actually matters is one only they can answer. Getting
that split right is most of what makes this go well.

### Ask — no amount of analysis substitutes

- **Which export did you actually review?** This decides which source becomes the category
  reference. Do not assume the newer or larger one; assume nothing. In one migration the app's
  own history looked authoritative and was machine-categorised and unchecked, while the older
  export had been reviewed weekly by hand.
- **Is this account the same as that one?** Two accounts can share a name and be different
  (an HSA at one provider, and its successor after the money moved), or differ in name and be
  the same. Balances, masks and date ranges narrow it; only the user settles it.
- **Which card was this, in that year?** When merchant profiling is inconclusive, say so and
  ask. They will often remember.
- **Overwrite the existing data, or only fill gaps?** Changes which import mode to use, and it
  is irreversible.
- **Does this account's balance belong in net worth?** Especially for spending funded from
  somewhere untracked.
- **Should closed accounts be recreated to hold their history?**

### Decide yourself — asking is noise

Whether to drop zero-amount rows, what to name output files, which regex to write, whether to
verify an extraction. Nobody wants to be consulted on these, and consulting on them buries the
questions that matter.

### Never block on a question

Do everything that does not depend on the answer, and keep the open questions listed at the end
of each turn. Users answer out of order, skip some, and come back to others three exchanges
later — that is fine and normal, but only if the list stays visible and the work keeps moving.
Re-asking the same question while doing nothing else is the failure mode to avoid.

Offering the list unprompted works well: "here is what I am still unsure about" surfaces
corrections early, while they are cheap.

### State inferences as inferences, with their evidence

You will infer which institution an account belongs to, which card a charge went on, what a
generic merchant name means. Some of these will be wrong, and the user can only catch them if
they can see what you concluded and why. "The paired leg reads *Goldman Sachs Ba P2p* on the
other side, so this is Marcus rather than the bank savings" invites a correction in a way that
"this is Marcus" does not.

Two specific inference traps, both of which produce a confident wrong answer:

- **An export proves presence, never absence.** An account with no transactions is invisible in
  a transactions export. Ask for the account list.
- **A holding is not a custodian.** A Vanguard fund sitting in a Schwab account does not make it
  a Vanguard account. Read the sweep or core position instead.

### When they push back, re-derive rather than defend

"Are you sure?" and "I think something is still off" are usually right. In one session each such
challenge surfaced a real defect: a category mapping that had quietly built a shadow taxonomy, a
tag that duplicated what its category already said, an extractor that had over-matched. Go back
to the data rather than restating the earlier conclusion.

## Reporting findings

Migration work is forensic, and the user knows their finances far better than the data does.
Surfacing what you find is part of the job, not a digression: an international wire traced from
a checking account through a high-yield savings parking spot into a brokerage; an annual IRA
contribution that zeroes out the same month, revealing a backdoor Roth; two employer
reimbursements the user had missed tagging.

State what the data shows, with the evidence, and let them confirm. Several times per migration
they will correct an inference you were confident about — which institution an account belongs
to, which card was used in 2021 — and those corrections are worth more than the inference was.

## Bundled resources

- `references/monarch-formats.md` — exact CSV columns for both importers, import modes, limits
- `references/source-exports.md` — Copilot and Credit Karma export schemas and their quirks
- `references/statement-layouts.md` — statement layouts per institution, and how to add one
- `scripts/convert_transactions.py` — config-driven source → Monarch transaction converter
- `scripts/extract_balances.py` — statement PDF → balance history, with reconciliation checks
- `scripts/audit_transactions.py` — post-conversion checks to run before importing
- `scripts/make_plan.py` — turns the converted output into a checklist: accounts and categories
  to create first, then the import order, smallest file first
