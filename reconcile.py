"""Link old station lines to today's FCC facilities, with a rule you can change.

    python3 reconcile.py                     # rule "dated": the call sign as it stood on the list's date
    python3 reconcile.py --rule today        # rule "today": the call sign as registered today
    python3 reconcile.py --accept-undated    # dated, and also link a call sign whose record has no start date
    python3 reconcile.py --require-city      # also require today's city of license to agree
    python3 reconcile.py --compare           # lines that change between the today and dated rules

Every run writes out/decisions.csv and, when a previous run left one, lists the lines whose
decision or facility changed since that run. Edit a rule, run again, and you see what moved.

Standard library only. No model, no network.
"""
import argparse, csv, json, re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
LIST_DATE = "2008-01-24"          # FCC 08-3 released 2008-01-24; Appendix A corrected by erratum 2008-01-30
CDBS_FROZEN = "2023-10-01"        # CDBS stopped being updated on this date
SNAPSHOT = "2026-11-05"           # date of the FCC registry extract

TV_SUFFIX = re.compile(r"(\(TV\)|-TV|-DT|-CA|-LP|-CD|-LD)$")
TRANSLATOR = re.compile(r"^[KW]\d{3}[A-Z]{2}$")          # FM translator, e.g. K236AB
TV_TRANSLATOR = re.compile(r"^[KW]\d{2}[A-Z]{2}(-?D)?$")  # TV translator, e.g. K31AE, K51BK-D
BOOSTER = re.compile(r"^[KW][A-Z]{2,3}-?FM\d$")           # FM booster, e.g. KIOI-FM1


# ---------- reading and normalising ----------------------------------------------------------

def parse_printed_call(printed):
    """'KUBE(FM)' -> ('KUBE', 'FM'); 'WKEEFM' -> ('WKEEFM', 'FM'); 'K236AB' -> ('K236AB', 'translator')."""
    s = printed.upper().replace(" ", "")
    if TV_SUFFIX.search(s) or TV_TRANSLATOR.match(s):
        return call_key(s), "TV"
    if BOOSTER.match(s):
        return call_key(s), "booster"
    if TRANSLATOR.match(s):
        return s, "translator"
    m = re.match(r"^(.*)\((AM|FM)\)?$", s)
    if m:
        return call_key(m[1]), m[2]
    if s.endswith("FM") and len(s) >= 5:
        return call_key(s), "FM"
    return call_key(s), None


def call_key(call):
    """Compare call signs without punctuation: 'KJR-FM', 'KJRFM' and 'KJR- FM' are the same key."""
    return re.sub(r"[^A-Z0-9]", "", call.upper())


def city_key(city):
    c = re.sub(r"[^A-Z ]", "", city.upper().replace("SAINT ", "ST ").replace("ST. ", "ST "))
    return re.sub(r"\s+", " ", c).strip()


def read_csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


def load():
    lot = read_csv("lot_fcc08-3_appendix_a.csv")
    registry = {r["facility_id"]: r for r in read_csv("registry_fcc_2026-11-05.csv")}
    timeline = defaultdict(list)
    for r in read_csv("cdbs_call_sign_timeline_2024-01-09.csv"):
        timeline[r["facility_id"]].append(r)
    websites = defaultdict(list)
    for r in read_csv("wikidata_websites_2026-11-05.csv"):
        websites[r["facility_id"]].append(r["website"])
    return lot, registry, timeline, websites


# ---------- evidence ------------------------------------------------------------------------

def holdings(fid, timeline, registry):
    """Every call sign a facility has carried, as (call, start, end, source) intervals.

    start/end are ISO dates or '' when the record has no date. A call sign registered today
    that differs from the frozen CDBS record started after CDBS_FROZEN; its exact date is not
    in our extracts, so its start is kept as a bound ('>2023-10-01')."""
    rows = sorted(timeline.get(fid, []), key=lambda r: int(r["seq"]))
    out = []
    for i, r in enumerate(rows):
        # End at the next dated entry. If an undated entry sits in between, the call sign ended
        # at or before that date ('<YYYY-MM-DD'), so a date before it is not proof.
        later = rows[i + 1:]
        nxt = next((x["effective_date"] for x in later if x["effective_date"]), "")
        gap = bool(later) and not later[0]["effective_date"]
        end = ("<" + nxt) if (gap and nxt) else nxt
        out.append((r["call_sign"], r["effective_date"], end, r["source"]))
    today = registry.get(fid)
    if today and rows and call_key(today["call_sign"]) != call_key(rows[-1]["call_sign"]):
        last = out.pop()
        out.append((last[0], last[1], ">" + CDBS_FROZEN, last[3]))
        out.append((today["call_sign"], ">" + CDBS_FROZEN, "", "registry_today"))
    return out


