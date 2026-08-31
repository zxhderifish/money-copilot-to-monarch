#!/usr/bin/env python3
"""Convert a Copilot or Credit Karma transaction export into Monarch CSVs.

Driven by a JSON config so the parts that differ per person -- which source
account maps to which Monarch account, which categories to rename -- live in data
rather than in edits to this file. Writes one CSV per account, because Monarch's
"Prioritize CSV" mode deletes across the uploaded file's whole date span.

Usage:
    python convert_transactions.py CONFIG.json
    python convert_transactions.py --example > config.json    # commented starter

The config:

{
  "source": "copilot" | "creditkarma",
  "input": "transactions.csv",
  "output_dir": "monarch_import",

  "accounts": {"Ultimate Rewards®|5678": "CREDIT CARD (...5678)"},
  "skip_accounts": ["Brokerage|9012"],
  "cutoffs": {"Adv Plus Banking - 1234": "2023-02-01"},

  "categories": {"Restaurants": "Restaurants & Bars"},
  "merchant_rules": [["costco gas|exxon", "Gas"]],
  "merchant_renames": [["^check$", "Daily Cash Deposit"]],
  "reference": {"csv": "curated.csv", "source": "copilot"},

  "drop_zero_amount": true,
  "drop_pending": true,
  "credit_card_accounts": ["CREDIT CARD (...5678)"]
}

`accounts` keys are "name|mask" for Copilot (neither is unique alone) and the bare
account name for Credit Karma. `cutoffs` drops rows on or after a date, for when a
second export covers that period better. `reference` builds merchant -> category
from an export whose categories the user actually curated; it wins over the
source's own guesses, which are often wrong in ways worth not migrating.
`credit_card_accounts` lists the Monarch names of card accounts, which lets a
transfer's two legs be told apart -- see pair_card_payments.

Precedence for a category: merchant_rules, then the curated reference, then the
source's own category. Rules come first because they encode corrections made
deliberately, after looking at what the source got wrong.

Patterns in `merchant_rules` and `merchant_renames` are tried against the merchant
and the original statement text separately, so anchors like ^ and $ behave.

`merchant_renames` fixes names the source got wrong -- Copilot files Apple Daily
Cash under the merchant "Check". The original text stays in Original Statement.
"""

import argparse
import collections
import csv
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

MONARCH_COLUMNS = ["Date", "Merchant", "Category", "Account",
                   "Original Statement", "Notes", "Amount", "Tags"]

CARD_PAYMENT = re.compile(
    r"thank you|bill payment|credit crd|american express|card payment|"
    r"epay|autopay|discover.*payment|gsbank", re.I)
PAYROLL = re.compile(r"payroll|direct dep", re.I)
INTEREST = re.compile(r"^interest\b", re.I)
CASHBACK = re.compile(r"cashback|cash back|cashreward", re.I)


# --------------------------------------------------------------------------- shared

def clean_account(name):
    """Strip the corruption aggregators bake into account display names."""
    name = (name or "").replace("�", "")
    name = "".join(c for c in name if unicodedata.category(c) != "Cc")
    name = name.replace("\xa0", " ")
    name = re.sub(r"\s*\.\.\.\d{4}\s*$", "", name)   # last-4 appended to the name
    return re.sub(r"\s+", " ", name).strip()


def norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())[:12]


def slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def build_reference(path, source, category_map):
    """merchant -> category, from an export whose categories were curated by hand.

    Only merchants with a clear majority are kept; a merchant split evenly across
    categories is telling you it genuinely varies.
    """
    counts = collections.defaultdict(collections.Counter)
    for row in csv.DictReader(open(path, encoding="utf-8")):
        if source == "copilot":
            name, category = row.get("name"), row.get("category")
        else:
            name, category = row.get("Description"), row.get("Category")
        if name and category:
            counts[norm(name)][category_map.get(category, category)] += 1
    out = {}
    for merchant, counter in counts.items():
        category, hits = counter.most_common(1)[0]
        if hits >= 2 and hits / sum(counter.values()) >= 0.6:
            out[merchant] = category
    return out


# --------------------------------------------------------------------------- sources

