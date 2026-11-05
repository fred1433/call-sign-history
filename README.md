# Call sign history

An old line says `KJR-FM, Seattle, WA`. Two FCC facilities have carried that call sign: 48385 (now KJEB, 95.7 MHz) and 48387 (KJR-FM today, 93.3 MHz). KJR-FM moved from 48385 to 48387 on April 20, 2022. Matching the line on today's call sign picks the wrong one. This repository links the 1,074 station lines of a 2008 FCC order to FCC facilities with a rule you can change, and checks every decision against the facility ID printed in the order.

Page: https://theaipipe.com/demos/call-sign-history/

## Run it

```
python3 reconcile.py --rule today           # match on the call sign as registered today
python3 reconcile.py                        # match on the call sign as it stood on the list's date
python3 reconcile.py --accept-undated       # dated, and also link a call sign whose record has no start date,
                                            # when no other facility in the state appears with it in this extract
python3 reconcile.py --require-city         # also require today's city of license to agree
python3 reconcile.py --compare              # lines that change between the today and dated rules
python3 -m unittest discover tests          # 21 tests
```

Python 3.9 or later, standard library only. No model, no network, no API cost.

Each run writes `out/decisions.csv` and, if a previous run left one, prints the lines whose decision or facility changed since that run. Edit a rule in `reconcile.py`, run again, and you see what moved. From a fresh clone:

```
$ python3 reconcile.py --rule today
rule=today accept_undated=False require_city=False list date=2008-01-24
...
Linked, wrong facility                          32
...
first run: run again after changing a rule to see which lines move
$ python3 reconcile.py
rule=dated accept_undated=False require_city=False list date=2008-01-24
...
Linked, wrong facility                           0
...
359 lines changed since the previous run
  A0001 WDDD(AM)   Johnston City, IL: No candidate in this snapshot -> Review  (...)
```

(`...` marks lines cut here, not in the output.)

`out/decisions.csv` has one row per line: decision (`Linked`, `Review`, `No candidate in this snapshot`, `Out of scope`), facility, candidates when it abstains, reason, `printed_call` (as printed in 2008), `call_of_facility_on_list_date` (what CDBS says the chosen facility carried on 2008-01-24, which shows a wrong link for what it is), call sign today, service, city of license, and the website Wikidata declares for that facility (not checked).

## What it measures

The list is the broadcast table in Appendix A of FCC order 08-3 (Clear Channel transfer of control, released January 24, 2008; Appendix A corrected by the erratum of January 30, 2008, DOC-279887A1, whose Appendix A matches the copy used here line for line). The parser counts the rows with a facility ID before reading any city and stops if one is lost: 1,074 rows, 1,074 distinct IDs. The IDs sit in `data/answers_fcc08-3_appendix_a.csv`; the rules never read that file (a test checks it), only `grade()` does, after the decisions are made. 127 lines are television, translators or boosters and stay out of scope, leaving 947. Matching date: January 24, 2008.

| On 947 in-scope lines | today's call sign | call sign on the list's date | same, undated records accepted |
|---|---|---|---|
| Linked to the facility printed in 2008 | 748 | 742 | 918 |
| Linked to another facility | 32 | 0 | 0 |
| Flagged for review | 80 (printed facility among candidates: 11) | 202 (201) | 26 (25) |
| No candidate in this snapshot | 87 | 3 | 3 |

Of the 32 mismatches of the today rule, the dated rule corrected 30 and flagged 2 for review (WKOX, Framingham and KNEW, Oakland, where the record has no start date and another facility carried the call sign). The price is the review queue: 80 lines under the today rule, 202 under the dated one, with the printed facility among the candidates in 201 of those 202. Accepting undated records brings it down to 26 without adding a wrong link. 359 lines change between the today and dated rules, 192 with undated records accepted.

Among the mismatches: KJR-FM moved from 48385 to 48387 on April 20, 2022; WKOX and WXKS swapped facilities on March 1, 2010; WRLX and WZZR on June 1, 2020. Several Review lines come from errors printed in the 2008 list itself (a Nebraska station printed with state CA, an AM station printed as FM).

"Right" here means "agrees with the facility ID printed in FCC 08-3": a check against an FCC document, not against ground truth. One case shows the limit. The order prints KUUL(FM), East Moline, IL with 43208, and FCC public notice DA 06-2531 (December 20, 2006, page 35) already lists KUUL on 43208 and KGLX on 60596 (page 41). CDBS dates those call signs from June 29 and June 28, 2010. CDBS effective dates can therefore lag behind the call signs the FCC printed: KUUL stays in Review with 60596 as the only candidate, and KGLX(FM), Gallup finds no candidate.

## Sources (all public, frozen in `data/`)

| File | Source | Date |
|---|---|---|
| `lot_fcc08-3_appendix_a.csv`, `answers_...` | FCC 08-3, Appendix A, pages 19 to 41, broadcast table only (the Part 25 and Part 90/101 tables are left out). Copy in `site/sources/FCC-08-3A1.pdf`, from the Internet Archive capture `web.archive.org/web/20111017164241/http://hraunfoss.fcc.gov/edocs_public/attachmatch/FCC-08-3A1.pdf` (sha1 07b75492af3114402250c8940b98cff12cb7798d). Erratum: https://docs.fcc.gov/public/attachments/DOC-279887A1.pdf | released 2008-01-24, corrected 2008-01-30 |
| `registry_fcc_2026-11-05.csv` | FCC public inspection file service, every AM and FM facility (`publicfiles.fcc.gov/api/service/{am,fm}/facility/getall`, then `/facility/id/{id}`): 16,677 records, of which two test records with negative IDs (-11 AM123, -10 FM123) are removed, leaving 16,675 | 2026-11-05 |
| `cdbs_call_sign_timeline_2024-01-09.csv` | FCC CDBS `call_sign_history.zip` and `facility.zip`, AM and FM only. CDBS has not been updated since 2023-10-01, so a call sign changed after that date shows only as a different call sign today, without its day | file of 2024-01-09 |
| `wikidata_websites_2026-11-05.csv` | Wikidata (CC0): items with an FCC Facility ID (P1400) and an official website (P856); two non-numeric P1400 values are dropped. Used only to show a declared website; never used to decide or to grade | 2026-11-05 |

The FCC public notice of 13 August 2024 (report PN-1-240813-01, pages 15 and 107) independently shows KJR-FM on 48387 at 93.3 MHz and KJEB on 48385 at 95.7 MHz: https://docs.fcc.gov/public/attachments/DOC-404679A1.pdf

Order of the CDBS history: each facility's call signs are kept in the CDBS sequence order. Sorting them by effective date instead was tested: it changes one decision of 1,074 (KGME(AM), Phoenix), because an undated entry in the middle of facility 55912's history left an old KGME interval open. The fix kept here is narrower: an interval ends at the next dated entry, and when an undated entry sits in between, a date before that end is treated as undated evidence. KGME now links to the printed 65480 under the dated rule.

`tools/build_extracts.py` rebuilds `data/` from the raw downloads.

## Change a rule

The two rules are `candidates_today` and `candidates_dated` in `reconcile.py`; `decide` turns candidates into a decision and a reason. Change one, run `python3 reconcile.py` again, and the lines that moved since the previous run are listed with their new reason.

Built by Frederic de Lavenne de Choulot, The AI Pipe. https://cal.theaipipe.com
