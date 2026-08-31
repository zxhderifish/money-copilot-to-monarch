#!/usr/bin/env python3
"""Extract balance history from statement PDFs into Monarch's Date,Balance format.

Statements are built to reconcile, and that is what makes this tractable: a figure
that reproduces a total the document itself states is trustworthy in a way a lone
regex match never is. Every layout here declares a reconciliation, and the run
reports how many statements passed it.

Institutions rework their statements every few years, so one account's five-year
run usually spans several layouts. Files that match no layout are reported rather
than skipped -- a silent skip is indistinguishable from success.

Usage:
    python extract_balances.py STATEMENT_DIR OUT_DIR [--prefix NAME] [--recursive]

Adding a layout: copy the closest Layout below, adjust the patterns, and give it a
`detect` regex specific enough not to claim another layout's files. Run with
--verbose to see which layout claimed each file.
"""

import argparse
import csv
import datetime
import glob
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber is required:  python -m venv .venv && .venv/bin/pip install pdfplumber")


# --------------------------------------------------------------------------- helpers

def money(text: str) -> float:
    """Parse a statement amount. Accounting parentheses mean negative; a bare dash
    means the column is empty, which is not the same as the next number on the line."""
    text = (text or "").strip()
    if text in ("", "-", "--", "—"):
        return 0.0
    negative = text.startswith("(") or text.startswith("-")
    digits = text.strip("()").replace("$", "").replace(",", "").lstrip("-")
    return -float(digits) if negative else float(digits)


def first(pattern: re.Pattern, lines, group: int = 1) -> Optional[str]:
    for line in lines:
        m = pattern.search(line)
        if m:
            return m.group(group)
    return None


def us_date(text: str) -> str:
    """Accept the date spellings statements use, return ISO."""
    for fmt in ("%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {text!r}")


# --------------------------------------------------------------------------- layouts

@dataclass
class Reading:
    """One statement's worth of extracted figures."""
    date: str
    account: str
    balance: float
    layout: str
    check: Optional[str] = None      # description of the check, if one ran
    check_ok: Optional[bool] = None


@dataclass
class Layout:
    """A statement format: how to recognise it and what to read out of it.

    `detect` should match something distinctive to this issuer *and* era. `read`
    receives the statement's lines plus the filename and returns a Reading, or None
    if this layout cannot in fact handle the file.
    """
    name: str
    detect: re.Pattern
    read: Callable[[list, str], Optional[Reading]]


def _reconcile(reading: Reading, parts: dict, expected_key: str = "ending") -> Reading:
    """Attach a pass/fail from summing `parts` against the stated ending balance."""
    total = sum(parts.values())
    stated = reading.balance
    reading.check = " + ".join(f"{k} {v:,.2f}" for k, v in parts.items()) + f" = {stated:,.2f}"
    reading.check_ok = abs(total - stated) < 0.02
    if not reading.check_ok:
        reading.check += f"   [computed {total:,.2f}]"
    return reading


# --- Bank of America checking -------------------------------------------------

_BOA_ACCT = re.compile(r"Account number:\s*([\d ]+\d)")
_BOA_BEGIN = re.compile(r"^Beginning balance on (\w+ \d{1,2}, \d{4})\s+(-?\$?-?[\d,]+\.\d{2})")
_BOA_END = re.compile(r"^Ending balance on (\w+ \d{1,2}, \d{4})\s+(-?\$?-?[\d,]+\.\d{2})")
_BOA_PARTS = {
    "deposits": re.compile(r"^Deposits and other additions\s+(-?\$?-?[\d,]+\.\d{2})"),
    "withdrawals": re.compile(r"^Withdrawals and other subtractions\s+(-?\$?-?[\d,]+\.\d{2})"),
    "checks": re.compile(r"^Checks\s+(-?\$?-?[\d,]+\.\d{2})"),
    "fees": re.compile(r"^Service fees\s+(-?\$?-?[\d,]+\.\d{2})"),
}


