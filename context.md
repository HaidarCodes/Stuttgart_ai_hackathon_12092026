# Context Pack - Purchase-to-Pay Legacy ERP

**Purpose of this file:** a single, self-contained semantic layer for a
system that turns business-language questions into correct, provenanced
answers against `data/erp_legacy.db` (1,274 tables, SQLite). It consolidates
`analysis.md` (what the documentation says) and `verification.md` (what the
database actually does), and adds new research into the ~1,260 tables that
are *not* part of the hand-picked 14-table extract, so the same system can
plausibly work when the crutch of `schema.sql` is taken away.

**Source-tagging convention used throughout:** every claim below is tagged
with where it came from, so provenance can be reproduced:
- `[glossary §N]` = `context/GLOSSARY.md`, official but partly outdated data catalogue
- `[process §N]` = `context/PROCESS.md`, business-language process description
- `[ticket INC0xxxxx]` = `context/tickets.jsonl`
- `[email Thread N]` = `context/emails.md`
- `[questions.md QN]` = the verified calibration answer
- `[DB: <query summary>]` = confirmed by directly querying `data/erp_legacy.db` (this session)
- `[README]` / `[deck pN]` = `README.md` / `powerpoint.pdf` (task brief)

Where a documentation source and the database disagree, the database wins,
and both sides are shown - this is the entire point of the exercise
`[README]`.

---

## 0. The task, in one paragraph

Build a "system of context" on top of a 20-year-old ERP replica so that
business questions like *"which supplier invoices are stuck, how much money
is tied up, and why?"* can be answered correctly, at scale (against all 1,274
tables, not just a hand-picked 14-table extract), live, with visible
provenance for every number `[README]` `[deck p2-p5]`. The deck's own
demonstration of the failure mode: the same underlying question, answered
naively straight from the schema, produces **394,630,962,907 EUR** instead of
the correct **1,998,331,067 EUR** - a factor of 197, caused by exactly the
two traps documented in §6 below `[deck p3]`.

---

## 1. The trustworthy core: 14 tables, what they mean, and what they actually contain

These are the tables named in `data/schema.sql`, picked by a colleague "by
hand... not guaranteed to be complete" `[README]`. All 14 exist unchanged
inside `data/schema_full.sql` as well.

### LFA1 - vendor master
| Field | Meaning | Notes |
|---|---|---|
| `LIFNR` | Vendor number, 10 digits, zero-padded | PK `[glossary §1]` |
| `NAME1` | Vendor name | **Not unique** - `[DB]` found 9 different vendors all containing "Steinwerk" in the name; only 1 of them is blocked. Never resolve a vendor by name alone, always by `LIFNR`. |
| `LAND1` | Country (ISO) | `[glossary §1]`. `[DB]`: 177 of 340 vendors have `LAND1='DE'` - exact match to `questions.md` Q1. |
| `ORT01` | City | `[glossary §1]` |
| `SPERR` | **Vendor block** - blocks all future business with this vendor, company-wide, set centrally by Vendor Master Data, "usually for compliance reasons" `[glossary §1]` `[email Thread 3]`. Values seen: `''` / `'X'`. `[DB]`: exactly 29 vendors have `SPERR='X'`, matching `questions.md` Q12 exactly, including all 5 named vendors in that answer. |
| `ERDAT` | Creation date | `[glossary §1]` |
| `KTOKK` | Account group | `[glossary §1]`, not used in any resolved question |

**Important - do not confuse with:** `RBKP.SPERR` and `RBKP.ZLSPR` below,
which are named similarly but are entirely different concepts (see §5).

### MARA - material master
| Field | Meaning | Notes |
|---|---|---|
| `MATNR` | Material number, 18 digits | PK `[glossary §2]` |
| `MTART` | Material type | `ROH`=raw material, `HALB`=semi-finished `[glossary §2]`. `[DB]`: of 2,000 materials, 1,374 `ROH` / 626 `HALB` - only these two types exist. |
| `MATKL` | Material group | `[glossary §2]`, unused in resolved questions |
| `MEINS` | Base unit of measure | `[glossary §2]` |
| `MAKTX` | Short text | `[glossary §2]` |
| `LVORM` | **Material master** deletion flag | `[glossary §2]`. **Trap, found via `[DB]`, not documented anywhere in the context sources:** this is a *different* concept from `EKPO.LOEKZ` (deleted order line). 85 of 2,000 materials have `LVORM='X'`, and **2,043 non-deleted `EKPO` line items still reference a material that is itself flagged `LVORM='X'`** in the master. A material being "marked for deletion" (stop using going forward) does not retroactively invalidate historical order items that already reference it. Do not filter `EKPO` by `MARA.LVORM` when computing historical order values - only `EKPO.LOEKZ` matters for that (see §6). |