def held_on(interval, date):
    """'yes' when dated records place the call sign on this facility on that date,
    'undated' when the record could fit but has no start date, 'no' otherwise."""
    call, start, end, _ = interval
    if end and not end.startswith(">") and end.lstrip("<") <= date:
        return "no"
    if end.startswith("<") and start and start <= date:
        return "undated"
    if start.startswith(">"):
        return "no" if date <= start[1:] else "undated"
    if not start:
        return "undated"
    return "yes" if start <= date else "no"


def call_on(fid, date, timeline, registry):
    """The call sign CDBS gives this facility on that date, whatever the line says."""
    for iv in holdings(fid, timeline, registry):
        v = held_on(iv, date)
        if v == "yes":
            return iv[0]
        if v == "undated":
            return f"{iv[0]} (no start date)"
    return ""


# ---------- the two rules -------------------------------------------------------------------

def candidates_today(key, service, state, registry):
    return [f for f in registry.get("_by_key", {}).get(key, ())
            if (state is None or f["state"] == state)
            and (service is None or f["service"] == service)]


def place_of(fid, timeline, registry):
    """State used to filter candidates: today's registry when the facility is still licensed, else CDBS."""
    return registry[fid]["state"] if fid in registry else timeline[fid][0]["cdbs_state"]


def candidates_dated(key, service, state, timeline, registry, index):
    found = []
    for fid in index.get(key, ()):
        rows = timeline[fid]
        if service is not None and rows[0]["cdbs_service"] != service:
            continue
        if state is not None and place_of(fid, timeline, registry) != state:
            continue
        for iv in holdings(fid, timeline, registry):
            if call_key(iv[0]) == key:
                verdict = held_on(iv, LIST_DATE)
                if verdict != "no":
                    found.append((fid, verdict, iv))
    return found


def where(fid, timeline, registry):
    """Name both places when CDBS and today's registry disagree."""
    t = timeline[fid][0]
    cdbs = f"{t['cdbs_service']} in {t['cdbs_city'].title()}, {t['cdbs_state']} per CDBS"
    r = registry.get(fid)
    if r and (r["state"], city_key(r["city"])) != (t["cdbs_state"], city_key(t["cdbs_city"])):
        cdbs += f", licensed in {r['city'].title()}, {r['state']} in the {SNAPSHOT} registry"
    return cdbs


