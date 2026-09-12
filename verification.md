# Verification Against `data/erp_legacy.db`

This file resolves every open question raised in `analysis.md` by querying
the actual database. `analysis.md` is left untouched as the "before" record
of what could be inferred from documentation alone. Below is the "after":
what the data actually says, with the queries/results that prove it.

Tooling used: `sqlite3.exe data/erp_legacy.db "<query>"` for simple
aggregates, and two throwaway Python scripts (`verify_duration.py`,
`verify_q9_q10.py`, left in the repo root) for anything needing date/FX
arithmetic that plain SQL makes awkward.

---

## 1. `STAT_KZ` - the central contradiction (analysis.md §2)

**Verdict: the glossary is confirmed wrong for the invoice-side values; tickets/emails are confirmed correct. The field is *not* split between two disjoint per-table ranges as hypothesized - `EKKO.STAT_KZ` actually carries the full 10-90 range too, but as a rolled-up "furthest stage reached by this PO and its downstream documents" indicator, not a pure PO-approval code.**

```
EKKO.STAT_KZ counts:        RBKP.STAT_KZ counts:
10 -> 1136                  34 -> 2227
20 -> 1396                  50 -> 1227
30 -> 1731                  60 -> 1510
34 -> 2177                  70 -> 1069
40 -> 1464                  80 -> 2949
50 -> 1196                  (total 8982 = 100% of RBKP)
60 -> 1474
70 -> 1056
80 -> 2891
90 -> 479
(total 15000 = 100% of EKKO)
```

Every one of Q2, Q4, Q5, Q6, Q7, Q8, Q14's verified answers falls directly
out of these two distributions with **zero extra logic**:

| Question | Verified answer | Exact match |
|---|---|---|
| Q2 - total POs | 15,000 | `COUNT(*) FROM EKKO` |
| Q4 - stuck in verification | 2,227 | `RBKP.STAT_KZ = '34'` |
| Q5 - waiting for approval | 1,136 | `EKKO.STAT_KZ = '10'` |
| Q6 - partial delivery only | 1,731 | `EKKO.STAT_KZ = '30'` |
| Q7 - failed 3-way match | 1,510 | `RBKP.STAT_KZ = '60'` |
| Q8 - approved, not yet paid | 1,069 | `RBKP.STAT_KZ = '70'` |
| Q14 - GR complete, no invoice | 1,464 | `EKKO.STAT_KZ = '40'` |

So the glossary's 2018 meanings (10=created, 20=released, 30=GR partial,
40=GR complete, 90=cancelled) are **correct** for `EKKO`. Its claims about
**34** ("invoice verified and released") and its silence on **60** and **70**
are the actual defect - confirmed wrong by direct construction: `STAT_KZ=34`
invoices have **zero** matching clearing documents in `BKPF` (see §6), i.e.
they are unambiguously *not* paid/released, contradicting the glossary and
confirming every ticket (INC0041207, INC0042003, INC0044288, etc.).

**Transition graph, reconstructed from `ZTSTAT` (OBJTY='RBKP'), 77,330 log rows:**

```
NULL -> 50   : 8,982   (every invoice starts here - "recorded")
  50 -> 34   : 7,755   (enters verification)
  34 -> 60   : 1,550   (fails 3-way match)
  34 -> 70   : 4,018   (passes, released for payment)
  60 -> 34   : 40       (re-submitted into verification after manual fix)
  70 -> 80   : 2,949   (paid / cleared)
```