### EKKO - purchase order header
| Field | Meaning | Notes |
|---|---|---|
| `EBELN` | PO number, PK | `[glossary §3]`. `[DB]`: exactly 15,000 rows - matches `questions.md` Q2 with zero filtering needed. |
| `BUKRS` | Company code | "always 1000" `[glossary §3]`. Not the same thing as plant (`WERKS`, see MSEG/EKPO) - `[DB]` confirms plants are `1000`/`1100`/`2000` `[ticket INC0046433]`, a different field entirely; this is *not* a contradiction, just two similarly-numbered but distinct fields. |
| `BSART` | Document type | See `T161` below. `[DB]` confirmed the 4 types in `questions.md` Q3 (`NB`, `UB`, `FO`, `ZRB`) exist exactly. |
| `LIFNR` | Vendor | `[glossary §3]` |
| `EKGRP` | Purchasing group | `[glossary §3]`, "organisational assignment of the responsible buyer, not relevant for status evaluation" `[ticket INC0044788]`. `[DB]`: exactly 9 groups (`001`-`009`), evenly distributed (1,609-1,714 orders each). Not used by any resolved question, but present and clean - usable for a "by purchasing group" breakdown if asked (e.g. the open approval-bottleneck request in `[ticket INC0046844]`). No separate purchasing-group description/master table exists anywhere in the 1,274 tables `[DB]` - only the 3-digit code. |
| `WAERS` | Document currency | `[glossary §3]`. `[DB]`: `EUR`/`USD`/`CNY` observed on the invoice side; needs `TCURR` conversion for any cross-currency total (§7). |
| `AEDAT` | Creation date | `[glossary §3]` |
| `ERNAM` | Created by | `[glossary §3]`, not resolved further |
| `FRGKE` | Release indicator | `[glossary §3]`. `[DB]`: a clean binary flag (`''`/`'X'`). Blank exactly for `STAT_KZ='10'` (1,136) plus 37 of the 479 cancelled orders that were cancelled *before* ever being approved; `'X'` for every other status, including the 442 cancelled orders that *had* been approved before cancellation. **This is a worse fit for "still waiting for approval" than `STAT_KZ='10'`** (1,136+37=1,173 ≠ Q5's verified 1,136) - use `STAT_KZ`, not `FRGKE`, for that question. `FRGKE` is still useful to distinguish "never got that far" vs "was approved, then cancelled" for cancelled orders. |
| `STAT_KZ` | **Status indicator - the central concept of this dataset.** | See §4. |

### EKPO - purchase order item
| Field | Meaning | Notes |
|---|---|---|
| `EBELN`, `EBELP` | PO number + item number, composite PK | `[glossary §3]` |
| `MATNR` | Material | `[glossary §3]` |
| `WERKS` | Plant | `[glossary §3]`. `[DB]`: exactly `1000`/`1100`/`2000`, matching `[ticket INC0046433]`. |
| `MENGE` | Order quantity | `[glossary §3]` |
| `NETPR` | Net price **per price unit**, not per piece | `[glossary §3]`. **Trap** - see §6. |
| `PEINH` | Price unit | `[glossary §3]`. Often 100 or 1000 for C-parts `[email Thread 2]`. |
| `ELIKZ` | Delivery-completed indicator | `[glossary §3]`. `[DB]`: perfectly correlated with `EKKO.STAT_KZ` - blank exactly for orders with header status in `{10,20,30,90}` (4,409 orders), `'X'` for the rest (10,591). No PO mixes both values across its items in this data. Redundant with header status here, but is the item-level signal `[ticket INC0043588]` calls for. |
| `LOEKZ` | Deletion indicator | `[glossary §3]`. **Trap** - a cancelled/deleted line stays physically in the table, only flagged - see §6. |

### EKET - schedule lines
| Field | Meaning | Notes |
|---|---|---|
| `EBELN`, `EBELP`, `ETENR` | Composite PK | `[glossary "not yet documented"]`, clarified in `[ticket INC0045888]`: "one entry per item in our configuration" |
| `EINDT` | Agreed delivery date | `[ticket INC0045888]` |
| `MENGE` | Scheduled quantity | |

`[DB]` confirmed: exactly 1:1 with `EKPO` in this dataset (52,846 = 52,846 =
52,846 distinct `EBELN`+`EBELP` pairs) even though the 3-column PK
structurally allows multiple schedule lines per item. Nobody should assume
this generalises to a future extract with genuine multi-schedule-line items.

### MKPF / MSEG - goods receipt (material document header/item)
| Field | Meaning | Notes |
|---|---|---|
| `MBLNR`, `MJAHR` | Material doc number + fiscal year, PK on MKPF | `[glossary §4]` |
| `BWART` | Movement type | 101 = goods receipt against a PO `[glossary §4]` `[ticket INC0043712]`. **`[DB]` confirms `MSEG.BWART` contains *only* the value `'101'`** in this entire extract - no reversals, returns, or other movement types exist. A duration/quantity calculation does not need to handle reversals here, but should not silently assume this holds on a future/larger extract. |
| `EBELN`, `EBELP` | Link back to the PO | `[glossary §4]` |
| `ERFMG`, `ERFME` | Received quantity + unit | schema.sql |
| `SHKZG` | Debit/credit indicator | Flagged as undocumented in `[glossary "not yet documented"]`. **`[DB]` resolves it: the column is constant (`'S'`) across every row of both `MSEG` and `RSEG` in this dataset** - it carries no discriminating information here. Do not build logic on it without re-checking on a different extract. |

### RBKP - invoice header
| Field | Meaning | Notes |
|---|---|---|
| `BELNR`, `GJAHR` | Invoice document number + fiscal year, PK | `[glossary §5]` |
| `LIFNR` | Vendor | `[glossary §5]` |
| `BLDAT` | **Document date** - the date printed on the invoice | `[glossary §5]` |
| `BUDAT` | **Posting date** | `[glossary §5]`. **This is the field to use for currency conversion**, not `BLDAT` - `[DB]` confirmed Q9's verified total (294,814,064.51 EUR) reproduces exactly only with `BUDAT`; using `BLDAT` gives 294,821,831.16 (off by ~7.8k EUR). |
| `RMWWR` | Gross invoice amount, document currency | `[glossary §5]`. `[DB]`: reconciles exactly to `SUM(RSEG.WRBTR)` for every single invoice in the table (0 mismatches) - confirms `[ticket INC0044903]`'s claim. |
| `SPERR` | **Verification block** (not the same as `LFA1.SPERR`!) | `[glossary §5]` `[ticket INC0043012]`. `[DB]`: fully redundant with `STAT_KZ` in this data - `'X'` exactly and only when `STAT_KZ` is `34` or `60` (3,737 rows total - the same number quoted as a trap in `questions.md` Q12). |
| `ZLSPR` | **Payment block** | `[glossary §5]`, value range originally undocumented, resolved by `[ticket INC0042890]`: `A` = auto-set entering verification, `R` = set when verification fails. `[DB]` confirms exactly: `ZLSPR='A'` iff `STAT_KZ=34` (2,227 rows), `ZLSPR='R'` iff `STAT_KZ=60` (1,510 rows), blank otherwise. No other values exist. |
| `USNAM`, `XBLNR` | User, reference doc number | Flagged undocumented `[glossary]`; not needed for any resolved question, not further investigated. |
| `STAT_KZ` | Status indicator | See §4. |

### RSEG - invoice item
| Field | Meaning | Notes |
|---|---|---|
| `BELNR`, `GJAHR`, `BUZEI` | Composite PK | `[glossary §5]` |
| `EBELN`, `EBELP` | Link to PO item | `[glossary §5]`. `[ticket INC0046155]`: confirmed every invoice item in this process has a PO reference - non-PO invoices are out of scope, handled elsewhere. |
| `MATNR`, `MENGE`, `WRBTR` | Material, quantity, item amount | schema.sql |
| `SHKZG` | Constant `'S'` in this data | see MSEG note above |

**Cardinality, `[DB]` confirmed:** in this dataset each PO has **at most one**
linked invoice (no `EBELN` joins to more than one distinct `RBKP.BELNR` via
`RSEG`) - a much simpler 1:0/1:1 relationship than a typical live ERP.
8,982 of the 15,000 POs have an invoice; the rest do not (yet, or ever).

**Known gap, `[ticket INC0047195]`, `[DB]` confirmed exactly:** exactly **40**
`RSEG` rows reference an `EBELN` that does not exist in `EKKO` (a batch of old
orders was moved out of the live order table during migration while their
invoice items stayed behind). **Any join from `RSEG`/`RBKP` back to `EKKO`
must be a `LEFT JOIN`**, or these 40 line items (and their invoices) silently
disappear from a report.

### BKPF - accounting document header
| Field | Meaning | Notes |
|---|---|---|
| `BUKRS`, `BELNR`, `GJAHR` | Composite PK | schema.sql |
| `BLART` | Document type | `[DB]`: only value present is `'KZ'` (payment run document) `[glossary §7]` - no other accounting document types exist in this extract. |
| `AWKEY` | Reference back to the originating invoice-verification document | `[glossary §7]`. `[DB]` confirmed the exact format: `BELNR` zero-padded to 10 digits, concatenated with `GJAHR` (e.g. `RBKP.BELNR='0005100005'`, `GJAHR='2025'` -> `AWKEY='00051000052025'`). |
| `AUGBL`, `AUGDT` | Clearing document number / date | "An item counts as cleared once `AUGBL` is populated" `[glossary §7]`. `[DB]` confirmed: **every** `RBKP.STAT_KZ='80'` invoice (2,949 of them) has a matching `BKPF` row with `BLART='KZ'` and a populated `AUGBL`, and **no** invoice with any other status does. Fully redundant with `STAT_KZ=80` in this dataset. |
| `DMBTR` | Amount | schema.sql |

The ~8 "manually cleared outside the payment run, missing clearing date"
cases mentioned in `[ticket INC0045601]` were searched for via `[DB]` and
**not found** in the current extract (0 rows with `AUGBL` populated and
`AUGDT` blank) - either already resolved by extract time, or specific to a
different period than this snapshot covers.

### ZTFRG - release/approval workflow (in-house table, undocumented in the glossary)
| Field | Meaning | Notes |
|---|---|---|
| `FRGID` | PK | schema.sql |
| `EBELN` | PO | schema.sql |
| `FRGST` | `A` = approval pending, `F` = approval granted | `[ticket INC0043404]` |
| `FRGCO` | Approval level/code | `[DB]`: values seen are `'01'` and `'A'` - **inconsistent coding for what looks like the same concept**, not documented or explained anywhere; treat with caution if used. |
| `FRGDT` | Approval date | column name, self-explanatory; not used by any resolved question but plausibly the field needed for an "approval bottleneck" analysis (`[ticket INC0046844]`, still open as of the extract) |
| `FRGUS` | Approver user | `[DB]` sample values look like real usernames (`K_MUELLER`, `M_KELLER`, `S_WEBER`, `T_SCHMIDT` - the same names that appear as authors in `emails.md`) |
| `FRGBE` | Free text, `'Release granted'` / `'Pending approval'` | `[DB]`, purely a redundant human-readable mirror of `FRGST` |

**Coverage caveat, `[ticket INC0043290]`, `[DB]` confirmed:** `ZTFRG` covers
14,401 of 15,000 orders (96% - *not* a tiny fraction restricted to
high-value orders, contrary to what "signature threshold" might suggest),
but its `FRGST='A'` (pending) count is only **574**, while the true count of
currently-unapproved orders (`EKKO.STAT_KZ='10'`) is **1,136**. So `ZTFRG`
alone undercounts pending approvals by more than half. **Always use
`EKKO.STAT_KZ='10'` for "orders waiting for approval", never `ZTFRG` alone**,
exactly as the ticket warns, even though the coverage gap isn't quite where
the ticket's wording implies.

### ZTSTAT - status change log (in-house table, undocumented in the glossary, but the single most authoritative source in the whole database)
| Field | Meaning |
|---|---|
| `LOGID` | PK, also usable as a tiebreaker for same-timestamp events |
| `OBJTY` | Object type - only `EKKO` and `RBKP` occur `[DB]` |
| `OBJKY` | Object key (`EBELN` or `BELNR`) |
| `STAT_ALT`, `STAT_NEU` | Previous / new `STAT_KZ` value |
| `CPUDT`, `CPUTM` | Date/time of the transition |
| `USNAM` | User who made the change (or `RFC_MM01`, a technical/interface user, `[ticket INC0045190]`) |

`[email Thread 5]`: "If you need to know what a status value actually means
today, look at the logging table... That sequence is the truth." This is
confirmed empirically over and over in `verification.md` - every current
`STAT_KZ` distribution and every duration figure was independently
reproduced from `ZTSTAT`.

**Full transition graph for `OBJTY='RBKP'`, `[DB]`, 77,330 log rows total:**
```
NULL -> 50 : 8,982   (every invoice starts here)
  50 -> 34 : 7,755   (enters verification)
  34 -> 60 : 1,550   (fails 3-way match)
  34 -> 70 : 4,018   (passes, released for payment)
  60 -> 34 :    40   (re-submitted into verification after a manual fix - never mentioned in any documentation source, only visible in the raw log)
  70 -> 80 : 2,949   (paid)
```
**Edge case, `[ticket INC0046701]`, `[DB]` confirmed present in the data:**
a handful of documents have two transitions with an *identical* timestamp
(verification completed within the same nightly batch window as the
following step) - any duration calculation must tolerate zero-length
intervals and use `LOGID` as a tiebreaker, not assume strictly increasing
timestamps between consecutive events for the same document.

### T161 - PO document type customizing
`BSART` -> `BATXT`. `[DB]` confirmed exact content: `NB`=Standard purchase
order, `UB`=Stock transport order, `FO`=Blanket purchase order,
`ZRB`=Scheduling agreement release `[glossary §8]` `[ticket INC0045477]`,
matching `questions.md` Q3 exactly. No other document types exist.

### TCURR - exchange rates
`FCURR` (from-currency) -> `TCURR` (to-currency, always `EUR` here) with
`GDATU` (valid-from date) and `UKURS` (rate). Rule: "the applicable rate is
the most recent one valid on or before the document date" `[glossary §8]`
`[email Thread 4]` `[ticket INC0042744]` - **confirmed via `[DB]` that "document
date" means `RBKP.BUDAT`, not `BLDAT`** (see RBKP section above). `[DB]`:
rates exist for `USD` and `CNY` quarterly from 2025-01-01 through
2025-10-01; no rate exists after that, but the "most recent rate on or
before" rule naturally extrapolates forward with no gap, confirmed against
the latest invoice `BUDAT` of 2026-01-19.

---

## 2. Business vocabulary <-> field mapping

`[process §1-§3]` describes the process without naming a single table or
field - this section is the bridge, cross-checked against tickets/emails and
the database.

```
Demand -> Purchase order -> Approval -> Goods receipt -> Invoice verification -> Payment release -> Payment
```

| Business term | Field-level definition | Source(s) |
|---|---|---|
| "sitting in the approval queue" / "waiting for release" | `EKKO.STAT_KZ = '10'` | `[process §2.2]` `[ticket INC0043290]` `[DB: exact match to Q5]` |
| "partial delivery" | `EKKO.STAT_KZ = '30'` (header) or `EKPO.ELIKZ = ''` (item) | `[process §2.3]` `[ticket INC0043588]` `[DB: exact match to Q6]` |
| "open receipts" (partials that never complete) | orders stuck at `STAT_KZ='30'` for an extended time - no fixed threshold documented anywhere; would need a duration cut similar to Q13's methodology if asked | `[process §2.3]` |
| "recorded" (invoice) | `RBKP.STAT_KZ = '50'` | `[ticket INC0046290]` |
| **"stuck" / "in verification"** | `RBKP.STAT_KZ = '34'` - recorded, entered verification, not yet approved for payment, not yet paid | `[process §2.4]` `[email Thread 1]` `[ticket INC0044001]` `[DB: exact match to Q4]` |
| "failed three-way match" / needs a clerk | `RBKP.STAT_KZ = '60'` | `[ticket INC0041766]` `[ticket INC0045744]` `[DB: exact match to Q7]` |
| "released for payment" | `RBKP.STAT_KZ = '70'` | `[ticket INC0042188]` `[DB: exact match to Q8]` |
| **"paid"** | `RBKP.STAT_KZ = '80'`, equivalently a `BKPF` row exists with `BLART='KZ'` and populated `AUGBL`, linked via `AWKEY` | `[ticket INC0044512]` `[glossary §7]` `[DB: 100% agreement between the two signals]` |
| "vendor block" | `LFA1.SPERR = 'X'` | `[process §3]` `[email Thread 3]` |
| "verification block" | `RBKP.SPERR = 'X'` | `[process §3]` `[ticket INC0043012]` |
| "payment block" | `RBKP.ZLSPR IN ('A','R')` | `[process §3]` `[ticket INC0042890]` |
| "GR complete, never invoiced" (GR/IR case) | `EKKO.STAT_KZ = '40'` with no `RSEG` row for that `EBELN` | `[ticket INC0045044]` `[DB: exact match to Q14, and the header-status shortcut alone already gives the same 1,464 without even checking RSEG]` |
| "three-way match" | (1) invoice references a valid PO (`RSEG.EBELN` exists in `EKKO`), (2) goods were received (`MSEG` with `BWART='101'` for that `EBELN`/`EBELP`), (3) quantity/price agree between `EKPO`, `MSEG`, `RSEG` | `[process §2.4]`; the precise agree/disagree comparison logic itself was not reverse-engineered field-by-field, only its outcome (`STAT_KZ=60` on failure) - see §9 "still open" |

---

## 3. `STAT_KZ` - full resolution of the central contradiction

**The claim in `[glossary §6]`** (last revision 2018): `STAT_KZ` values are
10=PO created, 20=PO released, 30=GR partial, **34=invoice verified and
released**, 40=GR complete, 50=invoice recorded, 80=process completed,
90=cancelled - with a margin note admitting the 2019 harmonisation added
values not covered here.

**The reality, `[DB]` confirmed exhaustively:**

```
EKKO.STAT_KZ  (15,000 rows total)     RBKP.STAT_KZ  (8,982 rows total)
  10 -> 1,136   PO created, unapproved      34 -> 2,227   in verification (NOT released!)
  20 -> 1,396   PO approved, no GR yet      50 -> 1,227   recorded, not yet in verification
  30 -> 1,731   partial GR                  60 -> 1,510   failed 3-way match (exception branch)
  34 -> 2,177   (mirrors invoice progress)  70 -> 1,069   released for payment
  40 -> 1,464   GR complete, no invoice     80 -> 2,949   paid
  50 -> 1,196
  60 -> 1,474
  70 -> 1,056
  80 -> 2,891
  90 ->   479   cancelled
```
`EKKO.STAT_KZ` is a **rolled-up "furthest stage reached" indicator per PO**
that spans the entire chain (creation through payment), not a pure
PO-approval code - it carries every downstream invoice-side value too. This
was not hypothesized correctly in `analysis.md` (which guessed `EKKO` only
used `{10,20,30,40,90}`) and was corrected by `[DB]` query.

**The glossary is confirmed wrong specifically about `34`** (it is the
opposite of "verified and released" - it means "currently stuck, unpaid") and
**silent about `60` and `70`**, which are central to current processing.
Every ticket that discusses this (`INC0041207`, `INC0041766`, `INC0042003`,
`INC0044288`, `INC0046290`) and both relevant email threads (`Thread 1`,
`Thread 5`) independently corroborate the database, and the glossary's own
margin note in `[glossary §6]` admits the risk. **This is very likely the
"confidently wrong" source the case brief refers to** `[README]`.

**Archived data uses a narrower, pre-harmonisation value range** - see §8.

---

## 4. Two numeric traps (the "factor 197" / "hundreds of billions" failure)

Both independently confirmed by a ticket **and** an email thread, i.e.
cross-validated by two independent 2025 sources before ever touching the
database - and now confirmed exactly against the database too:

1. **Deleted/cancelled line items are not removed, only flagged.**
   `EKPO.LOEKZ` `[email Thread 2]` `[ticket INC0042455]`. Must be filtered
   (`WHERE LOEKZ = '' OR LOEKZ IS NULL`).
2. **Price unit trap.** `EKPO.NETPR` is price *per `PEINH` units*, not per
   piece; `PEINH` is often 100 or 1000 for C-parts. Correct formula:
   `MENGE * NETPR / PEINH` `[email Thread 2]` `[ticket INC0042601]`.

`[DB]`: `SUM(MENGE*NETPR/PEINH) WHERE LOEKZ IS NULL OR LOEKZ=''` over all of
`EKPO` = **1,998,331,067.40 EUR**, an exact match to `questions.md` Q11.
**No third trap exists** - adding a filter on `EKKO.STAT_KZ<>'90'`
(excluding cancelled order headers) changes nothing; `EKPO.LOEKZ` already
captures everything needed at the line level. Likewise, filtering by
`MARA.LVORM` (material deletion flag, see §1) is *not* part of this
calculation and must not be applied here.

The deck's demonstrated failure mode (394,630,962,907 EUR vs. the correct
1,998,331,067 EUR, factor 197) is exactly reproducible by omitting both
fixes at once `[deck p3]`.

