# Monarch import formats

Two importers, reached from different places, taking different files.

## Transactions

**Where:** Accounts → **+ Add Account** → upload CSV (web only; the mobile apps cannot import).
Uploading from a single account's Edit menu also works, but then the `Account` column is ignored
and everything lands in that one account — wrong for a multi-account migration.

**Columns** — the importer matches on header keywords, so order does not matter and extra
columns are ignored:

```
Date, Merchant, Category, Account, Original Statement, Notes, Amount, Tags
```

| Column | Required | Notes |
|---|---|---|
| `Date` | yes | US formats accepted; `YYYY-MM-DD` also works and is what Monarch's own export emits |
| `Merchant` | yes | |
| `Amount` | yes | **Expenses negative**, income positive, no currency symbol |
| `Account` | no | Must match the Monarch account name exactly, including the ` (...1234)` suffix. Optional only when uploading into one specific account |
| `Category` | no | |
| `Original Statement` | no | Raw bank text. Useful once merchant names are cleaned — it preserves what was actually imported |
| `Notes` | no | |
| `Tags` | no | |

**Conflict modes**, offered when the target account already holds transactions:

| Mode | Behavior |
|---|---|
| **Prioritize CSV** | Deletes existing transactions inside the uploaded file's date range, then inserts the file |
| **Prioritize Monarch** | Keeps existing data, adds only what is missing |
| **Import all** | Inserts everything; duplicates likely |
| **Use transaction IDs** | Updates existing rows by ID; only for files exported from Monarch |

The deletion window comes from the file, which is why per-account files matter — see SKILL.md.

**Scale:** Monarch flags accounts over ~5,000 transactions as needing care and suggests
splitting by account, then by date range if an upload still errors.

**Irreversible.** Undoing means bulk-deleting transactions or deleting the account.

## Balance history

**Where:** the account's own page → Edit → import balance history. One file per account,
assigned to its account during the import.

**Columns:**

```
Date, Balance
```

No account column — the assignment happens in the UI. Duplicate dates are rejected.

This is the only way to give a connected account a net worth curve that predates its
connection date.

## Category and account behavior on import

- Category names are matched against existing categories; Monarch's own categories carry emoji
  icons in the import preview, which is a quick way to spot a name that will create a new
  custom category instead of matching an existing one.
- Monarch's default categories include `Rent`, `Mortgage`, `Gas`, `Public Transit`,
  `Parking & Tolls`, `Taxi & Ride Shares`, `Gas & Electric`, `Internet & Cable`, `Phone`,
  `Groceries`, `Restaurants & Bars`, `Coffee Shops`, `Travel & Vacation`,
  `Entertainment & Recreation`, `Shopping`, `Clothing`, `Electronics`, `Medical`, `Education`,
  `Taxes`, `Financial Fees`, `Charity`, `Gifts`, `Child Activities`, `Paychecks`, `Interest`,
  `Other Income`, `Cashback`, `Uncategorized`, plus the transfer group below.
- **Transfers group:** `Transfer`, `Credit Card Payment`, and (with investments on) `Buy`,
  `Sell`, `Dividends & Capital Gains`. These are excluded from budgets and cash flow, so both
  legs of a transfer can be imported without double-counting. Pairing the legs is not required.

## Two kinds of "exclude"

Users migrating from an app with an exclude flag usually mean the first of these:

| | Level | Effect |
|---|---|---|
| **Exclude from budget** | category | Leaves budget planning only; transactions still appear in cash flow and reports |
| **Hide transaction** | transaction | Removed from lists, reports and budgets; balances and net worth unaffected |

Neither is a CSV column. A source app's per-transaction exclude flag has no direct equivalent —
reproduce it as a category setting after import. Check first whether the flag was actually set
per category in the source app, because then the category-level setting reproduces it exactly
and a per-transaction tag would only restate what the category already says.

## Accounts that hold spending but no tracked balance

For an account used to record spending funded from somewhere untracked (a foreign account, cash),
the transactions are real but the running balance is meaningless. Type it **Cash** rather than
Credit Card — a credit card accumulates a liability that is never paid off — and enable **hide
balance from net worth** while leaving transactions visible to budgets.
