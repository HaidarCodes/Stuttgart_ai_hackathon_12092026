import sqlite3, datetime

con = sqlite3.connect("data/erp_legacy.db")
cur = con.cursor()

rows = cur.execute("""
    SELECT OBJKY, STAT_ALT, STAT_NEU, CPUDT, CPUTM, LOGID
    FROM ZTSTAT WHERE OBJTY='RBKP'
    ORDER BY OBJKY, CPUDT, CPUTM, LOGID
""").fetchall()

def to_dt(d, t):
    return datetime.datetime.strptime(d + t, "%Y%m%d%H%M%S")

by_doc = {}
for objky, alt, neu, cpudt, cputm, logid in rows:
    by_doc.setdefault(objky, []).append((to_dt(cpudt, cputm), alt, neu))

extract_date = datetime.datetime(2026, 3, 1)

durations_closed = []   # only fully-exited intervals, sums per doc, doc must have left 34 for good
durations_censored = [] # same but open ones censored at extract date
per_doc_total = {}

for doc, events in by_doc.items():
    events.sort()
    total = datetime.timedelta(0)
    entry = None
    still_open = False
    for ts, alt, neu in events:
        if neu == '34':
            entry = ts
        elif alt == '34' and neu in ('60', '70'):
            if entry is not None:
                total += (ts - entry)
                entry = None
    # after loop, if entry is not None -> still inside 34 at end of log (currently stuck)
    if entry is not None:
        still_open = True
        total_censored = total + (extract_date - entry)
    else:
        total_censored = total

    per_doc_total[doc] = (total, total_censored, still_open)

closed_days = [t.total_seconds()/86400 for (t, tc, open_) in per_doc_total.values() if not open_]
all_days_censored = [tc.total_seconds()/86400 for (t, tc, open_) in per_doc_total.values()]

print(f"docs with any 34-entry: {len(per_doc_total)}")
print(f"docs fully exited 34 (closed): {len(closed_days)}")
print(f"docs still open in 34 at extract date: {sum(1 for *_ , o in per_doc_total.values() if o)}")
print(f"avg duration, closed only: {sum(closed_days)/len(closed_days):.2f} days")
print(f"avg duration, all incl. censored-to-extract-date: {sum(all_days_censored)/len(all_days_censored):.2f} days")

closed_days.sort()
def pct(lst, p):
    idx = int(len(lst)*p)
    return lst[min(idx, len(lst)-1)]
print(f"90th percentile (closed): {pct(closed_days,0.9):.2f} days")

all_days_censored.sort()
print(f"90th percentile (all incl censored): {pct(all_days_censored,0.9):.2f} days")

# Alternative: span from first entry into 34 to the transition 34->70 (accepted),
# for docs that reached 70, ignoring detours through 60 (i.e. whole span, not net time).
span_days_to_70 = []
for doc, events in by_doc.items():
    events.sort()
    first_entry = None
    exit_to_70 = None
    for ts, alt, neu in events:
        if neu == '34' and first_entry is None:
            first_entry = ts
        if alt == '34' and neu == '70':
            exit_to_70 = ts
    if first_entry and exit_to_70:
        span_days_to_70.append((exit_to_70-first_entry).total_seconds()/86400)

print(f"\ndocs reaching 70 with computable span: {len(span_days_to_70)}")
print(f"avg span first-34-entry -> 70 (only docs that reached 70): {sum(span_days_to_70)/len(span_days_to_70):.2f} days")

# only 50->34->70 direct (never touched 60) - "normal" path
direct_days = []
for doc, events in by_doc.items():
    events.sort()
    seq = [(alt, neu) for ts, alt, neu in events]
    touched_60 = any(neu == '60' or alt == '60' for alt, neu in seq)
    if touched_60:
        continue
    entry = exitt = None
    for ts, alt, neu in events:
        if neu == '34':
            entry = ts
        if alt == '34' and neu == '70':
            exitt = ts
    if entry and exitt:
        direct_days.append((exitt-entry).total_seconds()/86400)
print(f"docs with direct 34->70 (never touched 60): {len(direct_days)}")
print(f"avg duration, direct path only: {sum(direct_days)/len(direct_days):.2f} days")
direct_days.sort()
print(f"median direct path: {direct_days[len(direct_days)//2]:.2f} days")

# closed_days split by touched 60 or not
closed_touched60 = []
closed_direct = []
for doc, events in by_doc.items():
    events.sort()
    seq = [(alt, neu) for ts, alt, neu in events]
    touched_60 = any(neu == '60' for alt, neu in seq)
    t, tc, open_ = per_doc_total[doc]
    if open_:
        continue
    d = t.total_seconds()/86400
    if touched_60:
        closed_touched60.append(d)
    else:
        closed_direct.append(d)
print(f"\nclosed docs touched 60: {len(closed_touched60)}, avg net-34-time: {sum(closed_touched60)/len(closed_touched60):.2f}")
print(f"closed docs never touched 60: {len(closed_direct)}, avg net-34-time: {sum(closed_direct)/len(closed_direct):.2f}")

overall_median = sorted(closed_days)[len(closed_days)//2]
print(f"\nmedian duration closed (net time in 34): {overall_median:.2f} days")

# first-visit-only duration (first entry to 34 -> first exit from 34), ignore re-entries
first_visit_days = []
for doc, events in by_doc.items():
    events.sort()
    entry = None
    exitt = None
    for ts, alt, neu in events:
        if neu == '34' and entry is None:
            entry = ts
        elif alt == '34' and neu in ('60','70') and entry is not None and exitt is None:
            exitt = ts
    if entry and exitt:
        first_visit_days.append((exitt-entry).total_seconds()/86400)
print(f"\nfirst-visit-only: n={len(first_visit_days)}, avg={sum(first_visit_days)/len(first_visit_days):.2f} days")

# what happens to the 40 docs that go 60->34 (i.e. re-enter verification after failing once)?
reentries = [doc for doc, events in by_doc.items()
             if any(alt=='60' and neu=='34' for ts,alt,neu in events)]
print(f"\ndocs that re-entered 34 from 60: {len(reentries)}")
for doc in reentries[:5]:
    print(doc, by_doc[doc])