---

## 5. Block terminology - three fields, one overloaded word

`[process §3]`: "block" is used loosely for at least three independent
things, confirmed and precisely located by `[DB]`:

| Concept | Field | Scope | `[DB]` count |
|---|---|---|---|
| Vendor block | `LFA1.SPERR` | whole vendor, all future business | 29 vendors |
| Verification block | `RBKP.SPERR` | single invoice | 3,737 invoices (= `STAT_KZ` 34 or 60) |
| Payment block | `RBKP.ZLSPR` (`A`/`R`) | single invoice | 3,737 invoices (same set, redundant with `SPERR` and with `STAT_KZ`) |

`questions.md` Q12 explicitly warns that 3,737 is "a different concept and a
different question" from the 29 blocked vendors - now precisely explained:
whichever of the two RBKP block fields is queried, the answer is the same
3,737 and is **not** the answer to "which vendors are blocked."

**Name-collision trap, found only via `[DB]`, not documented anywhere:**
`[email Thread 3]` discusses a vendor called "Steinwerk" that is *not*
blocked. There are **nine** LFA1 vendors with "Steinwerk" in the name
(`Components GmbH`, `Metalworks GmbH`, `Engineering GmbH`, `Industrial
Systems KG`, `Systems SE`, `Automotive GmbH`, `Polymers GmbH`,
`Manufacturing KG`, `Technologies AG`), and exactly one - `Steinwerk
Engineering GmbH` (`LIFNR 0000101148`, Czech Republic) - is actually blocked.
This is not a contradiction with the email; it's a live demonstration of
exactly the trap the email is warning about. **Never resolve a vendor
reference by name string; always resolve to `LIFNR` first.**