def _read_boa(lines, filename):
    end = None
    for line in lines:
        m = _BOA_END.match(line)
        if m:
            end = m
            break
    if not end:
        return None
    acct = first(_BOA_ACCT, lines) or "unknown"
    reading = Reading(us_date(end.group(1)), acct.replace(" ", "")[-4:],
                      money(end.group(2)), "bofa-checking")
    begin = None
    for line in lines:
        m = _BOA_BEGIN.match(line)
        if m:
            begin = money(m.group(2))
            break
    if begin is None:
        return reading
    parts = {"beginning": begin}
    for key, pat in _BOA_PARTS.items():
        v = first(pat, lines)
        if v is not None:
            parts[key] = money(v)
    return _reconcile(reading, parts)


# --- Schwab Bank (Investor Checking) -----------------------------------------

_SB_PARTS = {
    "beginning": re.compile(r"^Beginning Balance\s+\$?\s?(\(?-?[\d,]+\.\d{2}\)?)"),
    "deposits": re.compile(r"^Deposits and Credits\s+\$?\s?(\(?-?[\d,]+\.\d{2}\)?)"),
    "interest": re.compile(r"^Interest Paid\s+\$?\s?(\(?-?[\d,]+\.\d{2}\)?)"),
    "withdrawals": re.compile(r"^Withdrawals and Other Debits\s+\$?\s?(\(?-?[\d,]+\.\d{2}\)?)"),
    "checks": re.compile(r"^Checks Paid\s+\$?\s?(\(?-?[\d,]+\.\d{2}\)?)"),
}
_SB_END = re.compile(r"^Ending Balance\s+\$?\s?(\(?-?[\d,]+\.\d{2}\)?)")
_SB_ACCT = re.compile(r"Account Number:\s*(\d[\d ]*\d)")
_SB_PERIOD = re.compile(r"to\s+(\w+ \d{1,2}, \d{4})")


def _read_schwab_bank(lines, filename):
    end = first(_SB_END, lines)
    if end is None:
        return None
    date = _date_from_filename(filename) or (
        us_date(first(_SB_PERIOD, lines)) if first(_SB_PERIOD, lines) else None)
    if not date:
        return None
    acct = first(_SB_ACCT, lines) or "unknown"
    reading = Reading(date, acct.replace(" ", "")[-4:], money(end), "schwab-bank")
    parts = {}
    for key, pat in _SB_PARTS.items():
        v = first(pat, lines)
        if v is not None:
            parts[key] = money(v)
    return _reconcile(reading, parts) if "beginning" in parts else reading


# --- Schwab brokerage (three eras) -------------------------------------------

_SBK_AMOUNT = r"\$?\s?(\(?-?[\d,]+\.\d{2}\)?)"
_L = r"(?:^|\s)"          # a sidebar column often precedes the label on the line
_SBK = {
    "ending": re.compile(rf"{_L}Ending(?:Account)?Value\s+{_SBK_AMOUNT}"),
    "beginning": re.compile(rf"{_L}(?:Beginning(?:Account)?Value|Starting\s?AccountValue)\s+{_SBK_AMOUNT}"),
    "deposits": re.compile(rf"{_L}Deposits\s+{_SBK_AMOUNT}"),
    "withdrawals": re.compile(rf"{_L}Withdrawals\s+{_SBK_AMOUNT}"),
    "income": re.compile(rf"{_L}DividendsandInterest\s+{_SBK_AMOUNT}"),
    "transfers": re.compile(rf"{_L}TransferofSecurities(?:\(In/Out\))?\s+{_SBK_AMOUNT}"),
    "expenses": re.compile(rf"{_L}(?:Expenses|Fees)\s+{_SBK_AMOUNT}"),
    "market": re.compile(rf"{_L}(?:MarketAppreciation/\(Depreciation\)|MarketValueChange)\s+{_SBK_AMOUNT}"),
    # 2022 era
    "txn_income": re.compile(rf"{_L}Transactions\s?&Income\s+{_SBK_AMOUNT}"),
    "reinvested": re.compile(rf"{_L}Income\s?Reinvested\s+{_SBK_AMOUNT}"),
    "change": re.compile(rf"{_L}ChangeinValueofInvestments\s+{_SBK_AMOUNT}"),
}
# The account number sits on the header line in one era and the line below it in
# another, so search the document rather than a fixed line. The word boundaries
# keep it off the longer mail codes that share the shape.
_SBK_ACCT = re.compile(r"\b(\d{4}-\d{4})\b")


