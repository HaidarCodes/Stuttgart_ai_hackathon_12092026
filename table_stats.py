import sqlite3
con = sqlite3.connect('data/erp_legacy.db')
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print(len(tables))
counts = []
for t in tables:
    try:
        c = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    except Exception:
        c = -1
    counts.append((t, c))
counts.sort(key=lambda x: -x[1])
with open('table_counts.txt', 'w', encoding='utf-8') as f:
    for t, c in counts:
        f.write(f'{c}\t{t}\n')
print('total rows all tables:', sum(c for t, c in counts if c > 0))
core = {"LFA1","MARA","EKKO","EKPO","EKET","MKPF","MSEG","RBKP","RSEG","BKPF","ZTFRG","ZTSTAT","T161","TCURR"}
core_rows = sum(c for t,c in counts if t in core)
noncore_rows = sum(c for t,c in counts if t not in core and c>0)
print('core rows:', core_rows, 'non-core rows:', noncore_rows)
nonzero_noncore = [(t,c) for t,c in counts if t not in core and c>0]
print('non-core tables with >0 rows:', len(nonzero_noncore))
print('non-core tables with 0 rows:', len([1 for t,c in counts if t not in core and c==0]))