---

## 6. Duration and currency methodology (fully reverse-engineered)

**Verification duration (Q13 = 7.36 days), `[DB]` reconstructed exactly from
`ZTSTAT`:** of the 7,755 invoices that ever entered status 34, 2,227 are
still there today (exactly matching Q4 - i.e. currently "stuck" invoices are
excluded from the average since they have no exit yet); for the remaining
5,528, the average time from **first entry into 34 to first exit from 34**
(regardless of whether the exit was to 60 or to 70) is exactly 7.36 days.
`[ticket INC0045322]`'s figure of 11 days (worst decile >40 days) is not
wrong, it is a different, plausible measurement (likely including
currently-open documents censored to "now", which `[DB]` shows pulls the
average up to ~59 days, or measured at an earlier point when the population
differed) - **always state which duration definition is being used.**

**Currency conversion (Q9/Q10), `[DB]` confirmed exactly:** convert every
non-EUR `RBKP.RMWWR` using the `TCURR` rate valid on or before
**`RBKP.BUDAT`** (posting date, not `BLDAT`/document date). Reproduces Q9
(294,814,064.51 EUR) and all five vendors/amounts in Q10 exactly.

---

## 7. Trust hierarchy across all 1,274 tables (new research for scalability)

This is the part not covered by `questions.md`'s 14-table extract, done to
address the "does it work on all 1,274 tables" judging criterion `[deck p5]`.
Method: for every table, get its row count; for the populated ones, check
whether any column that looks like a core entity key (`EBELN`, `LIFNR`,
`MATNR`, `BELNR`) actually contains values that exist in the corresponding
core table `[DB: script table_stats.py / table_probe.py, this session]`.

