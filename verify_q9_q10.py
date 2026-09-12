import sqlite3

con = sqlite3.connect("data/erp_legacy.db")
cur = con.cursor()

rates = cur.execute("SELECT FCURR, TCURR, GDATU, UKURS FROM TCURR").fetchall()
# build lookup: for a given from-currency and a date, find most recent GDATU <= date
from collections import defaultdict
by_cur = defaultdict(list)
for fcurr, tcurr, gdatu, ukurs in rates:
    by_cur[fcurr].append((gdatu, ukurs))
for k in by_cur:
    by_cur[k].sort()

def rate_for(fcurr, date):
    if fcurr == 'EUR':
        return 1.0
    lst = by_cur[fcurr]
    best = None
    for gdatu, ukurs in lst:
        if gdatu <= date:
            best = ukurs
        else:
            break
    return best

invs = cur.execute("SELECT BELNR, LIFNR, WAERS, RMWWR, BLDAT, BUDAT FROM RBKP WHERE STAT_KZ='34'").fetchall()

def total_with(datefield_idx):
    total = 0.0
    for belnr, lifnr, waers, rmwwr, bldat, budat in invs:
        d = bldat if datefield_idx == 'BLDAT' else budat
        r = rate_for(waers, d)
        total += rmwwr * r
    return total

print("Q4 count:", len(invs))
print("Total using BUDAT (posting date):", round(total_with('BUDAT'), 2))
print("Total using BLDAT (document date):", round(total_with('BLDAT'), 2))
print("Expected (questions.md):", 294814064.51)

# Q10: top 5 vendors by value
from collections import defaultdict as dd
vendor_totals = dd(float)
vendor_counts = dd(int)
for belnr, lifnr, waers, rmwwr, bldat, budat in invs:
    r = rate_for(waers, budat)
    vendor_totals[lifnr] += rmwwr * r
    vendor_counts[lifnr] += 1

top5 = sorted(vendor_totals.items(), key=lambda x: -x[1])[:5]
name_map = dict(cur.execute("SELECT LIFNR, NAME1 FROM LFA1").fetchall())
print("\nTop 5 vendors by stuck-invoice value (using BUDAT):")
for lifnr, val in top5:
    print(f"  {name_map.get(lifnr, lifnr)} ({lifnr}) - {vendor_counts[lifnr]} invoices, {val:,.2f} EUR")