def decide(line, rule, require_city, accept_undated, registry, timeline, index, websites):
    key, service = parse_printed_call(line["printed_call"])
    base = {"line_id": line["line_id"], "page": line["page"], "printed_call": line["printed_call"],
            "city": line["city"], "state": line["state"], "rule": rule, "require_city": require_city,
            "accept_undated": accept_undated, "facility_id": "", "candidates": "",
            "call_of_facility_on_list_date": "", "call_today": "", "service": "", "city_today": "",
            "state_today": "", "website_declared_by_wikidata": ""}
    if service in ("TV", "translator", "booster"):
        kind = {"TV": "television", "translator": "FM translator", "booster": "FM booster"}[service]
        return {**base, "decision": "Out of scope", "reason": f"{kind}; this version covers full-power AM and FM"}

    svc = f"{service} " if service else ""
    if rule == "today":
        cands = candidates_today(key, service, line["state"], registry)
        ids = [c["facility_id"] for c in cands]
        if not ids:
            elsewhere = candidates_today(key, None, None, registry)
            if elsewhere:
                return {**base, "decision": "Review", "candidates": " ".join(c["facility_id"] for c in elsewhere),
                        "reason": f"no {svc}facility in {line['state']} carries {key} today; "
                                  + "; ".join(f"{c['facility_id']} does, {c['service']} in {c['city'].title()}, {c['state']}"
                                              for c in elsewhere)}
            return {**base, "decision": "No candidate in this snapshot",
                    "reason": f"no facility carries {key} in the {SNAPSHOT} registry"}
        if len(ids) > 1:
            return {**base, "decision": "Review", "candidates": " ".join(ids),
                    "reason": f"{len(ids)} facilities carry {key} today"}
        fid, evidence = ids[0], f"carries {cands[0]['call_sign']} in the {SNAPSHOT} registry"
    else:
        found = candidates_dated(key, service, line["state"], timeline, registry, index)
        sure = sorted({f for f, v, _ in found if v == "yes"})
        loose = sorted({f for f, v, _ in found if v == "undated"} - set(sure))
        if not found:
            loose_any = {f: v for f, v, _ in candidates_dated(key, None, None, timeline, registry, index)}
            if loose_any:
                said = "; ".join(f"{f} {'did' if v == 'yes' else 'may have (no start date)'}, {where(f, timeline, registry)}"
                                 for f, v in sorted(loose_any.items()))
                return {**base, "decision": "Review", "candidates": " ".join(sorted(loose_any)),
                        "reason": f"our history extract places no {svc}{key} in {line['state']} on {LIST_DATE}; {said}"}
            return {**base, "decision": "No candidate in this snapshot",
                    "reason": f"our history extract places {key} on no facility on {LIST_DATE}"}
        if len(sure) > 1 or (not sure and len(loose) > 1):
            ids = sure or loose
            return {**base, "decision": "Review", "candidates": " ".join(ids),
                    "reason": f"{len(ids)} facilities could have carried {key} on {LIST_DATE}"}
        if not sure:
            fid = loose[0]
            iv = next(iv for f, v, iv in found if f == fid)
            others = [f for f in index.get(key, ()) if f != fid and place_of(f, timeline, registry) == line["state"]]
            if not accept_undated or others:
                why = f"facility {fid} carried {iv[0]} but the record has no start date"
                if others:
                    why += f"; facility {' '.join(sorted(others))} also carried it at some point"
                return {**base, "decision": "Review", "candidates": fid, "reason": why}
            evidence = (f"CDBS: {iv[0]} with no start date, until {iv[2].replace('<', 'at most ') or 'today'}; "
                        f"no other facility in {line['state']} appears with that call sign in this extract")
        else:
            fid = sure[0]
            iv = next(iv for f, v, iv in found if f == fid and v == "yes")
            evidence = f"CDBS: {iv[0]} effective {iv[1]}, until {iv[2].replace('<', 'at most ') or 'today'}"
        if fid not in registry:
            st = timeline[fid][0]["cdbs_status"]
            return {**base, "decision": "No candidate in this snapshot", "candidates": fid,
                    "reason": f"facility {fid} carried {iv[0]} on {LIST_DATE} but is not in the {SNAPSHOT} registry (CDBS status {st})"}
    f = registry[fid]
    out = {**base, "facility_id": fid, "call_of_facility_on_list_date": call_on(fid, LIST_DATE, timeline, registry),
           "call_today": f["call_sign"], "service": f["service"], "city_today": f["city"], "state_today": f["state"],
           "website_declared_by_wikidata": " ".join(sorted(set(websites.get(fid, []))))}
    if require_city and city_key(f["city"]) != city_key(line["city"]):
        return {**out, "decision": "Review", "candidates": fid,
                "reason": f"city of license is {f['city'].title()} today, {line['city']} on the list ({evidence})"}
    return {**out, "decision": "Linked", "reason": evidence}


def run(rule="dated", require_city=False, accept_undated=False, data=None):
    lot, registry, timeline, websites = data or load()
    index = defaultdict(set)
    for fid, rows in timeline.items():
        for r in rows:
            index[call_key(r["call_sign"])].add(fid)
    by_key = defaultdict(list)
    for fid, f in registry.items():
        by_key[call_key(f["call_sign"])].append(f)
        if fid in timeline:
            index[call_key(f["call_sign"])].add(fid)
    registry = {**registry, "_by_key": by_key}
    return [decide(l, rule, require_city, accept_undated, registry, timeline, index, websites) for l in lot]


# ---------- grading, kept apart: the rules above never read the answers -----------------------

def answers():
    return {r["line_id"]: r["facility_id_printed"] for r in read_csv("answers_fcc08-3_appendix_a.csv")}


def grade(decisions, registry):
    truth_of = answers()
    c = Counter()
    for d in decisions:
        truth = truth_of[d["line_id"]]
        k = d["decision"]
        c[k] += 1
        if k == "Linked":
            c["Linked, right facility" if d["facility_id"] == truth else "Linked, wrong facility"] += 1
        if k == "Review":
            c["Review, right facility among candidates" if truth in d["candidates"].split() else "Review, right facility not offered"] += 1
        if k == "No candidate in this snapshot":
            c["No candidate, facility gone from registry" if truth not in registry else "No candidate, facility still registered"] += 1
    c["Lines"] = len(decisions)
    c["In scope"] = len(decisions) - c["Out of scope"]
    return dict(c)