**Headline result:** of 1,274 tables,
- **14** are the trustworthy core (§1),
- **13** are confirmed variants/copies of the core tables (see table below),
- **1,096 are completely empty** (0 rows) - pure structural noise,
- **~151** are populated but contain **synthetic, non-joinable filler data**
  - they reuse real-looking SAP table names (`MARD`, `MAST`, `CSKS`, `T106`,
    `T188D`, `T301`, `T937C`, `COSP`, ...) and a shared pool of generic
    column names (`MANDT`, `VALUE1/2`, `FLAG1/2`, `KZ`, `STAT`/`STATUS`,
    `ZUONR`, `BEZEI`, `XBLNR`, `KUNNR`, `AUFNR`, `ERNAM`, `AENAM`, `ERDAT`,
    `AEDAT`, `CPUDT`/`CPUTM`, `POSNR`, `BUZEI`, `BELNR`, `WERKS`, `BUKRS`,
    `PRCTR`, `KOSTL`, `SAKNR`, `HKONT`, `WRBTR`, `DMBTR`, `MENGE`, `MEINS`,
    `WAERS`, `TXZ01`, `GJAHR`, `LOEKZ`, `SPERR`, `REFID`, `OBJNR`, `USNAM`)
    that gets assigned essentially at random to each table. `[DB]` spot-checks
    (10 tables tested: `MARD`, `T937C`, `T188D`, `T447C`, `T102D`, `T830A`,
    `COSP`, `ZF_KPI_09`, `ZS_TRACE_46`, `ZT_PARAM_73`) all show columns
    literally named `LIFNR`/`EBELN`/`MATNR`/`BELNR` whose *values* have **zero
    overlap** with the real `LFA1`/`EKKO`/`MARA`/`RBKP` key spaces (e.g.
    `MARD.LIFNR` contains random 6-digit numbers, never one of the real
    10-digit vendor numbers). **A column name matching a core entity does not
    imply it refers to the same entity** in this database outside the 14 core
    + 13 variant tables. This pattern is strong and consistent across every
    table tested, but was not exhaustively checked against all ~150 - treat
    the same key-overlap test as a mandatory pre-flight check before joining
    any unfamiliar table into a query, rather than assuming the pattern holds
    universally.
  - No satellite/master-data tables exist for plant (`WERKS`) or purchasing
    group (`EKGRP`) descriptions anywhere in the 1,274 tables `[DB]` - these
    remain bare codes with no decodable text.

