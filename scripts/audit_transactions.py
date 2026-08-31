#!/usr/bin/env python3
"""Check converted Monarch CSVs before importing, since imports cannot be undone.

Compares the output against the source export row by row and reports the shape of
what will land in Monarch. Run this before the first upload.

Usage:
    python audit_transactions.py OUTPUT_DIR --source transactions.csv --format copilot
"""

import argparse
import collections
import csv
import glob
import os
import sys


def load_output(out_dir):
    rows = []
    for path in sorted(glob.glob(os.path.join(out_dir, "*.csv"))):
        rows += list(csv.DictReader(open(path, encoding="utf-8")))
    return rows


def load_source(path, fmt):
    out = []
    for row in csv.DictReader(open(path, encoding="utf-8")):
        if fmt == "copilot":
            # Copilot signs expenses positive; the converter flips them.
            out.append((row["date"], row["name"], round(-float(row["amount"]), 2)))
        else:
            amount = float(row["Amount"])
            if row["Transaction Type"] == "debit":
                amount = -amount
            name = row["Description"].strip() or row["Original Description"].strip()
            out.append((row["Date"], name, round(amount, 2)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output_dir")
    ap.add_argument("--source")
    ap.add_argument("--format", choices=["copilot", "creditkarma"], default="copilot")
    args = ap.parse_args()

    rows = load_output(args.output_dir)
    if not rows:
        sys.exit(f"no CSVs in {args.output_dir}")

    problems = []

    missing = [r for r in rows if not (r["Date"] and r["Merchant"]
                                       and r["Amount"] and r["Account"])]
    if missing:
        problems.append(f"{len(missing)} rows are missing a required field (Date / Merchant / Amount / Account)")

    # A merchant renamed by the converter should still keep its raw text.
    blank_statement = [r for r in rows if not r["Original Statement"]]

    income = sum(float(r["Amount"]) for r in rows if float(r["Amount"]) > 0)
    expense = sum(float(r["Amount"]) for r in rows if float(r["Amount"]) < 0)
    print(f"rows          {len(rows)}")
    print(f"accounts      {len(set(r['Account'] for r in rows))}")
    print(f"categories    {len(set(r['Category'] for r in rows))}")
    print(f"dates         {min(r['Date'] for r in rows)} .. {max(r['Date'] for r in rows)}")
    print(f"income {income:>13,.2f}   expenses {expense:>13,.2f}   net {income + expense:>12,.2f}")
    if blank_statement:
        print(f"blank Original Statement  {len(blank_statement)}")

    # Expenses positive is the classic sign error; on a card account almost
    # everything should be negative.
    print("\nsigns per account (expenses should be negative)")
    per = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        per[r["Account"]][0 if float(r["Amount"]) < 0 else 1] += 1
    for account, (neg, pos) in sorted(per.items(), key=lambda kv: -sum(kv[1]))[:12]:
        print(f"  {account[:48]:<50}neg {neg:>5}  pos {pos:>5}")

    print("\ncategory distribution")
    counts = collections.Counter(r["Category"] for r in rows)
    for category, n in counts.most_common(15):
        print(f"  {n:>5}  {category}")
    unc = counts.get("Uncategorized", 0)
    if unc > len(rows) * 0.1:
        problems.append(f"Uncategorized is {unc / len(rows):.0%} of rows — the category map may not be taking effect")

    if args.source:
        source = load_source(args.source, args.format)
        have = collections.Counter((r["Date"], r["Merchant"], round(float(r["Amount"]), 2))
                                   for r in rows)
        # Renamed merchants will not match by name; fall back to date + amount.
        by_amount = collections.Counter((r["Date"], round(float(r["Amount"]), 2)) for r in rows)
        unmatched = [s for s in source
                     if not have[s] and not by_amount[(s[0], s[2])]]
        print(f"\nsource has {len(source)} rows; {len(unmatched)} of them are not in the output")
        for s in unmatched[:8]:
            print(f"  {s[0]}  {s[2]:>10,.2f}  {s[1][:40]}")
        if len(unmatched) > 8:
            print(f"  ... and {len(unmatched) - 8} more")
        print("  Rows dropped on purpose — zero amounts, still pending, skipped accounts —\n"
              "  show up here and are expected.")

    print()
    if problems:
        for p in problems:
            print(f"  ⚠ {p}")
    else:
        print("  No structural problems. Import the smallest file first and check it by hand.")


if __name__ == "__main__":
    main()
