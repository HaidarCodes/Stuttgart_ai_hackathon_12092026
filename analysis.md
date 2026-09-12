# Context Analysis - Purchase-to-Pay Legacy ERP

Purpose: summarize everything found in `context/`, `README.md`, `questions.md`,
`data/schema.sql` and `data/schema_full.sql`, and flag every contradiction,
gap and trap **before** touching `data/erp_legacy.db`. Nothing below has been
verified against the actual data yet - that is the next step. Each open
question is marked so it can be turned into a SQL check later.

---

## 1. Inventory of sources

| Source | What it is | Authority | Last updated / covers |
|---|---|---|---|
| `context/GLOSSARY.md` (DK-MM-014) | Official data catalogue for the 14 "core" tables | Nominally the ground truth | Last full revision **2018-11-04**, pre-dates the 2019 harmonisation, "ad-hoc" patches since, explicitly marked incomplete by its own author |
| `context/PROCESS.md` (BPD-P2P-2.3) | Business-language description of the P2P process, written by an external consultancy | Good for *semantics/vocabulary*, useless for *table mapping* (deliberately, work package 4 was descoped) | 2023-06-15 |
| `context/tickets.jsonl` | 43 IT support tickets, Feb-Sep 2025 | Empirically grounded (describes actual system behaviour, incident by incident) but fragmentary and reactive | 2025, i.e. **post-harmonisation**, closest in time to the extract date (2026-03-01) |
| `context/emails.md` | 6 mail threads, AP/Procurement, Apr-Sep 2025 | Practitioner knowledge, includes explicit warnings about the glossary being wrong | 2025 |
| `data/schema.sql` | DDL for the 14 tables a colleague hand-picked as relevant | Structural truth for those 14 tables, but "not guaranteed to be complete" (own disclaimer) | current (matches `schema_full.sql` definitions for these tables) |
| `data/schema_full.sql` | DDL for all 1,274 tables | Structural truth, includes many decoy/copy tables | current |
| `questions.md` | 15 calibration questions with verified answers | Ground truth for *answers*, not for *method* - must not be hard-coded | n/a |

General pattern: **the closer a source is to 2025/2026 and to a concrete
incident, the more it can be trusted about current system behaviour.** The
glossary is the oldest and, by its own admission and by every other source's
admission, the least reliable for anything touching process status.

---

## 2. The central contradiction: `STAT_KZ` (status indicator)

This is explicitly the case's headline example (README) and is corroborated
independently by **every other source** - tickets, emails, and the glossary's
own margin notes. This is almost certainly the "confidently wrong" document
the README warns about.

### 2.1 What the glossary (2018) says (`GLOSSARY.md` §6)

| Value | Glossary meaning |
|---|---|
| 10 | Purchase order created |
| 20 | Purchase order released |
| 30 | Goods receipt partially posted |
| 34 | **Invoice verified and released** |
| 40 | Goods receipt complete |
| 50 | Invoice recorded |
| 80 | Process completed |
| 90 | Cancelled |

The glossary itself flags this section as suspect: *"Additional values were
introduced during the 2019 harmonisation... not yet incorporated here."*

### 2.2 What tickets/emails (2025) say actually happens

| Value | Actual meaning (per tickets) | Ticket(s) |
|---|---|---|
| 50 | Invoice recorded, verification **not yet started** | INC0046290, INC0044001 |
| 34 | Invoice **currently undergoing verification** - normal, usually short-lived, blocks payment | INC0041207, INC0042003, INC0043855, INC0044001, INC0045744 |
| 60 | Verification **failed** (price variance or invoiced qty > received qty) - exception branch, needs manual clerk action, introduced in 2019 | INC0041766, INC0042003, INC0045744 |
| 70 | Released for payment (successor of 34 once verification passes) | INC0042188, INC0041580 |
| 80 | Paid / cleared (clearing document exists) | INC0044512 |
| 90 | Cancelled (can be reached from *any* earlier status) | INC0044390 |

Sequence confirmed by IT (INC0042003): **50 -> 34 -> (70 or 60)**, and 60 requires
manual resolution before it can proceed (implicitly to 70, unconfirmed - open question).

### 2.3 The contradiction, precisely

