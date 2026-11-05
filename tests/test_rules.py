"""python3 -m unittest discover tests"""
import ast, csv, json, subprocess, sys, tempfile, unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import reconcile as R  # noqa: E402

DATA = R.load()


def line(call, city, state, line_id="T1"):
    return {"line_id": line_id, "page": 0, "printed_call": call, "city": city, "state": state}


def decide_one(l, rule, accept_undated=False, require_city=False, registry=None, timeline=None):
    lot, reg, tl, web = DATA
    reg = registry if registry is not None else reg
    tl = timeline if timeline is not None else tl
    return R.run(rule, require_city, accept_undated, ([l], reg, tl, web))[0]


def fac(fid, call, state="WA", city="SEATTLE", service="FM"):
    return {"facility_id": fid, "call_sign": call, "service": service, "status": "LICENSED",
            "city": city, "state": state, "frequency": "", "active": "Y"}


def hist(fid, *entries, service="FM", state="WA"):
    rows = []
    for i, (call, date) in enumerate(entries, 1):
        rows.append({"facility_id": fid, "seq": str(i), "call_sign": call, "effective_date": date,
                     "source": "cdbs_current" if i == len(entries) else "cdbs_history",
                     "cdbs_service": service, "cdbs_city": "SEATTLE", "cdbs_state": state, "cdbs_status": "LICEN"})
    return rows


