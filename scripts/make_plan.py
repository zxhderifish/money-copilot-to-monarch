#!/usr/bin/env python3
"""Turn converted CSVs into a migration plan the user can work through.

Imports are irreversible and there are usually dozens of files, so the useful
artifact is not another summary but a checklist: what to create before starting,
what order to upload in, and what each step should look like when it worked.

Comparing against a Monarch export is what makes the "create these first" lists
real rather than guesses -- an account or category named even slightly differently
gets silently created as a duplicate rather than matched.

Usage:
    python make_plan.py --transactions monarch_import/ [monarch_import_ck/] \
                        --balances monarch_balances/ \
                        --monarch-export Transactions.csv \
                        --out PLAN.md
"""

import argparse
import collections
import csv
import glob
import os


def load_dir(path):
    rows = []
    for f in sorted(glob.glob(os.path.join(path, "*.csv"))):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            r["_file"] = f
            rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transactions", nargs="*", default=[],
                    help="one or more directories of converted transaction CSVs")
    ap.add_argument("--balances", help="directory of Date,Balance CSVs")
    ap.add_argument("--monarch-export", help="a transactions export from Monarch")
    ap.add_argument("--out", default="PLAN.md")
    args = ap.parse_args()

    rows = []
    for d in args.transactions:
        rows += load_dir(d)

    have_accounts, have_categories = set(), set()
    if args.monarch_export:
        for r in csv.DictReader(open(args.monarch_export, encoding="utf-8")):
            have_accounts.add(r["Account"])
            if r["Category"]:
                have_categories.add(r["Category"])

    # One file per account per source, so an account can legitimately have two.
    files = collections.defaultdict(list)
    for r in rows:
        files[r["_file"]].append(r)
    per_file = {}
    for f, rs in files.items():
        dates = [r["Date"] for r in rs]
        per_file[f] = {"account": rs[0]["Account"], "n": len(rs),
                       "lo": min(dates), "hi": max(dates)}
    by_account = collections.defaultdict(list)
    for f, meta in per_file.items():
        by_account[meta["account"]].append((f, meta))

    out = ["# Migration checklist", "",
           f"{len(rows)} transactions across {len(per_file)} files and {len(by_account)} accounts.",
           "**Imports cannot be undone.** Work down the list, and check the first one by hand "
           "before continuing.", ""]

    if args.monarch_export:
        missing_acc = sorted(a for a in by_account if a not in have_accounts)
        if missing_acc:
            out += ["## Step 1 — create these accounts", "",
                    "Monarch does not have these yet. The names must match exactly, or the import "
                    "creates a second account beside the one you meant.", "",
                    "> This list comes from a transactions export, which **proves presence but never "
                    "absence** — an account with no transactions is invisible in one, so some of "
                    "these may already exist. Check against the accounts page before creating any.", "",
                    "| ✓ | Account | Rows | Range |", "|---|---|---|---|"]
            for a in missing_acc:
                n = sum(m["n"] for _, m in by_account[a])
                lo = min(m["lo"] for _, m in by_account[a])
                hi = max(m["hi"] for _, m in by_account[a])
                out.append(f"| ☐ | `{a}` | {n} | {lo} ~ {hi} |")
            out.append("")

        used = collections.Counter(r["Category"] for r in rows)
        missing_cat = sorted((c for c in used if c not in have_categories),
                             key=lambda c: -used[c])
        if missing_cat:
            out += ["## Step 2 — create these categories", "",
                    f"The other {len(used) - len(missing_cat)} categories will match existing ones.", "",
                    "| ✓ | Category | Rows |", "|---|---|---|"]
            for c in missing_cat:
                out.append(f"| ☐ | `{c}` | {used[c]} |")
            out.append("")

    step = 3 if args.monarch_export else 1
    out += [f"## Step {step} — import transactions", "",
            "One file at a time. Choose **Prioritize CSV** to overwrite, or **Prioritize Monarch** "
            "to fill gaps only.",
            "★ marks an account with two files; upload them in the order shown, oldest first.", "",
            "| # | ✓ | Rows | Range | File |", "|---|---|---|---|---|"]
    i = 0
    # Smallest account first: a mistake on four rows is cheap to undo.
    for account in sorted(by_account, key=lambda a: sum(m["n"] for _, m in by_account[a])):
        group = sorted(by_account[account], key=lambda fm: fm[1]["lo"])
        for f, meta in group:
            i += 1
            star = " ★" if len(group) > 1 else ""
            out.append(f"| {i}{star} | ☐ | {meta['n']} | {meta['lo']} ~ {meta['hi']} | `{f}` |")
    out += ["",
            "After the first upload, check three things before continuing: amounts point the right "
            "way (expenses negative), categories resolved rather than landing in Uncategorized, "
            "and dates fall in the expected range.", ""]

    if args.balances:
        bal = sorted(glob.glob(os.path.join(args.balances, "*.csv")))
        if bal:
            out += [f"## Step {step + 1} — import balance history", "",
                    "**A separate channel** — the account page → Edit → import balance history, one file "
                    "per account.",
                    "Net worth is built from these alone; no amount of transaction history moves it.", "",
                    "| ✓ | Periods | Range | File |", "|---|---|---|---|"]
            for f in bal:
                r = list(csv.DictReader(open(f, encoding="utf-8")))
                if r:
                    out.append(f"| ☐ | {len(r)} | {r[0]['Date']} ~ {r[-1]['Date']} | `{f}` |")
            out.append("")

    open(args.out, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"wrote {args.out}")
    print(f"  {len(rows)} transactions in {len(per_file)} files")
    if args.monarch_export:
        print(f"  {len(missing_acc)} accounts and {len(missing_cat)} categories to create first")
    if args.balances:
        print(f"  {len(glob.glob(os.path.join(args.balances, '*.csv')))} balance files")


if __name__ == "__main__":
    main()
