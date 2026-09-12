import sqlite3
con = sqlite3.connect('data/erp_legacy.db')
cur = con.cursor()

core = {"LFA1","MARA","EKKO","EKPO","EKET","MKPF","MSEG","RBKP","RSEG","BKPF","ZTFRG","ZTSTAT","T161","TCURR"}
known_variant_suffixes = ("_BAK","_SHADOW","_STG","_OLD","_ARCH","_MIG")

lookup = {
    "EBELN": "SELECT EBELN FROM EKKO",
    "LIFNR": "SELECT LIFNR FROM LFA1",
    "MATNR": "SELECT MATNR FROM MARA",
    "BELNR": "SELECT BELNR FROM RBKP",
}
lookup_sets = {k: set(r[0] for r in cur.execute(q)) for k, q in lookup.items()}

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
results = []
for t in tables:
    if t in core:
        continue
    cols = [r[1] for r in cur.execute(f'PRAGMA table_info("{t}")')]
    cnt = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    if cnt == 0:
        continue
    overlaps = {}
    for key, valset in lookup_sets.items():
        if key in cols:
            vals = set(r[0] for r in cur.execute(f'SELECT DISTINCT "{key}" FROM "{t}"'))
            inter = len(vals & valset)
            overlaps[key] = (len(vals), inter)
    results.append((t, cnt, overlaps))

with open('table_probe.txt', 'w', encoding='utf-8') as f:
    for t, cnt, overlaps in sorted(results, key=lambda x: -x[1]):
        f.write(f"{t}\trows={cnt}\toverlaps={overlaps}\n")

print("done, populated non-core tables:", len(results))
print("of which have any key overlap with core entities:", sum(1 for t,c,o in results if any(i>0 for _,i in o.values())))
