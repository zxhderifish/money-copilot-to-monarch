# Source export schemas and their quirks

## Copilot Money

Settings → Account → export transactions. **Transactions only** — Copilot has no balance or
net-worth export, so the balance side of the migration must come from statements.

```
date, name, amount, status, category, parent category, excluded, tags, type, account, account mask, note, recurring
```

| Field | Notes |
|---|---|
| `amount` | **Expenses positive**, income negative — inverted from Monarch |
| `type` | `regular` / `income` / `internal transfer`. Income and transfer rows usually carry an empty `category`, so category alone loses ~40% of rows |
| `category` / `parent category` | Two-level, but the parent is optional and often blank; Monarch takes a single category |
| `excluded` | Frequently set per *category* rather than per transaction — check whether every row in a category shares the flag before treating it as a per-row decision |
| `account` + `account mask` | Neither is unique alone. See SKILL.md |
| `recurring` | Holds the stream's *name*, not a boolean. Most repeat the merchant name; the useful minority identify an opaque charge (`CSP Fee` on a line reading "Annual Membership Fee") |
| `status` | `posted` / `pending`. Pending rows will be re-fetched by the bank feed after import — dropping them avoids duplicates |

### Things worth checking in a Copilot export

- **Zero-amount rows.** $0.00 interest postings and abandoned pending charges add noise.
- **Both legs of a transfer, unlinked.** No pairing ID, and the legs often post on different
  dates. Both legs land in Monarch's Transfers group, which is excluded from budgets, so
  importing both is correct and does not double-count.
- **Mojibake in account names.** Literal U+FFFD replacement characters and non-breaking spaces
  appear in display names; the last-4 sometimes gets appended to the name as well.
- **Generic merchant names.** Copilot may label a rewards deposit `Check` or a savings
  transfer `Deposit`. Cross-reference the same stream in another account or in statements
  before assuming the name means what it says.
- **Genuine duplicates.** Same date, merchant, amount and account repeated several times is
  usually real (gift-card reloads, repeated small orders). Confirm before de-duplicating.

## Mint / Credit Karma

Credit Karma inherited Mint's data and export format. Common in US migrations because Mint's
shutdown pushed people through Credit Karma.

```
Date, Description, Original Description, Amount, Transaction Type, Category, Account Name, Labels, Notes
```

| Field | Notes |
|---|---|
| `Amount` | Unsigned magnitude; direction comes from `Transaction Type` (`debit` / `credit`) |
| `Description` | Cleaned name — often too clean. `Google` here can be a game purchase or cloud storage |
| `Original Description` | The raw statement text. **Match categorization rules against this** |
| `Category` | Mint's taxonomy, including group headings with no Monarch equivalent |
| `Account Name` | Display name with no mask, e.g. a bare `CREDIT CARD` covering several cards |

### Mint category headings that need resolving per merchant

`Auto & transport`, `Bills & utilities`, `Business services`, `Gifts & donations`. Importing
these verbatim builds a shadow taxonomy beside Monarch's real categories.

Direct renames that are safe:

| Mint | Monarch |
|---|---|
| `Fees & charges` | `Financial Fees` |
| `Mortgage & rent` | `Rent` |
| `Cash & checks` | `Cash & ATM` |
| `Food & dining` | `Restaurants & Bars` |
| `Entertainment` | `Entertainment & Recreation` |
| `Travel & vacation` | `Travel & Vacation` |
| `Home & garden` | `Home Improvement` |
| `Investments` | `Transfer` (contributions and brokerage funding are money moved, not spent) |

### Attributing a merged account

When one Mint account name covers several real cards, the overlap period with a better-masked
source can identify some rows by merchant profile — which card a merchant appears on elsewhere.
Restrict the profile to cards that **existed at the time**; a card opened in 2023 cannot explain
a 2021 charge, and including it skews the comparison.

Expect this to resolve a minority of rows. When it does not, a clearly-labeled account
(`Chase (2021-2022)`) beats inventing an attribution. Card-level accuracy on closed historical
accounts is low-value anyway — categories drive the reports.

Card-issuer facts that help: annual fees identify a specific product (only one Chase
Ultimate Rewards card carries a $95 fee), and a rewards app's card list gives real open dates.

## Statement PDFs as a source of truth

Statements outrank both exports when they disagree, and they answer questions transactions
cannot. Beyond balances they carry per-transaction reward amounts, running balances, and the
institution's own name for a merchant.

They also settle identity questions cheaply: a fund ticker in a statement names the custodian
(SPAXX is Fidelity, a Schwab sweep is Schwab), which is more reliable than inferring an
institution from an account nickname.
