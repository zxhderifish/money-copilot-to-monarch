# Statement layouts

`scripts/extract_balances.py` ships with the layouts below. Each declares how to
recognise a statement, where its period-end balance is, and — the part that makes the
result trustworthy — an identity the statement states about itself.

Validated against 311 real statements across six institutions: all 311 parsed, 314
reconciliation checks, zero failures.

| Layout | Statement | Balance | Self-check |
|---|---|---|---|
| `bofa-checking` | BofA checking eStmt | `Ending balance on <date>` | beginning + deposits − withdrawals − checks − fees |
| `schwab-bank` | Schwab Bank Investor Checking | `Ending Balance` | beginning + credits + interest − debits |
| `schwab-equity-awards` | Schwab stock plan | `Total:` | shares × price per holding, plus cash, = total |
| `schwab-brokerage` | Schwab One brokerage | `EndingValue` / `EndingAccountValue` | beginning + deposits − withdrawals + income + market − fees |
| `fidelity-combined` | Fidelity household report | Portfolio Summary rows | per-account values sum to `Ending Portfolio Value` |
| `fidelity-solo` | Fidelity single account | `Ending Account Value` | beginning + additions − subtractions + change |
| `vanguard-personal` | Vanguard IRA / brokerage | `Account overview` | per-account values sum to `Statement overview` |
| `vanguard-401k` | Vanguard retirement plan | `Ending balance` | beginning + contributions + employer + market + other − fees; plus cover figure vs detail table |

## Layout drift within one issuer

A five-year run of one account usually spans several formats. The extractor absorbs
these as alternates inside a single layout rather than as separate layouts, because
they identify the same account and reconcile the same way.

**Schwab brokerage — four eras.** 2022 uses `Starting AccountValue` /
`ChangeinValueofInvestments`. Mid-2023 uses `EndingAccountValue` with a three-column
This/Previous/Change table and `MarketValueChange` / `Fees`. Late 2023–2025 uses
`EndingValue` with `MarketAppreciation/(Depreciation)` / `Expenses`. 2026 returns to
`EndingAccountValue`. A sidebar column also bleeds into some line starts
(`ManageYourAccount EndingValue $12,345.67`), so these patterns cannot anchor at `^`.

**Fidelity — three.** A combined household report, a single-account monthly report, and
a year-end report that inserts `as of Jan 1, 2025` between a label and its value.
Account numbers are `Z20-908128` for brokerage but `259-338859` for HSA, so an account
pattern requiring a letter prefix silently drops the HSA.

**Vanguard Personal Investor — two.** Through 2023 sections carry the full account
number (`—51042453`); from 2024 they are masked (`—XXXX2453`).

## Pitfalls this cost real debugging time

**pdfplumber drops spaces inside labels** on some issuers — Schwab brokerage renders
`BeginningValue` and `MarketAppreciation/(Depreciation)` with no internal spaces.
Print the extracted lines before writing patterns.

**A dash means the column is empty, not zero-then-a-number.** Fidelity prints
`Additions - 2,500.00`: nothing this period, $2,500 year to date, in that order. Reading the first
number gives you the YTD figure and breaks the reconciliation.

**The comparison column is not always the prior month.** Vanguard's monthly statements
show `Value on 06/30/2026 | 07/31/2026`, but year-to-date statements show
`12/31/2022 | 12/31/2023`. Read the column header date instead of assuming.

**Accounting parentheses mean negative.** `(176.91)` is −176.91.

**Some issuers put no date inside the PDF**, only in the filename
(`Statement12312024.pdf`, `Account Statement_2024-12-31.PDF`). Others put no date in
the filename (`document (3).pdf`) and only in the text. Support both.

**One PDF can hold several statements or several accounts.** A combined report yields
one reading per account; the extractor returns a list for exactly this reason.

**Duplicate downloads happen** (`Statement12312025 (1).pdf`). Same date twice is fine
if the values agree — the extractor reports it when they do not.

## Adding a layout

1. Extract the text and read the summary block. Find the stated period-end balance and
   whatever identity the statement asserts about it.
2. Copy the closest `_read_*` function and adjust its patterns.
3. Give the `Layout` a `detect` regex specific enough not to claim another layout's
   files, and register it in `LAYOUTS` — earlier entries win.
4. Run with `--verbose` to confirm which layout claimed each file.

Anything unmatched is listed at the end of the run. That list is the point: a parser
that silently skips files looks exactly like one that worked.