def _read_schwab_brokerage(lines, filename):
    end = first(_SBK["ending"], lines)
    if end is None:
        return None
    date = _date_from_filename(filename)
    if not date:
        return None
    acct = first(_SBK_ACCT, lines) or "unknown"
    reading = Reading(date, acct[-4:], money(end), "schwab-brokerage")
    got = {k: money(v) for k, v in
           ((k, first(p, lines)) for k, p in _SBK.items()) if v is not None}
    # Expenses are stated positive but subtract.
    if {"beginning", "market"} <= got.keys():
        parts = {k: got[k] for k in
                 ("beginning", "deposits", "withdrawals", "income", "transfers", "market")
                 if k in got}
        if "expenses" in got:
            parts["expenses"] = -abs(got["expenses"])
        return _reconcile(reading, parts)
    if {"beginning", "change"} <= got.keys():
        parts = {k: got[k] for k in
                 ("beginning", "txn_income", "reinvested", "change") if k in got}
        return _reconcile(reading, parts)
    return reading


# --- Schwab equity awards (stock plan) ---------------------------------------

_EA_TOTAL = re.compile(r"^Total:\s*\$([\d,]+\.\d{2})")
_EA_HOLDING = re.compile(r"^([\d,]+\.\d{4})\s+([\d,]+\.\d{4})\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})$")
_EA_CASH = re.compile(r"^\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})$")


def _read_schwab_equity(lines, filename):
    total = first(_EA_TOTAL, lines)
    if total is None:
        return None
    date = _date_from_filename(filename)
    if not date:
        return None
    reading = Reading(date, "equity-awards", money(total), "schwab-equity-awards")
    parts = {}
    for line in lines:
        m = _EA_HOLDING.match(line)
        if m:
            shares, price, value = money(m.group(2)), money(m.group(3)), money(m.group(4))
            parts[f"holding@{price}"] = value
            # shares x price is an independent check on the holding line itself
            if abs(shares * price - value) > 0.02:
                reading.check_ok = False
        m = _EA_CASH.match(line)
        if m and "cash" not in parts:
            parts["cash"] = money(m.group(3))
    return _reconcile(reading, parts) if parts else reading


# --- Fidelity (combined household, solo, and year-end) -----------------------

_FID_ROW = re.compile(
    r"^\d+\s+(?P<name>.+?)\s+(?P<number>[A-Z]?\d{2,3}-\d{6})\s+"
    r"(?P<beginning>\$?[\d,]+\.\d{2}|-)\s+(?P<ending>\$?[\d,]+\.\d{2}|-)\s*$")
_FID_TOTAL = re.compile(r"^Ending Portfolio Value\s+\$?[\d,]+\.\d{2}\s+\$?([\d,]+\.\d{2})")
_FID_SOLO_ACCT = re.compile(r"^Account Number:\s*([A-Z]?\d{2,3}-\d{6})")
_FID_PERIOD = r"(-(?=\s|$)|-?[\d,]+\.\d{2})"
_FID_SOLO = {
    "beginning": re.compile(rf"^Beginning Account Value(?: as of [^$]*?)?\s+\$?(-?[\d,]+\.\d{{2}})"),
    "additions": re.compile(rf"^Additions\s+{_FID_PERIOD}"),
    "subtractions": re.compile(rf"^Subtractions\s+{_FID_PERIOD}"),
    "change": re.compile(rf"^Change in Investment Value \*?\s+{_FID_PERIOD}"),
    "ending": re.compile(rf"^Ending Account Value(?: as of [^$*]*?)?\s*\*{{0,2}}\s+\$?(-?[\d,]+\.\d{{2}})"),
}