def read_copilot(path):
    """Copilot signs expenses positive; Monarch wants them negative."""
    for row in csv.DictReader(open(path, newline="", encoding="utf-8")):
        yield {
            "date": row["date"],
            "merchant": row["name"],
            "statement": row["name"],
            "amount": -float(row["amount"]),
            "category": row["category"] or None,
            "account_key": f"{clean_account(row['account'])}|{row['account mask']}",
            "type": row["type"],
            "status": row["status"],
            "tags": row.get("tags", ""),
            "note": row.get("note", ""),
            "recurring": row.get("recurring", ""),
        }


def read_creditkarma(path):
    """Credit Karma stores an unsigned magnitude plus a direction column, and keeps
    the useful detail in Original Description rather than Description."""
    for row in csv.DictReader(open(path, newline="", encoding="utf-8")):
        amount = float(row["Amount"])
        if row["Transaction Type"] == "debit":
            amount = -amount
        merchant = row["Description"].strip() or row["Original Description"].strip()
        yield {
            "date": row["Date"],
            "merchant": merchant,
            "statement": row["Original Description"].strip() or merchant,
            "amount": amount,
            "category": row["Category"] or None,
            "account_key": row["Account Name"],
            "type": None,
            "status": "posted",
            "tags": row.get("Labels", ""),
            "note": row.get("Notes", ""),
            "recurring": "",
        }


READERS = {"copilot": read_copilot, "creditkarma": read_creditkarma}


# --------------------------------------------------------------------------- convert

def matches(pattern, row):
    """Try a pattern against the merchant and the raw statement text separately.

    Concatenating them would break anchored patterns, and ^ / $ are exactly what
    you want for the short generic names aggregators produce ("Check", "Deposit").
    """
    return bool(pattern.search(row["merchant"]) or pattern.search(row["statement"]))


PAIR_WINDOW_DAYS = 5


def pair_card_payments(rows, card_accounts):
    """Mark both legs of a credit-card payment.

    A transfer leg sitting on a card account is unambiguously a card payment. Its
    funding leg, on a checking account, looks like any other transfer -- so claim
    it only when it matches a card leg by opposite amount within a few days. The
    two legs often post on different dates, which is why this is a window and not
    an equality.

    Both categories are excluded from budgets either way, so a leg left as
    Transfer is not an error; naming it correctly just makes card-payment
    tracking work.
    """
    legs = [r for r in rows if r["type"] == "internal transfer"]
    on_card = [r for r in legs if r["account"] in card_accounts]
    for r in on_card:
        r["pair"] = "Credit Card Payment"

    unclaimed = list(on_card)
    for r in (x for x in legs if x.get("pair") is None):
        for other in unclaimed:
            if (abs(r["amount"] + other["amount"]) < 0.005
                    and abs((r["_date"] - other["_date"]).days) <= PAIR_WINDOW_DAYS):
                r["pair"] = "Credit Card Payment"
                unclaimed.remove(other)
                break