def mismatches_fate(today, other):
    """What another rule does with the lines the today rule links to the wrong facility."""
    truth_of = answers()
    fate = Counter()
    for t, o in zip(today, other):
        truth = truth_of[t["line_id"]]
        if t["decision"] == "Linked" and t["facility_id"] != truth:
            if o["decision"] == "Linked":
                fate["corrected" if o["facility_id"] == truth else "still wrong"] += 1
            elif o["decision"] == "Review":
                fate["flagged for review"] += 1
            else:
                fate[o["decision"]] += 1
    return dict(fate)


ORDER = ["Lines", "Out of scope", "In scope", "Linked", "Linked, right facility", "Linked, wrong facility",
         "Review", "Review, right facility among candidates", "Review, right facility not offered",
         "No candidate in this snapshot", "No candidate, facility gone from registry",
         "No candidate, facility still registered"]


def table(g):
    return "\n".join(f"{k:<44}{g.get(k, 0):>6}" for k in ORDER)


def changes(a, b):
    return [(x, y) for x, y in zip(a, b) if (x["decision"], x["facility_id"]) != (y["decision"], y["facility_id"])]


def read_previous(path):
    if not path.exists():
        return None
    with open(path, newline="") as fh:
        return {r["line_id"]: r for r in csv.DictReader(fh)}


def since_previous(prev, ds):
    return [(prev[d["line_id"]], d) for d in ds
            if d["line_id"] in prev and (prev[d["line_id"]]["decision"], prev[d["line_id"]]["facility_id"]) != (d["decision"], d["facility_id"])]


def show(x):
    return f"{x['decision']} {x['facility_id']}".strip()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--rule", choices=["today", "dated"], default="dated")
    p.add_argument("--accept-undated", action="store_true",
                   help="link on a call sign with no recorded start date when no other facility in the state appears with it")
    p.add_argument("--require-city", action="store_true", help="the city of license today must agree with the list")
    p.add_argument("--compare", action="store_true", help="show the lines that change between the today and dated rules")
    p.add_argument("--out", default=str(HERE / "out" / "decisions.csv"), help="where to write the decisions")
    p.add_argument("--page-json", help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    data = load()
    registry = data[1]
    if a.page_json:
        write_page_json(a.page_json, data)
        return
    if a.compare:
        t = run("today", a.require_city, False, data)
        d = run("dated", a.require_city, a.accept_undated, data)
        ch = changes(t, d)
        fate = mismatches_fate(t, d)
        print(f"{len(ch)} lines change when the rule moves from 'today' to 'dated'"
              f"{' (undated records accepted)' if a.accept_undated else ''}.")
        print(f"Of the {sum(fate.values())} lines 'today' links to a facility other than the printed one, "
              f"'dated' corrects {fate.get('corrected', 0)} and flags {fate.get('flagged for review', 0)} for review.")
        for x, y in ch:
            print(f"  {x['line_id']} {x['printed_call']:<10} {x['city']}, {x['state']}: "
                  f"{show(x)} -> {show(y)}  ({y['reason']})")
        return
    ds = run(a.rule, a.require_city, a.accept_undated, data)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    prev = read_previous(out)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ds[0].keys()))
        w.writeheader()
        w.writerows(ds)
    print(f"rule={a.rule} accept_undated={a.accept_undated} require_city={a.require_city} list date={LIST_DATE}")
    print(table(grade(ds, registry)))
    print(f"decisions: {out}")
    if prev is None:
        print("first run: run again after changing a rule to see which lines move")
        return
    moved = since_previous(prev, ds)
    print(f"{len(moved)} lines changed since the previous run")
    for x, y in moved:
        print(f"  {y['line_id']} {y['printed_call']:<10} {y['city']}, {y['state']}: {show(x)} -> {show(y)}  ({y['reason']})")


CODES = {"Linked": "L", "Review": "R", "No candidate in this snapshot": "N", "Out of scope": "O"}
STATES = [("today", False), ("dated", False), ("dated", True)]


def write_page_json(path, data):
    """The page shows the same decisions, for the three rule states it offers."""
    lot, registry = data[0], data[1]
    truth_of = answers()
    out = {"list_date": LIST_DATE, "snapshot": SNAPSHOT,
           "lines": [[l["line_id"], l["printed_call"], l["city"], l["state"], truth_of[l["line_id"]], l["page"]] for l in lot],
           "combos": {}}
    runs = {f"{r}|{int(u)}": run(r, False, u, data) for r, u in STATES}
    for key, ds in runs.items():
        out["combos"][key] = {
            "grade": grade(ds, registry),
            "fate": mismatches_fate(runs["today|0"], ds),
            "d": [[CODES[d["decision"]], d["facility_id"], d["candidates"], d["reason"]] for d in ds]}
    Path(path).write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