def _read_fidelity(lines, filename):
    date = _date_from_filename(filename)
    if not date:
        return None

    rows = {}
    for line in lines:
        m = _FID_ROW.match(line)
        if m:
            rows[m.group("number")[-4:]] = money(m.group("ending"))
    if rows:
        # Combined statement: one reading per account, checked against the total.
        total = first(_FID_TOTAL, lines)
        readings = []
        for mask, value in rows.items():
            readings.append(Reading(date, mask, value, "fidelity-combined"))
        if total is not None:
            ok = abs(sum(rows.values()) - money(total)) < 0.02
            for r in readings:
                r.check = f"accounts sum {sum(rows.values()):,.2f} = portfolio {money(total):,.2f}"
                r.check_ok = ok
        return readings

    end = first(_FID_SOLO["ending"], lines)
    acct = first(_FID_SOLO_ACCT, lines)
    if end is None or acct is None:
        return None
    reading = Reading(date, acct[-4:], money(end), "fidelity-solo")
    parts = {}
    for key in ("beginning", "additions", "subtractions", "change"):
        v = first(_FID_SOLO[key], lines)
        if v is not None:
            parts[key] = money(v)
    return _reconcile(reading, parts) if "beginning" in parts else reading


# --- Vanguard Personal Investor (IRAs, brokerage) ----------------------------

_VG_SECTION = re.compile(r"^(?P<name>.+?)\s*[—-]\s*(?:XXXX|\d{4})(?P<mask>\d{4})\b")
_VG_ACCOUNT_TOTAL = re.compile(r"^Account overview\s+\$(-?[\d,]+\.\d{2})")
_VG_STATEMENT_TOTAL = re.compile(r"^Statement overview\s+\$(-?[\d,]+\.\d{2})")
_VG_AS_OF = re.compile(r"^Total account value as of\s+(\w+ \d{1,2}, \d{4})")


def _read_vanguard(lines, filename):
    as_of = first(_VG_AS_OF, lines)
    if as_of is None:
        return None
    date = us_date(as_of)
    accounts, mask = {}, None
    for line in lines:
        m = _VG_SECTION.match(line)
        if m:
            mask = m.group("mask")
        m = _VG_ACCOUNT_TOTAL.match(line)
        if m and mask and mask not in accounts:
            accounts[mask] = money(m.group(1))
    if not accounts:
        return None
    readings = [Reading(date, k, v, "vanguard-personal") for k, v in accounts.items()]
    total = first(_VG_STATEMENT_TOTAL, lines)
    if total is not None:
        ok = abs(sum(accounts.values()) - money(total)) < 0.02
        for r in readings:
            r.check = f"accounts sum {sum(accounts.values()):,.2f} = statement {money(total):,.2f}"
            r.check_ok = ok
    return readings


# --- Vanguard retirement plan (401k etc.) ------------------------------------

_401K_PERIOD = re.compile(r"^ACCOUNT SUMMARY:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})")
_401K_PLAN = re.compile(r"(\d{6})\s*$")
_401K_AMT = r"(-?\$?-?[\d,]+\.\d{2})"
_401K = {
    "beginning": re.compile(rf"^Beginning balance\s+{_401K_AMT}"),
    "contributions": re.compile(rf"^Your contributions\s+{_401K_AMT}"),
    "employer": re.compile(rf"^Employer contributions\s+{_401K_AMT}"),
    "market": re.compile(rf"^Market gain/loss\s+{_401K_AMT}"),
    "other": re.compile(rf"^Other transactions\s+{_401K_AMT}"),
    "fees": re.compile(rf"^Fees\*?\s+{_401K_AMT}"),
}
_401K_END = re.compile(rf"^Ending balance\s+{_401K_AMT}")
_401K_COVER = re.compile(rf"^Total Account Balance:\s*{_401K_AMT}")


def _read_401k(lines, filename):
    period = None
    for line in lines:
        m = _401K_PERIOD.match(line)
        if m:
            period = us_date(m.group(2))
            break
    end = first(_401K_END, lines)
    if period is None or end is None:
        return None
    mask = "unknown"
    for line in lines:
        if "401(K)" in line.upper():
            m = _401K_PLAN.search(line)
            if m:
                mask = m.group(1)[-4:]
                break
    reading = Reading(period, mask, money(end), "vanguard-401k")
    parts = {k: money(v) for k, v in
             ((k, first(p, lines)) for k, p in _401K.items()) if v is not None}
    reading = _reconcile(reading, parts) if "beginning" in parts else reading
    cover = first(_401K_COVER, lines)
    if cover is not None and abs(money(cover) - reading.balance) > 0.02:
        reading.check = (reading.check or "") + \
            f"   [cover {money(cover):,.2f} != detail {reading.balance:,.2f}]"
        reading.check_ok = False
    return reading