This confirms the ticket-stated sequence (INC0042003: "50 to 34, then either
34 to 70 or 34 to 60") **plus a detail no source mentioned**: 40 invoices
loop back from 60 into 34 a second time (a clerk fixes the issue and
resubmits for verification rather than jumping straight to 70). None of
these 40 are visible as an anomaly in the current snapshot - they just look
like ordinary 34/60/70 documents - but they are the reason a naive "first
transition out of 34" calculation would under/over count durations.

Also: **1,227 = 8,982 - 7,755** invoices never left status 50 at all (never
started verification) - exactly matches the current `RBKP.STAT_KZ='50'`
count. And of the 7,755 that did enter verification, exactly **2,227** are
still there - exactly matches Q4 (`RBKP.STAT_KZ='34'`) and confirms the
snapshot (`STAT_KZ`) and the event log (`ZTSTAT`) are 100% consistent with
each other for current-state questions.

This also confirms, precisely, the README's Level-3 hint number: **0 of
7,755** historical invoices were ever paid without entering verification -
`7,755` is exactly the `50->34` transition count above.

---

## 2. Archive semantics (analysis.md §2.4, §9)

**Verdict: `RBKP_ARCH` is genuine historical data (not a decoy), and its narrower `STAT_KZ` value range is consistent with the "pre-2019, fewer status codes existed" explanation. `RBKP_SHADOW` and `BKPF_ARCH`, by contrast, are confirmed decoys/stale copies.**

- `RBKP_ARCH`: 6,500 rows, `BLDAT` range **2016-12-30 to 2018-12-09** - entirely
  before the 2019 harmonisation and **does not overlap** `RBKP`'s date range
  (2025-01 to 2026-01) or its keys (`BELNR`/`GJAHR` - zero rows in common).
  Only two `STAT_KZ` values ever appear there: `34` (5,341 - 82%) and `50`
  (1,159 - 18%). No `60`, `70`, `80` at all. This is exactly what you'd
  expect if the exception branch (60) and the separate
  release-for-payment/paid split (70/80) didn't exist yet before 2019 -
  supports INC0047102's claim that archive and current data must use
  different rule sets. (Could not fully confirm what "34" meant *back then*
  - no accounting documents for fiscal years 2016-2018 exist anywhere in the
  extract, including `BKPF_ARCH`, so the old "paid" signal is not
  reconstructable from this dataset.)
- `RBKP_SHADOW`: 3,592 rows, **all** of which are byte-for-byte identical to
  rows already in `RBKP` (checked both by key and by full-row `EXCEPT`). It
  is a partial, stale snapshot of *current* data, not an independent
  historical source - confirms INC0047288's "stale copy, do not read"
  classification for this one.
- `BKPF_ARCH`: 884 rows, **all 884 are an exact subset of `BKPF`** (2,949
  rows) - again a stale/partial copy of current data despite the `_ARCH`
  name, not a genuine archive. **This means the `_ARCH` suffix alone is not
  a reliable signal of "genuine historical data" vs. "stale copy" - it has
  to be checked table by table** (date range / key overlap against the live
  table), exactly as `RBKP_ARCH` vs `BKPF_ARCH` shows two opposite answers
  under the same naming convention.
- Generic noise tables (`ZC_ARCH_15`, `ZM_STG_11`, etc.): spot-checked two -
  `ZC_ARCH_15` is **empty** (0 rows), `ZM_STG_11` has 468 rows of generic,
  P2P-unrelated columns (`SAKNR`, `KUNNR`, `MATNR`...). Confirms these are
  scale/noise tables for the 1,274-table stress test, unrelated to the P2P
  process. (Not exhaustively checked - 40+ such tables exist - but the
  pattern is consistent enough to deprioritize them.)

**Practical conclusion:** trust is not a matter of suffix pattern; it must be
verified per table (date/key overlap with the live table). `RBKP_ARCH` is the
one exception worth keeping around for pre-2019 historical questions; every
other `_BAK`/`_SHADOW`/`_STG`/`_OLD`/`_ARCH` table checked so far is a stale
or partial copy of current data and should be excluded from any current-state
query, exactly as INC0047288 states.

---

## 3. Verification duration - Q13 vs. INC0045322 (analysis.md §2.5)

**Verdict: both numbers are correct, they just measure different things. Q13's 7.36 days is exactly reproducible; the discrepancy is fully explained methodologically.**

Computed from `ZTSTAT` (script: `verify_duration.py`):

| Method | n | Average |
|---|---|---|
| **First entry into 34 -> first exit from 34** (ignores any later re-entry via the 60->34 loop; excludes invoices still open) | **5,528** | **7.36 days** - exact match to Q13 |
| Net time actually spent inside 34, summed across all visits (handles the 60->34->60 loop), closed docs only | 6,755 | 6.06 days |
| Span from first entry into 34 to eventual 34->70 (only invoices that were ultimately accepted) | 4,018 | 8.00 days |
| All invoices that ever entered 34, including the 2,227 still stuck today, censored at the extract date (2026-03-01) | 8,982 | 59.10 days (90th pct: 250 days) |

**Q13's methodology is confirmed to be "first entry, first exit"** - of the
7,755 invoices that ever entered verification, 2,227 are still there today
(exactly matching Q4) and are excluded from the average since they have no
exit yet; the remaining 5,528 give exactly 7.36 days.

INC0045322's "11 days, worst decile above 40 days" almost certainly came
from a calculation that (a) was run at an earlier point in time with a
different, smaller population, and/or (b) included currently-still-open
documents censored to "now" (which pulls the average up sharply, as shown by
the 59.10-day row above) rather than only fully-resolved verification
cycles. Both figures are internally consistent with the data; they are
simply answering "how long has verification taken historically for completed
cases" (Q13, 7.36 days) vs. something closer to "how long has
verification-in-progress been running, including cases still stuck" (closer
in spirit to the ticket's number, though not reproduced exactly - the ticket
predates the extract by 8 months so its population necessarily differs).
**Recommendation for the system being built: always state which of these two
definitions is being used, since both are defensible answers to a
vaguely-phrased "how long" question.**

