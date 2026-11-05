# Call sign history

An old line says `KJR-FM, Seattle, WA`. Two FCC facilities have carried that call sign: 48385 (now KJEB, 95.7 MHz) and 48387 (KJR-FM today, 93.3 MHz). Matching the line on today's call sign picks the wrong one. This repository links 1,068 real lines to FCC facilities with a rule you can change, and checks every decision against the answer printed in the source.

Page: https://theaipipe.com/demos/call-sign-history/

## Run it

```
python3 reconcile.py --compare              # lines that change between the two rules, with the reason
python3 reconcile.py --rule today           # match on the call sign as registered today
python3 reconcile.py                        # match on the call sign as it stood on the list's date
python3 reconcile.py --accept-undated       # also link a call sign whose record has no start date,
                                            # when no other facility in the state ever carried it
python3 reconcile.py --require-city         # also require today's city of license to agree
python3 -m unittest discover tests          # 14 tests
```

Python 3.9 or later, standard library only. No model, no network, no API cost. Each run writes `out/decisions.csv`: one row per line with its decision (`Linked`, `Review`, `No candidate in this snapshot`, `Out of scope`), the facility, the candidates when it abstains, the reason, the call sign on the list's date and today, service, city of license, and the website Wikidata declares for that facility (not checked).

## What it measures

The list is Appendix A of FCC order 08-3 (Clear Channel transfer of control, released 24 January 2008): 1,068 lines, each printed with its facility ID. The IDs sit in `data/answers_fcc08-3_appendix_a.csv`; the rules never read that file (a test checks it), only `grade()` does, after the decisions are made. 123 lines are television, translators or boosters and stay out of scope, leaving 945.

| On 945 in-scope lines | today's call sign | call sign on the list's date | same, plus undated records |
|---|---|---|---|
| Linked to the facility printed in 2008 | 749 | 740 | 916 |
| Linked to the wrong facility | 32 | 0 | 0 |
| Review (candidates and reason given) | 77 | 202 | 26 |
| No candidate in this snapshot | 87 | 3 | 3 |

The 32 wrong links are call signs that moved after 2008, several of them swapped between two facilities on the same list (KJR-FM and KUBE in Seattle, WKOX and WXKS near Boston, WRLX and WZZR in Florida). The dated rule abstains instead of guessing when the record has no start date or when two facilities fit; several of its Review lines come from errors printed in the 2008 list itself (a Nebraska station printed with state CA, an AM station printed as FM).

"Right" here means "agrees with the facility ID printed in FCC 08-3". It is a check against an FCC document, not against ground truth: one line (KUUL, East Moline) is printed with a call sign that CDBS gives to that facility only from 2010, and the dated rule sends it to Review.

## Sources (all public, frozen in `data/`)

| File | Source | Date |
|---|---|---|
| `lot_fcc08-3_appendix_a.csv`, `answers_...` | FCC 08-3, Appendix A, pages 19 to 41 (copy in `site/sources/FCC-08-3A1.pdf`) | released 2008-01-24 |
| `registry_fcc_2026-11-05.csv` | FCC public inspection file service, every AM and FM facility (`publicfiles.fcc.gov/api/service/{am,fm}/facility/getall`, then `/facility/id/{id}`): 16,677 facilities | 2026-11-05 |
| `cdbs_call_sign_timeline_2024-01-09.csv` | FCC CDBS `call_sign_history.zip` and `facility.zip`, AM and FM only. CDBS has not been updated since 2023-10-01, so a call sign changed after that date shows only as a different call sign today, without its day | file of 2024-01-09 |
| `wikidata_websites_2026-11-05.csv` | Wikidata (CC0): items with an FCC Facility ID (P1400) and an official website (P856). Used only to show a declared website; never used to decide or to grade | 2026-11-05 |

The FCC public notice of 13 August 2024 (report PN-1-240813-01, pages 15 and 107) independently shows KJR-FM on 48387 at 93.3 MHz and KJEB on 48385 at 95.7 MHz: https://docs.fcc.gov/public/attachments/DOC-404679A1.pdf

`tools/build_extracts.py` rebuilds `data/` from the raw downloads.

## Change a rule

The two rules are `candidates_today` and `candidates_dated` in `reconcile.py`; `decide` turns candidates into a decision and a reason. Change one, run `python3 reconcile.py --compare`, and the lines that moved are listed with their new reason.

Built by Frederic de Lavenne de Choulot, The AI Pipe. https://cal.theaipipe.com