LAYOUTS = [
    Layout("bofa-checking", re.compile(r"Beginning balance on"), _read_boa),
    Layout("schwab-bank", re.compile(r"Deposits and Credits"), _read_schwab_bank),
    Layout("schwab-equity-awards", re.compile(r"Account Summary:\s*\w+"), _read_schwab_equity),
    Layout("schwab-brokerage", re.compile(r"Ending(?:Account)?Value"), _read_schwab_brokerage),
    Layout("fidelity", re.compile(r"Fidelity|FIDELITY"), _read_fidelity),
    Layout("vanguard-401k", re.compile(r"ACCOUNT SUMMARY:"), _read_401k),
    Layout("vanguard-personal", re.compile(r"Total account value as of"), _read_vanguard),
]


# --------------------------------------------------------------------------- driver

_FILENAME_DATE = [
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),          # 2024-12-31
    re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)"),  # 12312024
]


def _date_from_filename(filename: str) -> Optional[str]:
    """Many issuers name the file for the period it closes; the PDF may not repeat it."""
    m = _FILENAME_DATE[0].search(filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _FILENAME_DATE[1].search(filename)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
    return None


def read_statement(path: str, verbose: bool = False):
    with pdfplumber.open(path) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    lines = [l.strip() for l in text.split("\n")]
    filename = os.path.basename(path)

    for layout in LAYOUTS:
        if not layout.detect.search(text):
            continue
        result = layout.read(lines, filename)
        if result is None:
            continue
        readings = result if isinstance(result, list) else [result]
        if verbose:
            print(f"    {filename}  ->  {layout.name}")
        return readings
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("statement_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--prefix", default="", help="prefix for output filenames")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    pattern = "**/*.[pP][dD][fF]" if args.recursive else "*.[pP][dD][fF]"
    paths = sorted(glob.glob(os.path.join(args.statement_dir, pattern),
                             recursive=args.recursive))
    if not paths:
        sys.exit(f"no PDFs under {args.statement_dir}")

    series, checks, failures, unparsed = {}, 0, 0, []
    conflicts = []
    for path in paths:
        readings = read_statement(path, args.verbose)
        if not readings:
            unparsed.append(os.path.basename(path))
            continue
        for r in readings:
            if r.check_ok is not None:
                checks += 1
                if not r.check_ok:
                    failures += 1
                    print(f"  CHECK FAILED  {os.path.basename(path)} [{r.account}]: {r.check}")
            prior = series.setdefault(r.account, {}).get(r.date)
            if prior is not None and abs(prior - r.balance) > 0.02:
                conflicts.append(f"{r.account} {r.date}: {prior:,.2f} vs {r.balance:,.2f}")
            series[r.account][r.date] = r.balance

    os.makedirs(args.out_dir, exist_ok=True)
    print()
    for account in sorted(series, key=lambda a: -len(series[a])):
        rows = [{"Date": d, "Balance": f"{v:.2f}"} for d, v in sorted(series[account].items())]
        name = f"{args.prefix}{account}.csv" if args.prefix else f"{account}.csv"
        out = os.path.join(args.out_dir, name)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["Date", "Balance"])
            w.writeheader()
            w.writerows(rows)
        print(f"  {out}  {len(rows)} periods  {rows[0]['Date']} .. {rows[-1]['Date']}"
              f"   last ${float(rows[-1]['Balance']):,.2f}")

    print(f"\n{len(paths)} statements, {len(paths) - len(unparsed)} parsed, "
          f"{checks} checks, {failures} failures")
    for c in conflicts:
        print(f"  conflicting values for one period: {c}")
    for u in unparsed:
        print(f"  no layout matched: {u}")
    if unparsed:
        print("\n  These need a new layout. Open one, find the ending balance it states\n"
              "  and the identity it reconciles with, then copy the closest Layout.")


if __name__ == "__main__":
    main()