**The 13 confirmed core-table variants, classified by genuine `[DB]` testing
(row-level `EXCEPT` diff and key-overlap against the live table), not by
name pattern alone:**

| Table | Rows | Relationship to its live counterpart | Verdict |
|---|---|---|---|
| `EKKO_BAK` | 5,250 | 100% identical subset of `EKKO` | stale copy - do not use |
| `EKPO_BAK` | 15,853 | 100% identical subset of `EKPO` | stale copy - do not use |
| `MARA_BAK` | 1,000 | 100% identical subset of `MARA` | stale copy - do not use |
| `LFA1_BAK` | 187 | 100% identical subset of `LFA1` | stale copy - do not use |
| `RSEG_BAK` | 7,527 | subset of `RSEG`, but **15 rows differ** from the current live values | **stale AND slightly wrong** - a concrete example of "looks plausible, is wrong" `[ticket INC0047288]` |
| `MSEG_SHADOW` | 12,305 | 100% identical subset of `MSEG` | stale copy - do not use |
| `RBKP_SHADOW` | 3,592 | 100% identical subset of `RBKP` | stale copy - do not use |
| `ZRBKP_STG` | 1,077 | 100% identical subset of `RBKP` | stale copy - do not use |
| `ZEKKO_MIG` | 2,250 | 100% identical subset of `EKKO` | stale copy - do not use (**not mentioned in any context source**, found only by scanning `schema_full.sql`/`[DB]`) |
| `BKPF_ARCH` | 884 | 100% identical subset of `BKPF` | **stale copy despite the `_ARCH` name** - do not use |
| `ZTSTAT_OLD` | 15,450 | 100% identical subset of `ZTSTAT` | stale copy - do not use |
| `RBKP_ARCH` | 6,500 | **zero key overlap** with `RBKP` (disjoint `BELNR`/`GJAHR`), dates 2016-12-30 to 2018-12-09 (entirely pre-2019-harmonisation), shares the vendor master (`LIFNR` fully overlaps `LFA1`) | **genuine historical data**, governed by different `STAT_KZ` semantics - see §8 |
| `ZTSTAT_ARCH` | 11,841 | **zero row overlap** with `ZTSTAT`, but every `OBJKY` value matches a `RBKP_ARCH.BELNR`, and its 6,500 distinct `RBKP` object keys exactly match `RBKP_ARCH`'s row count | **genuine historical log**, the transition history for `RBKP_ARCH` - use together with `RBKP_ARCH` for any pre-2019 question |