def resolve_category(row, cfg, reference, rules):
    """Order matters: an explicit rule beats a curated reference, which beats the
    source's own category, because the rules encode corrections we made knowingly."""
    for pattern, category in rules:
        if matches(pattern, row):
            return category

    known = reference.get(norm(row["merchant"]))
    if known:
        return known

    if row["category"]:
        return cfg["categories"].get(row["category"], row["category"])

    # Copilot leaves income and transfers uncategorised, but names their type.
    if row["type"] == "internal transfer":
        if row.get("pair") or matches(CARD_PAYMENT, row):
            return "Credit Card Payment"
        return "Transfer"
    if row["type"] == "income":
        if matches(PAYROLL, row):
            return "Paychecks"
        if matches(INTEREST, row):
            return "Interest"
        if matches(CASHBACK, row):
            return "Cashback"
        return "Other Income"
    return "Uncategorized"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", nargs="?")
    ap.add_argument("--example", action="store_true", help="print a starter config")
    args = ap.parse_args()

    if args.example:
        print(json.dumps({
            "source": "copilot",
            "input": "transactions.csv",
            "output_dir": "monarch_import",
            "accounts": {"Adv Plus Banking|1234": "Adv Plus Banking (...1234)"},
            "skip_accounts": [],
            "cutoffs": {},
            "categories": {"Restaurants": "Restaurants & Bars"},
            "merchant_rules": [["costco gas|exxon|sunoco", "Gas"]],
            "reference": None,
            "drop_zero_amount": True,
            "drop_pending": True,
        }, indent=2, ensure_ascii=False))
        return
    if not args.config:
        ap.error("give a config, or --example to print a starter")

    cfg = json.load(open(args.config, encoding="utf-8"))
    cfg.setdefault("categories", {})
    cfg.setdefault("skip_accounts", [])
    cfg.setdefault("cutoffs", {})

    rules = [(re.compile(p, re.I), c) for p, c in cfg.get("merchant_rules", [])]
    renames = [(re.compile(p, re.I), n) for p, n in cfg.get("merchant_renames", [])]
    reference = {}
    if cfg.get("reference"):
        reference = build_reference(cfg["reference"]["csv"],
                                    cfg["reference"].get("source", cfg["source"]),
                                    cfg["categories"])
        print(f"reference covers {len(reference)} merchants")

    kept = []
    dropped = collections.Counter()

    for row in READERS[cfg["source"]](cfg["input"]):
        key = row["account_key"]
        if key in cfg["skip_accounts"]:
            dropped["a better source covers this account"] += 1
            continue
        cutoff = cfg["cutoffs"].get(key)
        if cutoff and row["date"] >= cutoff:
            dropped["period already covered by another export"] += 1
            continue
        if cfg.get("drop_zero_amount", True) and row["amount"] == 0:
            dropped["zero amount"] += 1
            continue
        # Pending rows are re-fetched by the bank feed after import.
        if cfg.get("drop_pending", True) and row["status"] == "pending":
            dropped["still pending"] += 1
            continue
        account = cfg["accounts"].get(key)
        if account is None:
            dropped[f"unmapped account: {key}"] += 1
            continue

        row["account"] = account
        row["_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
        kept.append(row)

    pair_card_payments(kept, set(cfg.get("credit_card_accounts", [])))

    buckets = collections.defaultdict(list)
    for row in kept:
        account = row["account"]
        notes = [row["note"]] if row["note"] else []
        # Most recurring-stream names just repeat the merchant; keep the ones that
        # identify an otherwise opaque charge.
        stream, merchant = norm(row["recurring"]), norm(row["merchant"])
        if stream and not (stream.startswith(merchant[:8]) or merchant.startswith(stream[:8])):
            notes.append(f"[recurring: {row['recurring']}]")

        merchant = row["merchant"]
        for pattern, replacement in renames:
            if pattern.search(merchant):
                merchant = replacement
                break

        buckets[account].append({
            "Date": row["_date"].strftime("%Y-%m-%d"),
            "Merchant": merchant,
            "Category": resolve_category(row, cfg, reference, rules),
            "Account": account,
            "Original Statement": row["statement"],
            "Notes": " ".join(notes),
            "Amount": f"{row['amount']:.2f}",
            "Tags": ",".join(t.strip() for t in (row["tags"] or "").split(",") if t.strip()),
        })

    os.makedirs(cfg["output_dir"], exist_ok=True)
    written = 0
    print(f"\n{'account':<52}{'rows':>6}  date range")
    for account in sorted(buckets, key=lambda a: len(buckets[a])):
        rows = sorted(buckets[account], key=lambda r: r["Date"])
        path = os.path.join(cfg["output_dir"], f"{slug(account)}.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=MONARCH_COLUMNS)
            w.writeheader()
            w.writerows(rows)
        written += len(rows)
        print(f"{account:<52}{len(rows):>6}  {rows[0]['Date']}..{rows[-1]['Date']}")

    print(f"\nwrote {written} rows across {len(buckets)} files")
    for reason, n in dropped.most_common():
        print(f"  dropped {n:>5}  {reason}")
    print("\nFiles are listed smallest first. Import that one, confirm the amounts, categories\n"
          "and dates look right, then work down the list.")


if __name__ == "__main__":
    main()
