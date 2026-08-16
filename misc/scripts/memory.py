#!/usr/bin/env python3
"""Fabric memory: ETNF zstd-parquet relations, built into a SQLite index.

The parquet relations are the source and the only thing committed. The SQLite
database and its HRR vectors are derived: encode_atom is SHA-256 over the text,
so `build` reproduces them byte for byte from the same relations on any machine.
Committing both would store the same facts twice, and the derived copy is 31x
the size of the source it came from.

The vector is the index. A query is encoded the same way and compared by phase
cosine similarity, so recall is nearest-neighbour over meaning rather than a
substring match. Vectors are byte-identical to `tw_hrr.hpp` and to the planner's
holographic.py, which is what lets the same rows be read from C++ or Python.

The database is an ordinary SQLite file. It opens through the `weft_fdb` VFS when
one is registered -- the same VFS `service-store` opens `queen` with -- and as a
plain file when none is, so the rows are the same either way.

  memory.py build                      parquet -> sqlite, with the vectors
  memory.py add "<content>" --kind feedback --entities fabric cassie
  memory.py recall "<query>" [-n 5]
  memory.py verify
"""
import argparse, datetime, sqlite3, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hrr

ROOT = pathlib.Path(__file__).resolve().parents[2] / "memory"
DB = ROOT / "fabric.sqlite3"          # derived, gitignored
RELATIONS = ("kinds", "entities", "memory", "memory_entity")
VFS = "weft_fdb"          # registered by store-plane; absent means a plain file
KINDS = ("user", "feedback", "project", "reference")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
  id       INTEGER PRIMARY KEY,
  kind     TEXT NOT NULL,
  content  TEXT NOT NULL,
  entities TEXT NOT NULL,
  dim      INT  NOT NULL,
  vec      BLOB NOT NULL,
  created  TEXT NOT NULL
);
-- What produced the vectors, so a reader can tell whether they are still valid.
CREATE TABLE IF NOT EXISTS provenance (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);
"""


def connect(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        con = sqlite3.connect(f"file:{path}?vfs={VFS}", uri=True)
    except sqlite3.Error:
        con = sqlite3.connect(path)      # no store-plane VFS registered here
    con.executescript(SCHEMA)
    return con


def _read_relations():
    import pandas as pd
    rel = {n: pd.read_parquet(ROOT / f"{n}.parquet") for n in RELATIONS}
    for n, df in rel.items():
        assert not df.isnull().values.any(), f"NULLs in {n} violate ETNF"
    return rel


def _write_relations(rel):
    for n, df in rel.items():
        assert not df.isnull().values.any(), f"NULLs in {n} violate ETNF"
        df.to_parquet(ROOT / f"{n}.parquet", compression="zstd", index=False)


def build(con):
    """Join the relations, encode each fact, and fill the index. Idempotent.

    Entities are sorted for a stable `entities` column. The vectors no longer
    need it: they are stored on the uint16 phase grid, which absorbs the ~1e-14
    float difference that component order used to produce, so the bytes are equal
    either way.
    """
    rel = _read_relations()
    kind = dict(zip(rel["kinds"].kind_id, rel["kinds"].name))
    ent = dict(zip(rel["entities"].entity_id, rel["entities"].name))
    by_mem = {}
    for mid, eid in zip(rel["memory_entity"].memory_id, rel["memory_entity"].entity_id):
        by_mem.setdefault(mid, []).append(ent[eid])
    con.execute("DELETE FROM memory")
    for r in rel["memory"].itertuples():
        ents = sorted(by_mem.get(r.memory_id, []))
        vec = hrr.encode_fact(r.content, ents)
        con.execute("INSERT INTO memory(id, kind, content, entities, dim, vec, created)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (int(r.memory_id), kind[r.kind_id], r.content, " ".join(ents),
                     hrr.DIM, hrr.phases_to_u16(vec), r.created))
    con.commit()
    return len(rel["memory"])


def add(con, content, kind, entities):
    if kind not in KINDS:
        raise SystemExit(f"kind must be one of {KINDS}")
    import pandas as pd
    rel = _read_relations()
    if kind not in set(rel["kinds"].name):
        rel["kinds"] = pd.concat([rel["kinds"], pd.DataFrame(
            [{"kind_id": int(rel["kinds"].kind_id.max()) + 1, "name": kind}])], ignore_index=True)
    kid = dict(zip(rel["kinds"].name, rel["kinds"].kind_id))[kind]
    for e in entities:
        if e not in set(rel["entities"].name):
            rel["entities"] = pd.concat([rel["entities"], pd.DataFrame(
                [{"entity_id": int(rel["entities"].entity_id.max()) + 1, "name": e}])], ignore_index=True)
    eid = dict(zip(rel["entities"].name, rel["entities"].entity_id))
    mid = int(rel["memory"].memory_id.max()) + 1
    rel["memory"] = pd.concat([rel["memory"], pd.DataFrame([{
        "memory_id": mid, "kind_id": int(kid), "content": content,
        "created": datetime.date.today().isoformat()}])], ignore_index=True)
    if entities:
        rel["memory_entity"] = pd.concat([rel["memory_entity"], pd.DataFrame(
            [{"memory_id": mid, "entity_id": int(eid[e])} for e in entities])], ignore_index=True)
    _write_relations(rel)
    build(con)


def recall(con, query, n=5):
    q = hrr.encode_text(query)
    rows = []
    for mid, kind, content, ents, blob in con.execute(
            "SELECT id, kind, content, entities, vec FROM memory"):
        # The stored fact is a bundle; its content component is bound to the
        # content role, so unbind by that role before comparing.
        stored = hrr.unbind(hrr.u16_to_phases(blob), hrr.encode_atom(hrr.ROLE_CONTENT))
        rows.append((hrr.similarity(q, stored), mid, kind, content, ents))
    rows.sort(reverse=True)
    return rows[:n]


def verify(con):
    """Every stored vector must re-encode to itself from its own text."""
    bad = 0
    for mid, content, ents, dim, blob in con.execute(
            "SELECT id, content, entities, dim, vec FROM memory"):
        want = hrr.phases_to_u16(hrr.encode_fact(content, ents.split() if ents else []))
        if want != blob:
            print(f"  row {mid}: vector does not match its own content"); bad += 1
        if dim != hrr.DIM:
            print(f"  row {mid}: dim {dim} != {hrr.DIM}"); bad += 1
    print(f"{'MEMORY VERIFY PASS' if bad == 0 else f'{bad} rows wrong'}")
    return bad


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add");    a.add_argument("content"); a.add_argument("--kind", required=True); a.add_argument("--entities", nargs="*", default=[])
    r = sub.add_parser("recall"); r.add_argument("query");   r.add_argument("-n", type=int, default=5)
    sub.add_parser("verify"); sub.add_parser("build")
    args = p.parse_args()
    con = connect()
    if args.cmd == "build":
        print(f"built {build(con)} memories into {DB.name}")
    elif args.cmd == "add":
        add(con, args.content, args.kind, args.entities); print("stored")
    elif args.cmd == "recall":
        for s, mid, kind, content, ents in recall(con, args.query, args.n):
            print(f"  {s:+.4f}  [{kind}] {content}" + (f"  ({ents})" if ents else ""))
    else:
        sys.exit(1 if verify(con) else 0)


if __name__ == "__main__":
    main()