**Practical rule, corrected from `analysis.md`'s earlier framing:** the
`_ARCH` suffix is **not by itself** a reliable signal of "genuine archive" vs
"stale copy" - `RBKP_ARCH`/`ZTSTAT_ARCH` are genuine, `BKPF_ARCH` is a stale
copy despite an identical naming convention. **Every non-core table must be
checked individually** (row-level diff / key-overlap against its live
counterpart) before being trusted, exactly as done above - the suffix is a
hint, not a proof.

---

## 8. Archive semantics (pre-2019 data)

`RBKP_ARCH` (6,500 rows, `[DB]` genuine, see §7) only ever contains
`STAT_KZ` values **34** (5,341 rows, 82%) and **50** (1,159 rows, 18%) - no
60, 70, 80, or 90 at all. This is consistent with `[ticket INC0047102]`'s
claim that the exception branch (60) and the release/paid split (70/80)
simply did not exist before the 2019 harmonisation, so the archive's value
range is structurally narrower, not just differently distributed. **What
`34`/`50` meant *back then* could not be independently confirmed** - no
accounting documents (`BKPF`) exist anywhere in the extract for fiscal years
2016-2018, so the old "paid" signal is not reconstructable from this
dataset. Do not evaluate `RBKP_ARCH` with the current `STAT_KZ` rule set
(§3) - `[ticket INC0047102]`: "archive and current data must never be
evaluated with the same rule set."