- The glossary says **34 = "invoice verified and released"** (i.e. done, payable).
- Reality is the **opposite**: 34 = invoice **stuck in verification, not
  payable yet**. INC0044288 (still *open* at extract time) states this
  explicitly: *"Value 34 ... is described as approved and released, which is
  the opposite of what it means."*
- The glossary has **no entries at all** for 60 and 70, which are central to
  the current process (introduced 2019).
- `emails.md` Thread 1 (Kai Mueller, IT) independently confirms: *"the status
  codes in the data catalogue are not what the system actually does... I am
  building the list from the change log instead."*
- `emails.md` Thread 5 (handover note, Thomas Schmidt) independently confirms
  the same thing and names the fix: use `ZTSTAT` (the logging table), not the
  glossary, to determine what a status means / how documents actually move.

**Working hypothesis (needs DB verification):** `STAT_KZ` may carry two
disjoint value populations depending on the owning table:
- `EKKO.STAT_KZ` (purchase order): `{10, 20, 30, 40, 90}` - this range still
  seems to agree with the glossary and with tickets about PO approval/GR
  (INC0043290, INC0044390, INC0043588).
- `RBKP.STAT_KZ` (invoice): `{50, 34, 60, 70, 80, 90}` - this is the range
  redefined in 2019; the glossary's guesses (34="verified/released",
  80="process completed") are wrong or imprecise for this table.

**Open question for DB verification:** confirm the two value populations are
actually disjoint per table, confirm the full transition graph via `ZTSTAT`,
and confirm whether 60 always resolves back into 70 (or can also reach 90).

### 2.4 Archived data uses yet another semantic (a second, orthogonal trap)

INC0047102: colleague ran the *same* status evaluation against `RBKP_ARCH`
and got different proportions. Resolution: **the archive predates the 2019
harmonisation and follows the old (pre-harmonisation, i.e. closer to the 2018
glossary?) status semantics.** "Archive and current data must never be
evaluated with the same rule set." This is explicitly called out as
undocumented anywhere.

