"""python3 -m unittest discover tests"""
import ast, json, subprocess, sys, tempfile, unittest
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


class PrintedCalls(unittest.TestCase):
    def test_suffixes_and_dirty_spacing(self):
        self.assertEqual(R.parse_printed_call("KUBE(FM)"), ("KUBE", "FM"))
        self.assertEqual(R.parse_printed_call("KJR(AM)"), ("KJR", "AM"))
        self.assertEqual(R.parse_printed_call("KJR-FM"), ("KJRFM", "FM"))
        self.assertEqual(R.parse_printed_call("WKEEFM"), ("WKEEFM", "FM"))
        self.assertEqual(R.parse_printed_call("WFLA- FM"), ("WFLAFM", "FM"))
        self.assertEqual(R.parse_printed_call("KPKY (FM)"), ("KPKY", "FM"))

    def test_out_of_scope_services(self):
        self.assertEqual(R.parse_printed_call("KUCW(TV)")[1], "TV")
        self.assertEqual(R.parse_printed_call("WHP-TV")[1], "TV")
        self.assertEqual(R.parse_printed_call("K236AB")[1], "translator")


class SeattleCase(unittest.TestCase):
    """FCC 08-3 (2008-01-24) prints KJR-FM = 48385 and KUBE(FM) = 48387; today KJR-FM is 48387."""

    def test_today_rule_takes_the_wrong_facility(self):
        d = decide_one(line("KJR-FM", "Seattle", "WA"), "today")
        self.assertEqual((d["decision"], d["facility_id"]), ("Linked", "48387"))

    def test_dated_rule_takes_the_facility_of_2008(self):
        d = decide_one(line("KJR-FM", "Seattle", "WA"), "dated")
        self.assertEqual((d["decision"], d["facility_id"]), ("Linked", "48385"))
        self.assertIn("2002-05-30", d["reason"])
        self.assertEqual(d["call_today"], "KJEB")

    def test_kube_line_follows_its_facility(self):
        d = decide_one(line("KUBE(FM)", "Seattle", "WA"), "dated")
        self.assertEqual(d["facility_id"], "48387")


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

    def test_facility_gone_today_is_no_candidate_with_its_reason(self):
        reg = {}
        tl = defaultdict(list, {"9": hist("9", ("KDDD", "1999-01-01"))})
        d = decide_one(line("KDDD(FM)", "Seattle", "WA"), "dated", registry=reg, timeline=tl)
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


class Separation(unittest.TestCase):
    def test_rules_never_read_the_answers(self):
        tree = ast.parse((ROOT / "reconcile.py").read_text())
        funcs = {n.name: ast.get_source_segment((ROOT / "reconcile.py").read_text(), n)
                 for n in tree.body if isinstance(n, ast.FunctionDef)}
        for name in ("decide", "run", "candidates_today", "candidates_dated", "holdings", "load"):
            self.assertNotIn("answers", funcs[name], name)

    def test_page_numbers_match_the_command(self):
        page = json.loads((ROOT / "site" / "data.json").read_text())
        for key, combo in page["combos"].items():
            rule, und = key.split("|")
            ds = R.run(rule, False, und == "1", DATA)
            self.assertEqual(combo["grade"], R.grade(ds, DATA[1]), key)

    def test_command_runs_from_the_repo(self):
        with tempfile.TemporaryDirectory():
            out = subprocess.run([sys.executable, str(ROOT / "reconcile.py"), "--rule", "today"],
                                 capture_output=True, text=True, check=True).stdout
        self.assertIn("Linked, wrong facility", out)


if __name__ == "__main__":
    unittest.main()