---

## 9. Known unknowns - explicitly not fully resolved

Being honest about what is *not* nailed down, so the system doesn't overstate
its own certainty:

1. **The exact three-way-match comparison logic** (what counts as a
   "matching" quantity/price - exact equality? a tolerance band?) was never
   reverse-engineered field-by-field; only the *outcome* (`STAT_KZ=60` on
   failure) is confirmed `[process §2.4]`.
2. **Invoice cancellation is unrepresented.** `RBKP.STAT_KZ` never takes the
   value `90` (`[DB]`: 0 rows), unlike `EKKO`. How a cancelled/reversed
   invoice would actually look in this schema is unknown - nothing in any
   source describes it, and it doesn't occur in the data.
3. **`ZTFRG.FRGCO`'s two coding schemes (`'01'` vs `'A'`)** are unexplained
   by any source; use with caution if ever required.
4. **`data/incoming_documents.jsonl`** (Level 3 - anomaly detection on 31
   recently-processed documents) has not been analyzed as part of this
   context pack; it needs its own pass against the "normal" patterns
   documented here.
5. **The ~151 populated non-core noise tables** were spot-checked (10 tables)
   but not exhaustively verified; the "no real key overlap" finding is
   strong but not proven for every single one.
6. **Whether the exact three-way match tolerance, if any, is symmetric**
   (i.e. does an invoice *below* the ordered price/quantity also block, or
   only *above*?) - `[process §2.4]` only states "the most frequent reason...
   is a price variance or an invoiced quantity exceeding the quantity
   received", implying under-invoicing might not block, but this was not
   tested against the data.

---

## 10. Methodology / how this file was produced

- Documentation-only pass (`analysis.md`): read `context/GLOSSARY.md`,
  `context/PROCESS.md`, `context/tickets.jsonl`, `context/emails.md`,
  `README.md`, `questions.md`, `data/schema.sql`, `data/schema_full.sql`
  end-to-end, without touching the database, to catalogue every claim and
  every contradiction between sources.
- Database verification pass (`verification.md`): every open question from
  the documentation pass turned into a SQL prediction and checked against
  `data/erp_legacy.db` via `sqlite3.exe`, reproducing all 15 `questions.md`
  answers from first principles.
- This file: merges both, adds a full-database structural sweep (all 1,274
  tables' row counts + key-overlap testing) that neither prior file
  attempted, specifically to support questions on tables outside the
  original 14-table extract. Helper scripts used and left in the repo root
  for reproducibility: `table_stats.py`, `table_probe.py`,
  `verify_duration.py`, `verify_q9_q10.py`; raw outputs in `table_counts.txt`
  / `table_probe.txt`.
