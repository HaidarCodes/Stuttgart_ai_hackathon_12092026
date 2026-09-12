import sqlite3, datetime

con = sqlite3.connect("data/erp_legacy.db")
cur = con.cursor()

rows = cur.execute("""
    SELECT OBJKY, STAT_ALT, STAT_NEU, CPUDT, CPUTM
    FROM ZTSTAT WHERE OBJTY='RBKP'
    ORDER BY OBJKY, CPUDT, CPUTM, LOGID
""").fetchall()

def to_dt(d, t):
    return datetime.datetime.strptime(d + t, "%Y%m%d%H%M%S")

by_doc = {}
for objky, alt, neu, cpudt, cputm in rows:
    by_doc.setdefault(objky, []).append((to_dt(cpudt, cputm), alt, neu))

extract_date = datetime.datetime(2026, 3, 1)

censored_days_only_entered = []
for doc, events in by_doc.items():
    events.sort()
    total = datetime.timedelta(0)
    entry = None
    ever_entered = False
    for ts, alt, neu in events:
        if neu == '34':
            entry = ts
            ever_entered = True
        elif alt == '34' and neu in ('60', '70'):
            if entry is not None:
                total += (ts - entry)
                entry = None
    if not ever_entered:
        continue  # exclude invoices that never entered verification at all
    if entry is not None:
        total += (extract_date - entry)
    censored_days_only_entered.append(total.total_seconds() / 86400)

print("n (only invoices that ever entered 34):", len(censored_days_only_entered))
print("avg (corrected, excludes never-entered):", round(sum(censored_days_only_entered) / len(censored_days_only_entered), 2))