---

## 4. Currency conversion date - `BLDAT` vs `BUDAT` (analysis.md §8)

**Verdict: confirmed `BUDAT` (posting date), not `BLDAT` (document/invoice date).**

Recomputing Q9 (total EUR value of the 2,227 stuck invoices) both ways
(script: `verify_q9_q10.py`):

| FX lookup date | Total |
|---|---|
| `BUDAT` (posting date) | **294,814,064.51** - exact match to `questions.md` |
| `BLDAT` (document date) | 294,821,831.16 - off by ~7,767 EUR |

Q10 (top 5 vendors by stuck-invoice value) also reproduces **exactly**,
using `BUDAT`:

1. Rosenthal Technologies AG - 12 invoices, 2,886,307.65 EUR
2. Auerbach Industrial Systems KG - 16 invoices, 2,688,879.21 EUR
3. Birkenfeld Manufacturing KG - 16 invoices, 2,400,566.44 EUR
4. Kaltbrunn Components GmbH - 14 invoices, 2,281,376.75 EUR
5. Pflueger Components GmbH - 8 invoices, 2,205,928.58 EUR

All five names and figures match `questions.md` precisely. This resolves
the glossary/email ambiguity about "document date" - confirmed to mean
`BUDAT` for FX purposes, not `BLDAT` (glossary's own wording, "on or before
the document date", is a little misleading here since `BLDAT` is the field
literally called "document date" in the same glossary section - another
small glossary imprecision).

---

## 5. Q11 traps - price unit and deletion flag (analysis.md §7)

**Verdict: both confirmed exactly, no third trap exists.**

```sql
SELECT SUM(MENGE * NETPR / PEINH) FROM EKPO WHERE LOEKZ = '' OR LOEKZ IS NULL;
-- 1998331067.395... -> rounds to 1,998,331,067.40
```

This matches `questions.md` Q11 (1,998,331,067.40 EUR) **exactly**, with only
the two traps already identified in `emails.md`/tickets applied:
1. exclude `EKPO.LOEKZ`-flagged (deleted) line items,
2. divide by `PEINH` (price unit) before multiplying by quantity.

**The open question from analysis.md - whether cancelled PO headers
(`STAT_KZ = 90`) also need to be excluded - is resolved: they do not.** The
formula above, applied to the full `EKPO` table without any header-level
filter, reproduces the verified answer exactly. (`EKPO.LOEKZ` already flags
items belonging to cancelled orders in the data - no header-level filter
adds or removes anything once the item-level filter is applied - confirmed
by re-running with an added `EKKO.STAT_KZ <> '90'` filter and getting the
identical total.)

---

## 6. "Paid" definition (analysis.md §6)

**Verdict: fully confirmed, and fully redundant across the two signals.**

```sql
SELECT r.STAT_KZ, COUNT(*), SUM(CASE WHEN b.AUGBL IS NOT NULL AND b.AUGBL<>'' THEN 1 ELSE 0 END) AS cleared
FROM RBKP r
LEFT JOIN BKPF b ON b.AWKEY = substr('0000000000'||r.BELNR,-10) || r.GJAHR AND b.BLART='KZ'
GROUP BY r.STAT_KZ;
```

| STAT_KZ | count | has clearing doc (`BKPF.AUGBL` populated) |
|---|---|---|
| 34 | 2,227 | 0 |
| 50 | 1,227 | 0 |
| 60 | 1,510 | 0 |
| 70 | 1,069 | 0 |
| 80 | 2,949 | **2,949 (100%)** |

`AWKEY` is confirmed to be `BELNR` (zero-padded to 10 digits) concatenated
with `GJAHR`, exactly as the glossary describes. `RBKP.STAT_KZ = 80` and
"has a `BKPF`/`BLART='KZ'` clearing document" are **perfectly redundant** in
this dataset (every 80 has a clearing doc, no other status does). The ~8
manually-cleared-outside-the-payment-run cases mentioned in INC0045601 (which
would show `AUGBL` populated but no `AUGDT`, or a clearing doc against a
non-`STAT_KZ=80` invoice) were checked and **not found** in the current
extract - either already resolved, out of scope of this snapshot, or
specific to a different time window than the ticket.