def cli(*args, cwd):
    return subprocess.run([sys.executable, str(ROOT / "reconcile.py"), *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


class TheList(unittest.TestCase):
    def test_every_facility_id_row_is_parsed(self):
        lot = DATA[0]
        self.assertEqual(len(lot), 1074)
        ids = [r["facility_id_printed"] for r in R.read_csv("answers_fcc08-3_appendix_a.csv")]
        self.assertEqual(len(set(ids)), 1074)

    def test_hard_rows_of_the_pdf(self):
        by_call = {r["printed_call"]: r for r in DATA[0]}
        self.assertEqual((by_call["WCRR(FM)"]["city"], by_call["WCRR(FM)"]["state"]), ("South Bristol Township", "NY"))
        self.assertEqual(by_call["WQUL(FM)"]["state"], "IL")           # printed "Il"
        self.assertEqual(by_call["K48JD"]["state"], "UT")               # state on the next line
        self.assertEqual(by_call["WRQK-FM"]["city"], "Canton")          # file number 20070906ADD

    def test_registry_and_wikidata_hold_only_real_facility_ids(self):
        self.assertTrue(all(int(f) > 0 for f in DATA[1]))
        self.assertEqual(len(DATA[1]), 16675)
        self.assertTrue(all(f.isdigit() for f in DATA[3]))


class PrintedCalls(unittest.TestCase):
    def test_suffixes_and_dirty_spacing(self):
        self.assertEqual(R.parse_printed_call("KUBE(FM)"), ("KUBE", "FM"))
        self.assertEqual(R.parse_printed_call("KJR(AM)"), ("KJR", "AM"))
        self.assertEqual(R.parse_printed_call("KJR-FM"), ("KJRFM", "FM"))
        self.assertEqual(R.parse_printed_call("WKEEFM"), ("WKEEFM", "FM"))
        self.assertEqual(R.parse_printed_call("WFLA- FM"), ("WFLAFM", "FM"))
        self.assertEqual(R.parse_printed_call("KPKY (FM)"), ("KPKY", "FM"))
        self.assertEqual(R.parse_printed_call("WVON(AM"), ("WVON", "AM"))

    def test_out_of_scope_services(self):
        self.assertEqual(R.parse_printed_call("KUCW(TV)")[1], "TV")
        self.assertEqual(R.parse_printed_call("K31AE")[1], "TV")
        self.assertEqual(R.parse_printed_call("K236AB")[1], "translator")
        self.assertEqual(R.parse_printed_call("KIOI-FM1")[1], "booster")


class SeattleCase(unittest.TestCase):
    """FCC 08-3 (2008-01-24) prints KJR-FM = 48385 and KUBE(FM) = 48387; today KJR-FM is 48387."""

    def test_today_rule_takes_the_wrong_facility_and_says_what_it_carried(self):
        d = decide_one(line("KJR-FM", "Seattle", "WA"), "today")
        self.assertEqual((d["decision"], d["facility_id"]), ("Linked", "48387"))
        self.assertEqual(d["call_of_facility_on_list_date"], "KUBE")

    def test_dated_rule_takes_the_facility_of_2008(self):
        d = decide_one(line("KJR-FM", "Seattle", "WA"), "dated")
        self.assertEqual((d["decision"], d["facility_id"]), ("Linked", "48385"))
        self.assertIn("2002-05-30", d["reason"])
        self.assertEqual((d["call_today"], d["call_of_facility_on_list_date"]), ("KJEB", "KJR-FM"))

    def test_kuul_stays_in_review(self):
        d = decide_one(line("KUUL(FM)", "East Moline", "IL"), "dated")
        self.assertEqual((d["decision"], d["candidates"]), ("Review", "60596"))


class Abstention(unittest.TestCase):
    def test_two_dated_holders_go_to_review(self):
        reg = {"1": fac("1", "KAAA"), "2": fac("2", "KAAA")}
        tl = defaultdict(list, {"1": hist("1", ("KAAA", "2000-01-01")), "2": hist("2", ("KAAA", "2001-01-01"))})
        d = decide_one(line("KAAA(FM)", "Seattle", "WA"), "dated", registry=reg, timeline=tl)
        self.assertEqual(d["decision"], "Review")
        self.assertEqual(set(d["candidates"].split()), {"1", "2"})

    def test_undated_record_is_review_unless_switched_on(self):
        reg = {"1": fac("1", "KBBB")}
        tl = defaultdict(list, {"1": hist("1", ("KBBB", ""))})
        l = line("KBBB(FM)", "Seattle", "WA")
        self.assertEqual(decide_one(l, "dated", registry=reg, timeline=tl)["decision"], "Review")
        self.assertEqual(decide_one(l, "dated", True, registry=reg, timeline=tl)["decision"], "Linked")

    def test_undated_record_stays_review_when_another_facility_carried_the_call(self):
        reg = {"1": fac("1", "KCCC"), "2": fac("2", "KXYZ")}
        tl = defaultdict(list, {"1": hist("1", ("KCCC", "")),
                                "2": hist("2", ("KCCC", "1990-01-01"), ("KXYZ", "1995-01-01"))})
        d = decide_one(line("KCCC(FM)", "Seattle", "WA"), "dated", True, registry=reg, timeline=tl)
        self.assertEqual(d["decision"], "Review")

    def test_undated_entry_in_the_middle_does_not_reopen_an_old_call_sign(self):
        """CDBS 55912: KGME 1994, an undated KFDJ, KCTK 1999. KGME ended by 1999 at the latest."""
        reg = {"1": fac("1", "KPXQ", service="AM"), "2": fac("2", "KGME", service="AM")}
        tl = defaultdict(list, {
            "1": hist("1", ("KGME", "1994-02-11"), ("KFDJ", ""), ("KCTK", "1999-10-12"), ("KPXQ", "1999-10-14"), service="AM"),
            "2": hist("2", ("KFYI", "1985-07-03"), ("KGME", "2000-09-26"), service="AM")})
        d = decide_one(line("KGME(AM)", "Seattle", "WA"), "dated", registry=reg, timeline=tl)
        self.assertEqual((d["decision"], d["facility_id"]), ("Linked", "2"))

    def test_facility_gone_today_is_no_candidate_with_its_reason(self):
        tl = defaultdict(list, {"9": hist("9", ("KDDD", "1999-01-01"))})
        d = decide_one(line("KDDD(FM)", "Seattle", "WA"), "dated", registry={}, timeline=tl)
        self.assertEqual(d["decision"], "No candidate in this snapshot")
        self.assertIn("not in the", d["reason"])

    def test_call_sign_taken_after_the_list_date_is_not_evidence(self):
        reg = {"1": fac("1", "KEEE")}
        tl = defaultdict(list, {"1": hist("1", ("KOLD", "1990-01-01"), ("KEEE", "2015-01-01"))})
        self.assertEqual(decide_one(line("KEEE(FM)", "Seattle", "WA"), "today", registry=reg, timeline=tl)["decision"], "Linked")
        self.assertEqual(decide_one(line("KEEE(FM)", "Seattle", "WA"), "dated", registry=reg, timeline=tl)["decision"],
                         "No candidate in this snapshot")

    def test_city_switch_sends_a_moved_station_to_review(self):
        reg = {"1": fac("1", "KFFF", city="TACOMA")}
        tl = defaultdict(list, {"1": hist("1", ("KFFF", "1990-01-01"))})
        d = decide_one(line("KFFF(FM)", "Seattle", "WA"), "dated", require_city=True, registry=reg, timeline=tl)
        self.assertEqual(d["decision"], "Review")

    def test_reason_names_both_states_when_they_disagree(self):
        d = decide_one(line("WUSW(FM)", "Hattiesburg", "MS"), "dated")
        self.assertEqual(d["decision"], "Review")
        self.assertIn("Hattiesburg, MS per CDBS", d["reason"])
        self.assertIn(", LA in the", d["reason"])


class Measures(unittest.TestCase):
    def test_what_the_dated_rule_does_with_the_mismatches(self):
        t, d = R.run("today", data=DATA), R.run("dated", data=DATA)
        self.assertEqual(R.grade(t, DATA[1])["Linked, wrong facility"], 32)
        self.assertEqual(R.mismatches_fate(t, d), {"corrected": 30, "flagged for review": 2})


class Separation(unittest.TestCase):
    def test_rules_never_read_the_answers(self):
        src = (ROOT / "reconcile.py").read_text()
        funcs = {n.name: ast.get_source_segment(src, n) for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
        for name in ("decide", "run", "candidates_today", "candidates_dated", "holdings", "call_on", "load"):
            self.assertNotIn("answers", funcs[name], name)

    def test_page_numbers_match_the_command(self):
        page = json.loads((ROOT / "site" / "data.json").read_text())
        self.assertEqual(set(page["combos"]), {"today|0", "dated|0", "dated|1"})
        for key, combo in page["combos"].items():
            rule, und = key.split("|")
            ds = R.run(rule, False, und == "1", DATA)
            self.assertEqual(combo["grade"], R.grade(ds, DATA[1]), key)


class Replay(unittest.TestCase):
    def test_a_second_run_lists_what_moved_since_the_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "decisions.csv")
            first = cli("--rule", "today", "--out", out, cwd=tmp)
            self.assertIn("first run", first)
            self.assertIn("Linked, wrong facility                          32", first)
            second = cli("--out", out, cwd=tmp)
            n = len(R.changes(R.run("today", data=DATA), R.run("dated", data=DATA)))
            self.assertIn(f"{n} lines changed since the previous run", second)
            with open(out, newline="") as fh:
                self.assertEqual(len(list(csv.DictReader(fh))), 1074)
            third = cli("--out", out, cwd=tmp)
            self.assertIn("0 lines changed since the previous run", third)

    def test_page_shows_the_real_command_output(self):
        html = (ROOT / "site" / "index.html").read_text()
        n = len(R.changes(R.run("today", data=DATA), R.run("dated", data=DATA)))
        self.assertIn(f"{n} lines changed since the previous run", html)
        self.assertIn(f"{len(tests_in_suite())} tests", html)


def tests_in_suite():
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    def walk(s):
        for t in s:
            yield from walk(t) if isinstance(t, unittest.TestSuite) else [t]
    return list(walk(suite))


if __name__ == "__main__":
    unittest.main()