**Open question:** does `RBKP_ARCH`'s status semantics actually match the
2018 glossary (i.e. is the glossary "correct, just for the wrong table
version")? That would explain why the glossary looks plausible at all - it
may be describing the pre-2019/archived world, not the current one. Needs
verification against `RBKP_ARCH` content and against `T161`/known archived
document dates.

### 2.5 Duration/statistics discrepancy to resolve

- `questions.md` Q13 (verified answer): average time in verification =
  **7.36 days**.
- INC0045322 (ticket, computed "from the logging table as the time between
  the transition into 34 and the transition out of it"): average **11 days**,
  worst decile above 40 days.

These are two independently computed numbers for what sounds like the same
metric, and they disagree. Possible explanations to check empirically:
different time windows, different populations (e.g. only closed/resolved
transitions vs. all), calendar days vs. business days, or whether cancelled
(90) exits are included/excluded. **Needs DB verification** - recompute from
`ZTSTAT` transitions into/out of 34 and compare methodologies.

### 2.6 Simultaneous-timestamp edge case

INC0046701: some documents appear to skip 34 entirely (jump straight from 50
to a later status). Explained as verification completing within the same
batch window, so the 34 transition exists in `ZTSTAT` but shares an identical
timestamp with the next transition. **Implication:** any duration/sequence
calculation must not assume strictly increasing timestamps between
consecutive `ZTSTAT` rows for the same document; ordering must also use
`LOGID` (or another tiebreaker) to recover the true order, and zero-length
verification intervals are legitimate, not a data bug.

---

## 3. "Block" terminology - three concepts, overlapping field names

`PROCESS.md` §3 explicitly warns that "block" is used loosely for at least
three independent things. Emails and tickets confirm this is a live source of
confusion, and even name the specific fields:

| Business concept | Field | Table | Scope | Notes |
|---|---|---|---|---|
| **Vendor block** | `SPERR` | `LFA1` | whole vendor, all future business | Set centrally by Vendor Master Data (emails Thread 3), "usually for compliance reasons" (glossary) |
| **Verification block** | `SPERR` | `RBKP` | single invoice document | Set during invoice verification when the three-way match fails (PROCESS.md); confirmed distinct field, same name, by INC0043012 |
| **Payment block** | `ZLSPR` | `RBKP` | single invoice document | Prevents an otherwise-valid invoice from being paid; values `A`/`R` per INC0042890 (A = auto-set entering verification, R = set when verification fails); value range **not documented** in glossary |

This resolves the emails Thread 3 confusion ("Steinwerk blocked?") and
directly explains **Q12**: 29 vendors are blocked (`LFA1.SPERR`), which is a
completely different number from the 3,737 invoices carrying a payment block
(`RBKP.ZLSPR`) - these must never be conflated (explicit warning in
`questions.md` Q12, echoed by INC0043012 and emails Thread 3).

**Open question:** confirm `RBKP.SPERR` (verification block) is populated
consistently with `STAT_KZ = 60` (exception branch), i.e. whether it's
redundant with status or carries extra information (glossary lists it, but
its value range is also unlisted/"not yet documented").

---

## 4. Approval / release workflow

- `PROCESS.md` §2.2: an order needs approval by one or more approvers
  depending on value/purchasing group; no goods receipt allowed until fully
  approved.
- `ZTFRG` (custom release-workflow table) is **not documented in the
  glossary** at all ("Not yet documented", contact Mr Weber) but is described
  in tickets:
  - INC0043404: field with values `A` (pending) / `F` (granted, i.e. "freigegeben").
  - INC0043290: **critical caveat** - `ZTFRG` only carries entries for orders
    **above the signature threshold**. It therefore lists *considerably
    fewer* pending approvals than actually exist. "For a complete picture use
    the header status" (i.e. `EKKO.STAT_KZ`, presumably 10 = not yet
    approved, 20 = approved/released, consistent with the glossary for the PO
    side - see §2.3 hypothesis).
- `EKKO.FRGKE` ("release indicator", per glossary) is a second, distinct
  candidate field for approval status that has not been cross-checked against
  `STAT_KZ` or `ZTFRG` anywhere in the context sources.

**Open question:** does Q5 (1,136 orders waiting for approval) come from
`EKKO.STAT_KZ = 10`, from `EKKO.FRGKE`, or from `ZTFRG`? Given INC0043290's
explicit warning against using `ZTFRG` for a complete picture, the header
status field is the more likely correct source - needs DB verification, and
`FRGKE` vs `STAT_KZ` agreement should be checked.

---

## 5. Three-way match / invoice verification

`PROCESS.md` §2.4 defines the three-way match as:
1. Invoice references a valid PO.
2. Goods were actually received.
3. Quantity and price match what was ordered.

Ticket confirmation (INC0041766, INC0042003, INC0045744): failure of any leg
routes the invoice into **status 60** and sets a **verification block**
(`RBKP.SPERR`) and/or **payment block** (`RBKP.ZLSPR = R`). The most common
failure per PROCESS.md and emails Thread 6 (Hagenbach case) is **invoiced
quantity exceeding received quantity**, or a **price variance**.

Mapping to fields (structural, from `schema.sql`, needs DB confirmation of
the actual comparison logic):
- Ordered qty/price: `EKPO.MENGE`, `EKPO.NETPR`, `EKPO.PEINH` (see §7 price
  unit trap).
- Received qty: `MSEG.ERFMG` where `BWART = '101'` (goods receipt against PO,
  per glossary §4 and INC0043712), joined via `MSEG.EBELN`/`EBELP`.
- Invoiced qty/amount: `RSEG.MENGE`, `RSEG.WRBTR`, joined via
  `RSEG.EBELN`/`EBELP`.

**Q4 vs Q7 distinction (explicit in questions.md):** Q4 ("stuck in
verification") = normal processing, i.e. `STAT_KZ = 34`. Q7 ("failed
three-way match") = exception branch, i.e. `STAT_KZ = 60`. These are
disjoint sets and must not be merged - this is explicitly one of the
questions' teaching points.

---

## 6. Definitions needed for the north-star question ("which invoices are stuck")

Reconciling `PROCESS.md` §2.4/§2.6, `emails.md` Thread 1, and
INC0044001/INC0046290/INC0042188:

- **Recorded, not yet in verification:** `STAT_KZ = 50`.
- **Stuck / in verification (Q4's definition):** `STAT_KZ = 34` - recorded,
  entered verification, **not yet** approved for payment, **not yet** paid.
  Do not rely on the payment block field alone (INC0044001) - it is also set
  for the exception branch (60).
- **Exception branch, needs a clerk (Q7's definition):** `STAT_KZ = 60`.
- **Approved for payment but not yet paid (Q8):** `STAT_KZ = 70`.
- **Paid (Q7/Q8 boundary, and INC0044512):** an accounting document exists
  with `BLART = 'KZ'` and `AUGBL` populated (clearing document), linked via
  `BKPF.AWKEY` back to the RBKP document (glossary §7); `RBKP.STAT_KZ = 80`
  should reflect the same fact redundantly - **needs DB cross-check that
  these two signals never disagree** (INC0045601 notes 8 known cases where
  clearing happened manually outside the payment run and the clearing date
  is missing - a potential source of disagreement between the STAT_KZ view
  and the BKPF/AUGBL view).

---

## 7. Two numeric traps explicitly called out for Q11 (net PO value)

Both are independently confirmed by an email thread **and** a ticket, i.e.
already cross-validated by two 2025 sources - high confidence these are real,
current behaviours, not stale documentation:

1. **Deleted/cancelled line items are not removed, only flagged.**
   `EKPO.LOEKZ` (deletion indicator). Confirmed by `emails.md` Thread 2 (Kai
   Mueller) and INC0042455 ("Report did not exclude items carrying the
   deletion indicator... deleted items remain physically in the item table").
   Must filter `LOEKZ` out (and, per INC0044390, also filter cancelled order
   headers, `EKKO.STAT_KZ = 90`, noting the previous status is sometimes still
   visible since cancellation can happen "from any earlier status").
2. **Price unit trap.** `EKPO.NETPR` is price **per price unit**
   (`EKPO.PEINH`), not per piece. `PEINH` is often 100 or 1000 for C-parts.
   Correct formula: `net value = MENGE * NETPR / PEINH`. Confirmed by
   `emails.md` Thread 2 and INC0042601 ("factor of 1000 too high... Price
   unit was not taken into account").

`questions.md` Q11 explicitly says a wrong answer "in the hundreds of
billions" means you fell into **both** traps at once (deleted items inflate
count, missing price-unit division inflates each line by 100-1000x) -
consistent with these two independently-documented issues.

**Open question:** does "actually valid" in Q11 also require excluding
cancelled PO headers (`STAT_KZ = 90`) in addition to `LOEKZ`-flagged items?
INC0044390 suggests yes for order-volume reporting generally.

---

## 8. Currency conversion

Confirmed consistently across glossary (§8, `TCURR`/`GDATU`), emails Thread 4
(Markus Keller), and INC0042744:

- Amounts (`RBKP.RMWWR`, `BKPF.DMBTR`-adjacent) are stored in **document
  currency** (`WAERS`), not EUR. Summing across currencies without conversion
  "gives a number that means nothing at all" (Thread 4).
- Conversion rule: use `TCURR`, select the **most recent rate with
  `GDATU` <= the relevant document date** (glossary says "on or before the
  document date"; Q9 in `questions.md` says "posting date" specifically -
  i.e. `BUDAT`, not `BLDAT`). **Open question:** confirm which date
  (`BLDAT` vs `BUDAT`) is the correct one to key the FX lookup on - the
  glossary and Q9 both say "document date" resp. "posting date"; these are
  two different fields in `RBKP` and need to be disambiguated (`BLDAT` =
  date printed on the invoice, `BUDAT` = posting date, per glossary §5). Q9's
  wording ("posting date") suggests `BUDAT` is correct.

---

## 9. Table trust hierarchy - decoys, copies, staging, archive

README explicitly warns: 1,274 tables total, only 14 are "core", and there
are lookalike tables (`EKKO_BAK`, `RBKP_SHADOW`, `ZRBKP_STG`, `ZTSTAT_OLD`,
`RBKP_ARCH`, etc.) that "contain data that looks entirely plausible."
Confirmed to exist in `data/schema_full.sql`:

| Suffix pattern | Examples found in schema_full.sql | Per INC0047288 |
|---|---|---|
| `_BAK` | `EKKO_BAK`, `EKPO_BAK`, `LFA1_BAK`, `MARA_BAK`, `RSEG_BAK` | stale copy, not maintained |
| `_SHADOW` | `RBKP_SHADOW`, `MSEG_SHADOW` | staging/shadow copy, not maintained |
| `_STG` | `ZRBKP_STG`, plus many generically-named `Z*_STG_NN` tables | staging area, not maintained |
| `_OLD` | `ZTSTAT_OLD` | stale copy, not maintained |
| `_ARCH` | `RBKP_ARCH`, `BKPF_ARCH`, `ZTSTAT_ARCH`, plus generic `Z*_ARCH_NN` | **archive - see caveat below** |

INC0047288's blanket rule: **"Only the base table without a suffix is
productive... reading [the others] yields results that look plausible and
are wrong."**

**Tension to resolve:** INC0047102 treats `RBKP_ARCH` differently - not as
"wrong", but as legitimately-scoped historical data governed by *different*
status semantics (pre-2019). This appears to contradict the blanket
"none of them are maintained, don't read them" framing of INC0047288 for the
`_ARCH` suffix specifically. **Open question:** is `RBKP_ARCH` (and other
`_ARCH` tables) a legitimate historical extension of the current table (to
be unioned in with different rules applied per row's era), or is it also
stale/unreliable data that merely happens to look self-consistent? This
matters directly for Q2 ("15,000 purchase orders total") and Q11 - do these
totals include archived documents or only the live `EKKO`/`RBKP`/`EKPO`
tables? Needs a direct row-count/date-range check against `EKKO` vs
`EKKO`-adjacent archive tables (note: no `EKKO_ARCH` was found, only
`EKKO_BAK` - suggesting POs may not have a legitimate archive counterpart the
way invoices do; needs confirmation).

The generic `Z*_ARCH_NN` / `Z*_STG_NN` tables (e.g. `ZC_ARCH_15`,
`ZM_STG_11`, ...) appear to be decoys/noise unrelated to the P2P core - they
have generic, non-descriptive column sets (`VALUE1`, `VALUE2`, `FLAG1`,
`FLAG2`, `KZ`, ...) shared across many unrelated table name stems (`AFKO`,
`BALDAT`, `CDHDR`, etc.), unlike the real P2P tables which have stable,
meaningful column sets across `schema.sql` and `schema_full.sql`. Working
assumption: these are scale/noise tables for the "1,274 tables" stress test
and are not part of the P2P process - **to be confirmed** by checking a
handful for row counts and content once DB access is allowed.

---

## 10. Referential integrity gap (migration artifact)

INC0047195: a batch of old orders was moved out of the live order table
during migration while their invoice items (`RSEG`) stayed behind. Roughly
**40 invoice items** reference an `EBELN` that no longer exists in `EKKO`.
An `INNER JOIN` silently drops these rows, which is how a prior reporting
discrepancy arose. **Implication: any join from `RSEG`/`RBKP` to `EKKO` for
totals or three-way-match logic must be a `LEFT JOIN`** (or otherwise
explicitly account for orphaned references) rather than an inner join, or
such invoices will silently vanish from stuck-invoice / value reports.

**Open question:** do these ~40 orphaned items overlap with the "stuck"
population (Q4) or the "three-way match failed" population (Q7)? If so, they
need special handling (can't fully three-way-match an invoice whose PO
doesn't exist) - worth checking whether this is itself a source of Q7-like
blocks.

---

## 11. Goods receipt: partial vs. complete

Two independent signals are both said to represent the same fact
(INC0043588 - "both views were provided"):
- `EKKO`/PO-level: `STAT_KZ = 30` (partial) vs. `40` (complete).
- Item-level: `EKPO.ELIKZ` ("delivery completed indicator", glossary §3).

**Open question:** confirm these two signals agree at the item level (a PO
could have some items complete and others not - does header `STAT_KZ`
reflect "all items complete" or "at least one item received"?). This matters
for Q6 (1,731 orders with only partial delivery) and Q14 (1,464 orders fully
received but never invoiced - the GR/IR case, per INC0045044, defined as
`STAT_KZ = 40` with no corresponding invoice document, again requiring a
`LEFT JOIN`/anti-join per §10's caution).

---

## 12. Document types and glossary accuracy check

`questions.md` Q3 gives four document types (NB, UB, FO, ZRB) with plain-text
meanings; `T161` per glossary §8 is the customizing table naming these types,
and INC0045477 confirms `ZRB` = scheduling agreement release. This part of
the glossary/customizing chain appears **not** to be in dispute - no
contradicting source found. Treated as reliable.

---

## 13. Plants vs. company code - not a contradiction, just two different things

Glossary says `EKKO.BUKRS` ("always 1000 in our system") = company code.
INC0046433 says plants in scope are `1000, 1100, 2000`. These are different
fields (`BUKRS` vs `WERKS`) and not in conflict - noting this explicitly
since the shared literal "1000" could otherwise look like a contradiction.

---

## 14. Explicitly documented gaps (glossary's own admission, §"Not yet documented")

The glossary itself lists these as undocumented - i.e. it does not even
attempt an authoritative claim here, so there is nothing to "contradict", but
they are necessary building blocks and their meaning had to be reconstructed
from tickets/emails above:

- `ZTFRG` - release workflow (reconstructed in §4 above).
- `ZTSTAT` - status log (reconstructed throughout §2; per emails Thread 5,
  this is actually the **most authoritative** source for process truth, not
  a documentation gap in practice).
- `EKET` - schedule lines; INC0045888 clarifies delivery dates live here,
  "one entry per item in our configuration" (i.e. `EKET` here is effectively
  1:1 with `EKPO`, not genuinely multi-schedule-line, at least in this
  dataset - **worth a DB check**, since the DDL PK is
  `(EBELN, EBELP, ETENR)` implying multiple lines are structurally possible).
- `SHKZG`, `XBLNR`, `USNAM` - debit/credit indicator, reference document
  number, username; not central to the status question, no contradictions
  found, low priority.
- Value range of `ZLSPR` - reconstructed in §3 above (`A`/`R`, per INC0042890).

---

## 15. Process pain points relevant to system design (from PROCESS.md §4)

Not contradictions, but requirements the answer system should visibly
satisfy:
- Nobody can answer "where is this invoice right now" without calling three
  people -> answers should state current status **and reason** (cf.
  emails Thread 6 - "in verification, reason is a quantity difference,
  expected clearing date X").
- Existing stuck-invoice reporting is manual, monthly, ~1.5 days of work, and
  stale by the time it's circulated (PROCESS.md, and independently
  INC0046988, INC0046577 - both open tickets as of the extract date,
  requesting automation / self-service).
- Cancelled/deleted items are frequently included in reports by mistake,
  inflating volume (PROCESS.md §4, matches §7 above).
- "The meaning of the status values... is not reliably documented" -
  PROCESS.md's own summary of the central contradiction in §2.

---

## 16. Summary: verification plan for once DB access is allowed

Priority-ordered list of predictions to test against `data/erp_legacy.db`:

1. Confirm `EKKO.STAT_KZ` and `RBKP.STAT_KZ` occupy disjoint value sets, and
   derive the full transition graph from `ZTSTAT` (§2.3).
2. Check whether `RBKP_ARCH`'s `STAT_KZ` distribution matches the 2018
   glossary's proposed meanings (test the "archive = pre-2019 semantics =
   matches old glossary" hypothesis, §2.4).
3. Recompute average verification duration from `ZTSTAT` (34-entry to
   34-exit) and reconcile 7.36 days (questions.md) vs. 11 days (INC0045322)
   (§2.5).
4. Verify `EKKO.STAT_KZ=10` counts vs. `ZTFRG` pending counts vs.
   `EKKO.FRGKE` for Q5, confirming ZTFRG under-counts as warned (§4).
5. Confirm `LFA1.SPERR` (29 vendors) vs `RBKP.ZLSPR` (3,737 invoices) are
   the numbers behind Q12, and that `RBKP.SPERR` (verification block) is a
   third, distinct signal (§3).
6. Recompute Q11 with both traps fixed (`LOEKZ` filter + `NETPR*MENGE/PEINH`)
   and check whether excluding `STAT_KZ=90` headers changes the result (§7).
7. Confirm FX lookup date: `BUDAT` vs `BLDAT` against `TCURR.GDATU` for Q9
   (§8).
8. Quantify the ~40 orphaned `RSEG`/`RBKP` items with missing `EKKO` parents;
   check whether inner-join vs left-join changes Q4/Q9/Q11 results (§10).
9. Check whether `EKET` truly has 1:1 cardinality with `EKPO` in this dataset
   despite its 3-column PK suggesting otherwise (§14).
10. Spot-check a handful of generic `Z*_ARCH_NN`/`Z*_STG_NN` tables to confirm
    they are unrelated noise rather than part of the P2P process (§9).
11. Confirm `BKPF.AUGBL`-based "paid" determination agrees with
    `RBKP.STAT_KZ=80` in all but the ~8 manually-cleared cases from
    INC0045601 (§6).
