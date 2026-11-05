"""Rebuild the frozen extracts in data/ from the raw public downloads.

You do not need this to replay the exercise: data/ is committed. It is here so
every number can be traced back to a public file.

Raw inputs (all public, see README for URLs and dates):
  RAW/FCC-08-3A1.txt              pdftotext -layout of the FCC order FCC 08-3 (released 2008-01-24)
  RAW/facility_detail.jsonl       one JSON line per AM/FM facility from the FCC public files API (2026-11-05)
  RAW/cdbs/call_sign_history.dat  FCC CDBS call sign history (file dated 2024-01-09, CDBS frozen since 2023-10-01)
  RAW/cdbs/facility.dat           FCC CDBS facility table (same date)
  RAW/wikidata_p1400_p2317.csv    Wikidata SPARQL export (CC0), 2026-11-05

Usage: python3 tools/build_extracts.py RAW_DIR
"""
import csv, json, re, sys
from pathlib import Path

RAW = Path(sys.argv[1])
OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(exist_ok=True)

LINE_RE = re.compile(r"^\s*([A-Z0-9][A-Z0-9()\- ]{2,14}?)\s{2,}(\d{1,7})\s{2,}(.+?),\s*([A-Z]{2})\s+(\S+)?\s*$")


def us_date(s):
    s = (s or "").strip()
    m = re.match(r"(\d\d)/(\d\d)/(\d{4})$", s)
    return f"{m[3]}-{m[1]}-{m[2]}" if m else ""


def build_lot():
    pages = (RAW / "FCC-08-3A1.txt").read_text().split("\f")
    lot, answers = [], []
    # Appendix A ("Licenses Subject To Transfer Of Control") runs from page 19 to page 41.
    for pno in range(19, 42):
        for raw_line in pages[pno - 1].splitlines():
            m = LINE_RE.match(raw_line)
            if not m:
                continue
            call, fid, city, state, filesuffix = m.groups()
            line_id = f"A{len(lot) + 1:04d}"
            lot.append({"line_id": line_id, "page": pno, "printed_call": call.strip(),
                        "city": city.strip(), "state": state})
            answers.append({"line_id": line_id, "facility_id_printed": fid})
    write(OUT / "lot_fcc08-3_appendix_a.csv", lot)
    write(OUT / "answers_fcc08-3_appendix_a.csv", answers)
    return lot


def build_registry():
    rows = []
    for l in (RAW / "facility_detail.jsonl").read_text().splitlines():
        d = json.loads(l)
        if d.get("_error") or d.get("_missing"):
            raise SystemExit(f"incomplete download: {d}")
        rows.append({"facility_id": d["id"], "call_sign": d["callSign"], "service": d["serviceCode"],
                     "status": d["status"], "city": d["communityCity"], "state": d["communityState"],
                     "frequency": d["frequency"], "active": d["activeInd"]})
    rows.sort(key=lambda r: int(r["facility_id"]))
    write(OUT / "registry_fcc_2026-11-05.csv", rows)
    return rows


def build_timeline():
    fac = {}
    for l in (RAW / "cdbs" / "facility.dat").read_text(errors="replace").splitlines():
        c = l.rstrip("\r").split("|")
        if len(c) < 23 or c[10] not in ("AM", "FM"):
            continue
        fac[c[14]] = {"call": c[5], "service": c[10], "city": c[0], "state": c[1], "status": c[16],
                      "eff": us_date(c[21])}
    hist = {}
    for l in (RAW / "cdbs" / "call_sign_history.dat").read_text(errors="replace").splitlines():
        c = l.rstrip("\r").split("|")
        if len(c) < 5 or c[4] not in fac:
            continue
        hist.setdefault(c[4], []).append((int(c[3] or 0), c[1].strip(), us_date(c[0])))
    rows = []
    for fid, f in fac.items():
        entries = [(s, call, d, "cdbs_history") for s, call, d in sorted(hist.get(fid, []))]
        cur = (len(entries) + 1, f["call"], f["eff"], "cdbs_current")
        if entries and entries[-1][1] == cur[1]:
            last = entries.pop()
            cur = (last[0], cur[1], last[2] or cur[2], "cdbs_current")
        entries.append(cur)
        for seq, call, d, src in entries:
            rows.append({"facility_id": fid, "seq": seq, "call_sign": call, "effective_date": d, "source": src,
                         "cdbs_service": f["service"], "cdbs_city": f["city"], "cdbs_state": f["state"],
                         "cdbs_status": f["status"]})
    rows.sort(key=lambda r: (int(r["facility_id"]), r["seq"]))
    write(OUT / "cdbs_call_sign_timeline_2024-01-09.csv", rows)


def build_wikidata():
    seen, rows = set(), []
    for r in csv.DictReader(open(RAW / "wikidata_p1400_p2317.csv")):
        if not r["web"]:
            continue
        key = (r["fid"], r["item"], r["web"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({"facility_id": r["fid"], "wikidata_item": r["item"].rsplit("/", 1)[-1], "website": r["web"]})
    rows.sort(key=lambda r: (r["facility_id"], r["wikidata_item"], r["website"]))
    write(OUT / "wikidata_websites_2026-11-05.csv", rows)


def write(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{path.name}: {len(rows)} rows")


if __name__ == "__main__":
    build_lot()
    build_registry()
    build_timeline()
    build_wikidata()