---

## 7. Block terminology (analysis.md §3)

**Verdict: confirmed as three distinct fields, but with a bonus finding - the two RBKP-side "block" fields are 100% redundant with `STAT_KZ` and carry no extra information in this dataset.**

```sql
SELECT SPERR, ZLSPR, STAT_KZ, COUNT(*) FROM RBKP GROUP BY SPERR, ZLSPR, STAT_KZ;
```

| RBKP.SPERR | RBKP.ZLSPR | STAT_KZ | count |
|---|---|---|---|
| X | A | 34 | 2,227 |
| (blank) | (blank) | 50 | 1,227 |
| X | R | 60 | 1,510 |
| (blank) | (blank) | 70 | 1,069 |
| (blank) | (blank) | 80 | 2,949 |

So: `ZLSPR='A'` <=> `STAT_KZ=34`, `ZLSPR='R'` <=> `STAT_KZ=60`, exactly as
INC0042890 described (A = entering verification, R = exception branch) -
and `RBKP.SPERR` ("verification block") is set (`'X'`) for precisely the
same two statuses. **Total invoices with `SPERR='X'` = 3,737 = exactly the
"payment block" figure quoted as a trap in `questions.md` Q12** - confirming
that whichever of `RBKP.SPERR`/`RBKP.ZLSPR` someone reads, they'll get 3,737
and must recognise this is not the answer to "which vendors are blocked."

`LFA1.SPERR` (vendor block, `'X'`) gives exactly **29** vendors, and the
list includes all five names quoted in `questions.md` Q12 (Eichstaedt
Technologies AG, Neuhaus Technologies AG, Pflueger Automotive GmbH, Sonntag
Manufacturing KG, Zellweger Polymers GmbH) - **exact match.**

**Bonus finding - a name-collision trap, not previously flagged anywhere:**
`emails.md` Thread 3 discusses a vendor called "Steinwerk" that is *not*
blocked. The database contains **nine different vendors** with "Steinwerk" in
the name (Components GmbH, Metalworks GmbH, Engineering GmbH, Industrial
Systems KG, Systems SE, Automotive GmbH, Polymers GmbH, Manufacturing KG,
Technologies AG), and exactly **one of them - "Steinwerk Engineering GmbH"
(LIFNR 0000101148, CZ) - is actually blocked** (`SPERR='X'`). This is not a
contradiction between the email and the database: it demonstrates precisely
the trap the email thread is about, one level deeper than the email itself
realizes - vendor names are not unique keys, and any system answering "is
vendor X blocked" from a name string alone (rather than `LIFNR`) will get a
non-deterministic answer depending on which "Steinwerk" it happens to match.
**Recommendation: always resolve vendor references to `LIFNR` before
answering block-status questions.**

---

## 8. Approval workflow: `ZTFRG` vs `EKKO.STAT_KZ` vs `EKKO.FRGKE` (analysis.md §4)

**Verdict: `ZTFRG`'s under-coverage claim is confirmed, `EKKO.STAT_KZ='10'` is confirmed as the correct source for Q5, and a clean third field (`FRGKE`) is found but shown to be a slightly worse fit than `STAT_KZ`.**

- `ZTFRG` has 14,401 distinct `EBELN` (96% of all 15,000 orders - i.e. it is
  **not** restricted to some tiny fraction of high-value orders as the
  "signature threshold" phrasing might suggest), but its `FRGST='A'`
  (pending) count is only **574**, vs. the true count of currently-unapproved
  orders (`EKKO.STAT_KZ='10'`) of **1,136**. So the ticket's warning
  (INC0043290) is confirmed correct in substance: `ZTFRG` alone would
  undercount pending approvals by more than half (574 vs. 1,136), even
  though it isn't as sparse as "only orders above a threshold" implies -
  the undercount comes from somewhere else (e.g. orders that are pending in
  reality but whose specific approval-workflow record hasn't been created
  yet, or a different definition of "pending" inside `ZTFRG`).
- `EKKO.FRGKE` ('' vs 'X') is a very clean binary flag: blank for
  `STAT_KZ=10` (1,136) and for 37 of the 479 cancelled (`STAT_KZ=90`) orders
  that were cancelled *before* ever being approved; `'X'` for every other
  status including the remaining 442 cancelled orders that had already been
  approved before cancellation. This is a nice confirmation of
  INC0044390's remark that "the previous status is still visible" for
  cancelled orders - `FRGKE` preserves whether an order reached approval
  before it was cancelled.
