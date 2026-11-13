#!/usr/bin/env python3
"""Stáhne historii cen podílových listů z Conseq a spočítá data pro web.

Použití:
  python scripts/update.py              # stáhne ceny + přepočítá data/portfolio.json
  python scripts/update.py --no-download  # jen přepočítá z uložených cen
  python scripts/update.py --import-xlsx soubor.xlsx fond-id   # naimportuje ručně stažený soubor

Soubory:
  funds.json            seznam fondů (id, název, ISIN, productid pro Conseq, aliasy názvů)
  data/nakupy.csv       nákupy: datum, fond, pocet_kusu, castka_czk (castka je nepovinná)
  data/prices/<id>.csv  historie cen (datum, cena) – generuje skript
  data/portfolio.json   data pro graf – generuje skript
"""
import csv
import io
import json
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNDS_FILE = ROOT / "funds.json"
PURCHASES_FILE = ROOT / "data" / "nakupy.csv"
PRICES_DIR = ROOT / "data" / "prices"
OUTPUT_FILE = ROOT / "data" / "portfolio.json"

PRICE_URL = "https://www.conseq.cz/Conseq/Pricehist.ashx?productid={productid}&culture=cs-CZ"
USER_AGENT = "Mozilla/5.0 (compatible; verka-portfolio/1.0; +https://github.com)"


# ---------- parsování ----------

def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d. %m. %Y", "%d.%m.%y", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Neznámý formát data: {value!r}")


def parse_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    return float(s)


def rows_from_bytes(content: bytes):
    """Vrátí řádky tabulky z xlsx (zip) nebo textového CSV."""
    if content[:2] == b"PK":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    text = None
    for enc in ("utf-8-sig", "cp1250"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Soubor není xlsx ani čitelný text")
    if "<html" in text[:500].lower():
        raise ValueError("Server vrátil HTML stránku místo dat")
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=";,\t")
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def prices_from_rows(rows):
    """Najde hlavičku se sloupci Datum a Cena a vrátí {datum: cena}."""
    header_idx = None
    for i, row in enumerate(rows[:30]):
        cells = [str(c).strip().lower() if c is not None else "" for c in row]
        if "datum" in cells and any(c.startswith("cena") for c in cells):
            header_idx = i
            date_col = cells.index("datum")
            price_col = next(j for j, c in enumerate(cells) if c.startswith("cena"))
            break
    if header_idx is None:
        raise ValueError("V souboru chybí hlavička se sloupci Datum a Cena")
    prices = {}
    for row in rows[header_idx + 1:]:
        if len(row) <= max(date_col, price_col):
            continue
        d, p = row[date_col], row[price_col]
        if d in (None, "") or p in (None, ""):
            continue
        try:
            prices[parse_date(d)] = parse_number(p)
        except ValueError:
            continue
    if not prices:
        raise ValueError("V souboru nejsou žádné ceny")
    return prices


# ---------- uložené ceny ----------

def load_prices(fund_id):
    path = PRICES_DIR / f"{fund_id}.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {date.fromisoformat(r["datum"]): float(r["cena"]) for r in csv.DictReader(f)}


def save_prices(fund_id, prices):
    PRICES_DIR.mkdir(parents=True, exist_ok=True)
    path = PRICES_DIR / f"{fund_id}.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["datum", "cena"])
        for d in sorted(prices):
            w.writerow([d.isoformat(), repr(float(prices[d]))])


def merge_and_save(fund_id, new_prices):
    old = load_prices(fund_id)
    merged = {**old, **new_prices}
    save_prices(fund_id, merged)
    added = len(set(new_prices) - set(old))
    return added, max(merged)


def download(fund):
    url = PRICE_URL.format(productid=fund["productid"])
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = resp.read()
    return prices_from_rows(rows_from_bytes(content))


# ---------- výpočet portfolia ----------

def load_purchases(funds):
    alias = {}
    for fund in funds:
        for name in [fund["id"], fund["name"], *fund.get("aliases", [])]:
            alias[name.strip().lower()] = fund["id"]
    purchases = []
    with PURCHASES_FILE.open(encoding="utf-8-sig") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            if not (r.get("datum") or "").strip():
                continue
            key = (r.get("fond") or "").strip().lower()
            if key not in alias:
                raise SystemExit(f"data/nakupy.csv řádek {i}: neznámý fond {r.get('fond')!r} – doplň ho do aliasů ve funds.json")
            amount = (r.get("castka_czk") or "").strip()
            purchases.append({
                "date": parse_date(r["datum"]),
                "fund": alias[key],
                "units": parse_number(r["pocet_kusu"]),
                "amount": parse_number(amount) if amount else None,
            })
    return sorted(purchases, key=lambda p: p["date"])


