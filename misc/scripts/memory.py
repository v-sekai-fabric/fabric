#!/usr/bin/env python3
"""Fabric memory: ETNF relations as JSON Lines, built into a SQLite index.

The JSON Lines relations are the source and the only thing committed. The SQLite
database and its HRR vectors are derived: encode_atom is SHA-256 over the text,
so `build` reproduces them byte for byte from the same relations on any machine.
Committing both would store the same facts twice, and the derived copy is 31x
the size of the source it came from.

The vector is the index. A query is encoded the same way and compared by phase
cosine similarity, so recall is nearest-neighbour over meaning rather than a
substring match. Vectors are byte-identical to `tw_hrr.hpp` and to the planner's
holographic.py, which is what lets the same rows be read from C++ or Python.

The database is an ordinary SQLite file. It opens through the `weft_fdb` VFS when
one is registered -- the same VFS `datasource-queen` opens `queen` with -- and as a
plain file when none is, so the rows are the same either way.

  memory.py build                      jsonl -> sqlite, with the vectors
  memory.py add "<content>" --kind feedback --entities fabric cassie
  memory.py recall "<query>" [-n 5]
  memory.py verify
"""
import argparse, datetime, hashlib, json, sqlite3, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hrr

ROOT = pathlib.Path(__file__).resolve().parents[2] / "memory"
DB = ROOT / "fabric.sqlite3"          # derived, gitignored
RELATIONS = ("kinds", "entities", "memory", "memory_entity")
# Each relation sorts on its own key rather than on whatever column happens to come first
# alphabetically. The keys are uuid7, so sorting on them is sorting by creation time, and a
# new tuple lands at the end of the file instead of in the middle: the diff for one added
# memory is the lines that were added. Sorting memory_entity by entity_id would scatter them.
SORT_KEYS = {
    "kinds": ("kind_id",),
    "entities": ("entity_id",),
    "memory": ("memory_id",),
    "memory_entity": ("memory_id", "entity_id"),
}
VFS = "weft_fdb"          # registered by store-plane; absent means a plain file
KINDS = ("user", "feedback", "project", "reference")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
  id       TEXT PRIMARY KEY,
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


def tuple_id(kind, key, created):
    """A time-ordered identifier derived from the tuple, RFC 9562 version 8.

        48 bits  the creation date in unix milliseconds, big-endian
         4 bits  version 8, which the RFC reserves for exactly this
        74 bits  SHA-256 over the relation and the tuple's natural key

    Not a counter. `max(id) + 1` needs every existing tuple in hand to allocate one, so two
    people adding a memory on two branches take the same number and the merge keeps one
    row's content under the other's edges.

    Not a v7 either, though v7 was tried first and is what the shape is copied from. A v7
    takes its low bits from the clock and a random source, so it is not reproducible: regenerate
    these relations from any source -- a re-seed, a rebuild from prose, a second machine
    replaying the same additions -- and every identifier changes, every line of every file
    changes with it, and the diff says nothing about what actually moved. Deriving the low
    bits from the tuple instead means the same fact gets the same identifier wherever it is
    built, so a regenerated file is byte-identical where the facts are and differs only where
    they are not.

    The date prefix keeps the sort time-ordered, which is what makes an added tuple append to
    a sorted file rather than land in the middle of it. Two tuples with the same natural key
    on the same day are the same fact and collapse to one row, which is the behaviour a set
    of facts should have.
    """
    ms = int(datetime.datetime.strptime(created, "%Y-%m-%d")
             .replace(tzinfo=datetime.timezone.utc).timestamp()) * 1000
    h = hashlib.sha256(f"{kind}\0{key}".encode()).digest()
    b = bytearray(ms.to_bytes(6, "big") + h[:10])
    b[6] = 0x80 | (b[6] & 0x0F)          # version 8: custom
    b[8] = 0x80 | (b[8] & 0x3F)          # variant 10
    x = b.hex()
    return f"{x[0:8]}-{x[8:12]}-{x[12:16]}-{x[16:20]}-{x[20:32]}"