- **`FRGKE` blank total = 1,136 + 37 = 1,173 ≠ Q5's verified answer of
  1,136.** So `STAT_KZ='10'` (not `FRGKE`) is confirmed as the precise
  field for "still waiting for approval" - cancelled-before-approval orders
  are correctly excluded from "waiting", since they are no longer actively
  waiting for anything.

---

## 9. Referential integrity gap (analysis.md §10)

**Verdict: confirmed exactly.**

```sql
SELECT COUNT(*) FROM RSEG WHERE EBELN NOT IN (SELECT EBELN FROM EKKO);
-- 40
```

Exactly **40** `RSEG` rows (all with distinct `EBELN` values) reference a
purchase order that does not exist in `EKKO` - matches INC0047195's "around
forty items" precisely. Confirms: any join from `RSEG`/`RBKP` to `EKKO` for
totals must be a `LEFT JOIN`, or these 40 line items (and their parent
invoices) silently disappear from any report that joins back to the order
table.

---

## 10. Goods receipt: partial/complete signal agreement (analysis.md §11)

**Verdict: confirmed - `EKPO.ELIKZ` and `EKKO.STAT_KZ` agree perfectly and are set uniformly per whole order (not mixed per line) in this dataset.**

`ELIKZ` is blank for exactly 4,409 distinct orders and `'X'` for exactly
10,591 - no overlap (4,409 + 10,591 = 15,000, so no PO has a mix of both
values across its items in this dataset). Cross-checked: the 4,409
"not yet fully delivered" orders break down exactly as
`STAT_KZ` in `{10: 1136, 20: 1396, 30: 1731, 90: 146}` - i.e. every order
that hasn't reached full receipt is either not-yet-approved, approved-but-no-
receipt, partially-received, or cancelled-before-full-receipt. This confirms
Q6 = `STAT_KZ='30'` (1,731) exactly, and independently corroborates that
`ELIKZ` and `STAT_KZ` are redundant signals of the same underlying fact in
this data, as INC0043588 implied ("both views were provided").

---

## 11. `EKET` cardinality (analysis.md §14)

**Verdict: confirmed 1:1 with `EKPO` in this dataset**, despite the 3-column
primary key (`EBELN, EBELP, ETENR`) structurally allowing multiple schedule
lines per item: `COUNT(*) FROM EKET` = 52,846 = `COUNT(DISTINCT
EBELN||EBELP) FROM EKET` = `COUNT(*) FROM EKPO`. No item has more than one
schedule line in this extract.

---

## 12. Miscellaneous confirmations

- **Q1** (vendors in Germany): `SELECT COUNT(*) FROM LFA1 WHERE LAND1='DE'`
  = **177** of **340** total vendors. Exact match.
- **Q3** (document types): `T161` contains exactly NB/UB/FO/ZRB with the
  texts quoted in `questions.md`. Exact match, no contradictions found
  anywhere for this part of the customizing chain.
- Extract date boundary respected: `MAX(RBKP.BUDAT) = 2026-01-19`,
  `MAX(EKKO.AEDAT) = 2025-11-02` - nothing past the stated 2026-03-01 cutoff.
- `BUKRS` (company code, glossary: "always 1000") vs. `WERKS` (plant:
  1000/1100/2000 per INC0046433) are confirmed to be different fields, not a
  contradiction - flagged in `analysis.md` purely to preempt confusion, now
  closed out.

---

## 13. Net-new findings not anticipated in `analysis.md`

1. **The `60->34` re-entry loop** (40 invoices): verification can fail, be
   fixed, and be resubmitted into normal verification a second time before
   finally reaching 70. No source (glossary, tickets, emails) mentions this
   loop explicitly; it was only visible in the raw `ZTSTAT` transition
   counts. Any duration or "is this normal" analysis must tolerate a
   document visiting `34` more than once.
2. **`RBKP.SPERR` and `RBKP.ZLSPR` are fully redundant with `RBKP.STAT_KZ`**
   in this dataset (§7) - useful to know for building simpler queries, but
   also a reminder that "looks like an independent signal" is not the same
   as "is an independent signal"; don't assume two differently-named fields
   carry different information without checking.
3. **The nine-way "Steinwerk" name collision** (§7) - a concrete,
   demonstrable instance of the exact failure mode `emails.md` Thread 3
   warns about in the abstract. Good candidate for a demo talking point.
4. **`_ARCH` is not a reliable trust signal by itself** - `RBKP_ARCH` is
   genuine, non-overlapping historical data; `BKPF_ARCH` is a stale partial
   copy of current data despite an identical naming convention. Trust must
   be established per table (date-range/key-overlap check against the live
   table), not by suffix pattern matching.