def price_on(sorted_dates, prices, d):
    """Poslední známá cena k datu d (nebo první následující, pokud starší není)."""
    import bisect
    i = bisect.bisect_right(sorted_dates, d)
    if i == 0:
        nd = sorted_dates[0]
        return prices[nd], nd
    pd = sorted_dates[i - 1]
    return prices[pd], pd


def r2(x):
    return round(x, 2)


def build(funds):
    purchases = load_purchases(funds)
    if not purchases:
        raise SystemExit("data/nakupy.csv neobsahuje žádné nákupy")
    start = purchases[0]["date"]

    all_prices = {f["id"]: load_prices(f["id"]) for f in funds}
    held_ids = [f["id"] for f in funds if any(p["fund"] == f["id"] for p in purchases)]
    for fid in held_ids:
        if not all_prices[fid]:
            raise SystemExit(f"Chybí ceny pro fond {fid} (data/prices/{fid}.csv)")

    # Pro každý nákup dopočítat cenu a částku
    for p in purchases:
        prices = all_prices[p["fund"]]
        dates = sorted(prices)
        price, pdate = price_on(dates, prices, p["date"])
        p["price"] = price
        p["price_date"] = pdate
        if p["amount"] is None:
            p["amount"] = p["units"] * price
            p["amount_source"] = "odhad"
        else:
            p["amount_source"] = "zadáno"

    end = max(max(all_prices[fid]) for fid in held_ids)
    timeline = sorted({d for fid in held_ids for d in all_prices[fid] if start <= d <= end} | {p["date"] for p in purchases})

    out_funds = []
    total = {}
    for fund in funds:
        fid = fund["id"]
        if fid not in held_ids:
            continue
        prices = all_prices[fid]
        dates = sorted(prices)
        fps = [p for p in purchases if p["fund"] == fid]
        series = []
        for d in timeline:
            units = sum(p["units"] for p in fps if p["date"] <= d)
            invested = sum(p["amount"] for p in fps if p["date"] <= d)
            if units == 0:
                series.append([d.isoformat(), 0, 0])
                continue
            price, _ = price_on(dates, prices, d)
            value = units * price
            series.append([d.isoformat(), r2(value), r2(invested)])
            t = total.setdefault(d, [0.0, 0.0])
            t[0] += value
            t[1] += invested
        last_date = dates[-1]
        units = sum(p["units"] for p in fps)
        out_funds.append({
            "id": fid,
            "name": fund["name"],
            "isin": fund["isin"],
            "units": units,
            "last_price": prices[last_date],
            "last_price_date": last_date.isoformat(),
            "invested": r2(sum(p["amount"] for p in fps)),
            "value": r2(units * prices[last_date]),
            "purchases": [{
                "date": p["date"].isoformat(),
                "units": p["units"],
                "price": p["price"],
                "price_date": p["price_date"].isoformat(),
                "amount": r2(p["amount"]),
                "amount_source": p["amount_source"],
            } for p in fps],
            "series": series,
        })

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_price_date": end.isoformat(),
        "funds": out_funds,
        "total": {
            "invested": r2(sum(f["invested"] for f in out_funds)),
            "value": r2(sum(f["value"] for f in out_funds)),
            "series": [[d.isoformat(), r2(v), r2(i)] for d, (v, i) in sorted(total.items())],
        },
    }
    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Hotovo: {OUTPUT_FILE.relative_to(ROOT)} – hodnota {result['total']['value']:,.0f} Kč, "
          f"vloženo {result['total']['invested']:,.0f} Kč, ceny k {end}")


def main(argv):
    funds = json.loads(FUNDS_FILE.read_text(encoding="utf-8"))

    if len(argv) >= 3 and argv[0] == "--import-xlsx":
        path, fid = Path(argv[1]), argv[2]
        if fid not in {f["id"] for f in funds}:
            raise SystemExit(f"Neznámé id fondu {fid}")
        added, last = merge_and_save(fid, prices_from_rows(rows_from_bytes(path.read_bytes())))
        print(f"{fid}: +{added} nových cen, poslední {last}")
        return

    failures = 0
    if "--no-download" not in argv:
        for fund in funds:
            try:
                added, last = merge_and_save(fund["id"], download(fund))
                print(f"{fund['id']}: +{added} nových cen, poslední {last}")
            except Exception as e:  # stažení jednoho fondu nesmí shodit ostatní
                failures += 1
                print(f"::warning::{fund['id']}: stažení selhalo ({e}); ponechávám uložené ceny")
    build(funds)
    if failures == len(funds):
        raise SystemExit("Nepodařilo se stáhnout ceny žádného fondu.")


if __name__ == "__main__":
    main(sys.argv[1:])