def _read_relations():
    """One JSON object per line, one line per tuple."""
    rel = {}
    for n in RELATIONS:
        rows = [json.loads(l) for l in (ROOT / f"{n}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        assert all(v is not None for r in rows for v in r.values()), f"nulls in {n} violate ETNF"
        rel[n] = rows
    return rel


def _write_relations(rel):
    """Sorted, one tuple per line, so a diff shows the tuples that changed."""
    for n, rows in rel.items():
        assert all(v is not None for r in rows for v in r.values()), f"nulls in {n} violate ETNF"
        key = SORT_KEYS[n]
        rows = sorted(rows, key=lambda r: tuple(r[c] for c in key))
        with open(ROOT / f"{n}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")


def build(con):
    """Join the relations, encode each fact, and fill the index. Idempotent.

    Entities are sorted for a stable `entities` column. The vectors no longer
    need it: they are stored on the uint16 phase grid, which absorbs the ~1e-14
    float difference that component order used to produce, so the bytes are equal
    either way.
    """
    rel = _read_relations()
    kind = {r["kind_id"]: r["name"] for r in rel["kinds"]}
    ent = {r["entity_id"]: r["name"] for r in rel["entities"]}
    by_mem = {}
    for r in rel["memory_entity"]:
        by_mem.setdefault(r["memory_id"], []).append(ent[r["entity_id"]])
    con.execute("DELETE FROM memory")
    for r in rel["memory"]:
        ents = sorted(by_mem.get(r["memory_id"], []))
        vec = hrr.encode_fact(r["content"], ents)
        con.execute("INSERT INTO memory(id, kind, content, entities, dim, vec, created)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (r["memory_id"], kind[r["kind_id"]], r["content"], " ".join(ents),
                     hrr.DIM, hrr.phases_to_u16(vec), r["created"]))
    con.commit()
    return len(rel["memory"])


def add(con, content, kind, entities):
    if kind not in KINDS:
        raise SystemExit(f"kind must be one of {KINDS}")
    rel = _read_relations()
    today = datetime.date.today().isoformat()
    if kind not in {r["name"] for r in rel["kinds"]}:
        rel["kinds"].append({"kind_id": tuple_id("kind", kind, today), "name": kind})
    kid = {r["name"]: r["kind_id"] for r in rel["kinds"]}[kind]
    for e in entities:
        if e not in {r["name"] for r in rel["entities"]}:
            rel["entities"].append({"entity_id": tuple_id("entity", e, today), "name": e})
    eid = {r["name"]: r["entity_id"] for r in rel["entities"]}
    mid = tuple_id("memory", content, today)
    rel["memory"].append({"memory_id": mid, "kind_id": kid, "content": content,
                          "created": today})
    for e in entities:
        rel["memory_entity"].append({"memory_id": mid, "entity_id": eid[e]})
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
    """Every stored vector must re-encode to itself, and every id must re-derive from its tuple.

    The second half is what makes the identifiers auditable rather than merely present. An id
    that no longer equals tuple_id of the row it sits on is an id that came from somewhere
    else -- a hand edit, a generator that was not this one, or a random source -- and that is
    the drift a random identifier introduces silently: nothing else in the file would notice.
    """
    bad = 0
    rel = _read_relations()
    first = min(r["created"] for r in rel["memory"])
    for r in rel["kinds"]:
        if r["kind_id"] != tuple_id("kind", r["name"], first):
            print(f"  kind {r['name']}: id does not derive from its tuple"); bad += 1
    for r in rel["entities"]:
        if r["entity_id"] != tuple_id("entity", r["name"], first):
            print(f"  entity {r['name']}: id does not derive from its tuple"); bad += 1
    for r in rel["memory"]:
        if r["memory_id"] != tuple_id("memory", r["content"], r["created"]):
            print(f"  memory {r['memory_id']}: id does not derive from its tuple"); bad += 1
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
