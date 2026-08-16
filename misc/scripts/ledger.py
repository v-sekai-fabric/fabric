#!/usr/bin/env python3
"""Fabric delivery: git history booked as double-entry hours, checked by bean-check.

Ninety days of commits went 5.3% to the mesh being delivered and 27.2% to documents
about it, and nobody noticed because nothing counted. A ledger counts. Double entry is
the right shape for it: an hour cannot be spent without being booked against where it
came from, so the lane split falls out of the file instead of being argued.

Beancount is an operating-system tool here, the way gcc is. `brew install beancount`,
never vendored and never imported -- it is GPL-2.0, which this project's licence policy
files as restricted, so keeping it outside the tree is a licence decision as much as a
dependency one. What is tracked is the plain-text accounting file. This is the same
arrangement `memory.py` has with `usdcat`: the artefact is ours, the validator is the
system's, and the validator is what keeps a hand-written emitter honest.

  ledger.py build            git sessions -> ledger/delivery.beancount
  ledger.py report [--since N]   the lane split, as a command rather than a paragraph
  ledger.py path             the critical path, computed from ledger/plan.beancount
  ledger.py verify           bean-check, then regeneration must be byte-identical
"""
import argparse
import collections
import datetime
import math
import pathlib
import random
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "ledger" / "delivery.beancount"
PLAN = ROOT / "ledger" / "plan.beancount"

# A gap longer than this means somebody went away rather than worked slowly. Same
# definition the PERT table in CLAUDE.md is derived from, so the two agree by construction.
SESSION_GAP_H = 4

# The deliverable. One at a time, and it changes only when the previous one is finished.
DELIVERABLE = ("A player draws a closed curve in VR, gets a mesh back, "
               "and the mesh is correct by a check that can fail")

# Which lane a checkout's hours are booked to. The mesh chain is named explicitly because
# it is the one the build asks about; everything else we author falls to Other.
LANES = {
    "2-contract/patch-verify": "Expenses:Delivery:Mesh",
    "3-interactor/triangulation": "Expenses:Delivery:Mesh",
    "3-interactor/cassie": "Expenses:Delivery:Mesh",
    "3-interactor/sketch": "Expenses:Delivery:Mesh",
    "2-contract/manuals": "Expenses:Docs",
    ".": "Expenses:Fabric",
}
DEFAULT_LANE = "Expenses:Other"
ACCOUNTS = ["Income:Sessions", "Expenses:Delivery:Mesh", "Expenses:Docs",
            "Expenses:Fabric", "Expenses:Other"]

# Repositories another organisation authors. Their commits are not this project's hours,
# and booking them would drown the lanes that are. Kept in step with check_docs.py's
# FIXED_NAMES and MIRRORS by naming the checkout rather than the repository.
NOT_OURS = {
    "6-datasource/foundationdb", "4-entities/godot", "4-entities/LabRCSF",
    "6-datasource/cassie-data", "6-datasource/idtx-flow", "4-entities/model-explorer",
    "1-transport/xr-grid", ".repo/repo", ".repo/manifests",
}


def _checkouts():
    """Every git checkout in the workspace, named by its path relative to the root.

    Two levels because the manifest puts most children on a side of the hexagon, one
    directory down; a one-level glob finds the few at the root and reports the rest as
    absent, which is the answer this exists to prevent.
    """
    ws = ROOT
    seen = []
    for pat in ("*/.git", "*/*/.git"):
        for g in ws.glob(pat):
            rel = str(g.parent.relative_to(ws))
            if rel not in NOT_OURS:
                seen.append((rel, g.parent))
    if (ws / ".git").exists():
        seen.append((".", ws))
    return sorted(set(seen))


def _sessions(path):
    """Commits grouped into sessions, each as (start, end, count, last subject).

    The cost of a session is the span from its first commit to its last. That is a
    measurement, where the PERT table holds estimates -- the ledger is actuals and the
    plan is guesses, and mixing them would make both unfalsifiable. The bias is stated
    rather than fudged: a span between commits excludes the thinking before the first
    one, so a single-commit session books zero and this ledger under-counts.
    """
    out = subprocess.run(["git", "-C", str(path), "log", "--since=1.year", "--pretty=%ct\t%s"],
                         capture_output=True, text=True).stdout.splitlines()
    rows = []
    for line in out:
        ct, _, subj = line.partition("\t")
        try:
            rows.append((int(ct), subj))
        except ValueError:
            pass
    rows.sort()
    if not rows:
        return []
    sessions, cur = [], [rows[0]]
    for prev, this in zip(rows, rows[1:]):
        if this[0] - prev[0] > SESSION_GAP_H * 3600:
            sessions.append(cur)
            cur = []
        cur.append(this)
    sessions.append(cur)
    return [(s[0][0], s[-1][0], len(s), [c[1] for c in s]) for s in sessions]


def _escape(s):
    """Beancount narration is a double-quoted string, so a quote in a subject ends it."""
    return s.replace("\\", "").replace('"', "'")


def build():
    entries = []
    for rel, path in _checkouts():
        lane = LANES.get(rel, DEFAULT_LANE)
        for start, end, n, subjects in _sessions(path):
            hours = (end - start) / 3600.0
            day = datetime.datetime.utcfromtimestamp(end).date().isoformat()
            entries.append((day, rel, lane, hours, n, subjects))
    entries.sort()

    first = entries[0][0] if entries else datetime.date.today().isoformat()
    today = datetime.date.today().isoformat()
    lines = [
        ";; Generated by misc/scripts/ledger.py -- do not edit.",
        ";;",
        ";; A session is a run of commits with no gap over four hours, and its cost is",
        ";; the span from its first commit to its last. Measured, not estimated: the",
        ";; PERT table in CLAUDE.md holds guesses about work not yet done, and this",
        ";; holds what happened. A one-commit session spans zero, so this under-counts,",
        ";; which is a stated bias rather than a corrected one.",
        ";;",
        ";; Sessions in different checkouts overlap. Work moves between repositories inside",
        ";; one sitting, so their spans are concurrent and summing them counts the same wall",
        ";; clock more than once -- 2026-08-16 totals 40.04 h, which no day contains. The",
        ";; totals are therefore effort by lane, not elapsed time, and the share between",
        ";; lanes is the number worth reading. Elapsed time would need the union of the",
        ";; spans, which is a different report and is not this one.",
        "",
        'option "title" "fabric-delivery: hours booked from git sessions"',
        'option "operating_currency" "HOURS"',
        "",
    ]
    for a in ACCOUNTS:
        lines.append(f"{first} open {a}  HOURS")
    lines += ["", f'{today} event "deliverable" "{_escape(DELIVERABLE)}"', ""]
    for day, rel, lane, hours, n, subjects in entries:
        # The narration is what the session ended on; `steps` is every commit in it, in
        # order. A session that books two hours and says only what it finished with tells
        # you the cost and hides the work, which is the half worth reading later.
        lines.append(f'{day} * "{_escape(rel)}" "{_escape(subjects[-1])[:88]}"')
        lines.append(f"  commits: {n}")
        steps = " | ".join(_escape(s)[:72] for s in subjects)
        lines.append(f'  steps: "{steps[:900]}"')
        lines.append(f"  {lane:<26} {hours:8.2f} HOURS")
        lines.append(f"  Income:Sessions")
        lines.append("")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return len(entries)


def _postings(since_days=None):
    """(date, account, hours) for every expense posting, read back from the file.

    Read back rather than recomputed, so `report` and the delivery gate answer from the
    artefact that is committed. A number produced by the generator and never read from
    the file would prove the generator agrees with itself.
    """
    cutoff = None
    if since_days is not None:
        cutoff = datetime.date.today() - datetime.timedelta(days=since_days)
    out, day = [], None
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        head = line[:10]
        if len(line) > 11 and line[4] == "-" and line[7] == "-" and " * " in line:
            try:
                day = datetime.date.fromisoformat(head)
            except ValueError:
                day = None
        elif line.startswith("  Expenses:") and day is not None:
            acct, _, amt = line.strip().partition(" ")
            hours = float(amt.replace("HOURS", "").strip())
            if cutoff is None or day >= cutoff:
                out.append((day, acct, hours))
    return out


def report(since_days):
    rows = _postings(since_days)
    tot = collections.Counter()
    for _, acct, hours in rows:
        tot[acct] += hours
    total = sum(tot.values()) or 1.0
    print(f"  last {since_days} days, from {LEDGER.relative_to(ROOT)}")
    for acct, hours in sorted(tot.items(), key=lambda x: -x[1]):
        print(f"    {acct:<26} {hours:8.2f} h  {hours / total * 100:5.1f}%")
    print(f"    {'TOTAL':<26} {total:8.2f} h")
    return 0


def delivery_hours(window_days=30):
    """Hours booked to the mesh in the trailing window. What the build asks about."""
    return sum(h for _, a, h in _postings(window_days) if a.startswith("Expenses:Delivery"))


def verify():
    bad = 0
    for f in (LEDGER, PLAN):
        # One file per invocation: bean-check takes a single FILENAME and rejects a second
        # as an extra argument, which reads like a ledger error and is not one.
        r = subprocess.run(["bean-check", str(f)], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  bean-check rejects {f.name}:")
            for line in (r.stderr or r.stdout).strip().splitlines()[:4]:
                print(f"    {line}")
            bad += 1
        else:
            print(f"  bean-check ok  {f.name}")
    before = LEDGER.read_text(encoding="utf-8")
    build()
    after = LEDGER.read_text(encoding="utf-8")
    if before != after:
        LEDGER.write_text(before, encoding="utf-8")
        print("  the ledger is not what git says; it was hand-edited")
        bad += 1
    else:
        print("  regenerates byte-identical")
    print("LEDGER VERIFY PASS" if bad == 0 else f"{bad} problem(s)")
    return bad


def _plan_tasks():
    """The planned tasks, read out of the plan ledger's transaction metadata.

    The plan is a beancount file rather than a diagram because a diagram goes stale and
    nothing notices. Here a task is a transaction, its three-point estimate is metadata,
    and the path below is computed rather than drawn -- so an estimate cannot disagree
    with the picture of it, which is how 231/234 outlived the code that reached 1360/1360.
    """
    tasks, cur = {}, None
    for line in PLAN.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("task:"):
            cur = s.split('"')[1]
            tasks[cur] = {"id": cur, "depends": "", "o": 0.0, "m": 0.0, "p": 0.0,
                          "what": "", "done": ""}
        elif cur and s.startswith("depends:"):
            tasks[cur]["depends"] = s.split('"')[1]
        elif cur and s.startswith("done:"):
            tasks[cur]["done"] = s.split(":", 1)[1].strip()
        elif cur and s.split(":")[0] in ("optimistic", "likely", "pessimistic"):
            k, _, v = s.partition(":")
            tasks[cur][{"optimistic": "o", "likely": "m", "pessimistic": "p"}[k]] = float(v)
    # The narration carries what the task is; re-read to attach it to the id below it.
    narr = None
    for line in PLAN.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("2") and '"plan"' in s:
            narr = s.split('"plan"')[1].strip().strip('"')
        elif s.startswith("task:") and narr:
            tasks[s.split('"')[1]]["what"] = narr
    for t in tasks.values():
        t["te"] = (t["o"] + 4 * t["m"] + t["p"]) / 6
    return tasks


def _open_tasks():
    """Tasks still to do. A done task stays in the file as a record and leaves the path."""
    return {k: v for k, v in _plan_tasks().items() if not v["done"]}


def _predictive(task, draws, rng):
    """Draws from a task's posterior predictive, recovered from its three points.

    The plan stores quantiles, not parameters, so the lognormal is read back out of them:
    the median fixes mu, and the ratio of the 99th percentile to the median fixes sigma,
    because ln(p99/m) is 2.326 sigma. Nothing else in the file is needed, which keeps the
    beancount entries the only source and this function a reader of them.
    """
    m = max(task["m"], 1e-6)
    sigma = max(math.log(max(task["p"], m * 1.0001) / m) / 2.326, 1e-6)
    mu = math.log(m)
    return [math.exp(rng.gauss(mu, sigma)) for _ in range(draws)]


def path(draws=40000):
    """Longest chain of dependent tasks, and when it finishes with 99% probability.

    The chain's total is not a sum of three-point estimates. Lognormals do not add in
    closed form, and adding the p99s would answer a different question -- every task
    simultaneously at its worst, which is far more pessimistic than the chain being late.
    So the tasks are sampled together and the total's own quantiles are read off. The seed
    is fixed, because a plan that changes when you look at it twice is not a plan.
    """
    tasks = _open_tasks()

    def chain(tid, seen=()):
        if tid in seen:
            raise SystemExit(f"plan has a dependency cycle at {tid}")
        t = tasks[tid]
        dep = t["depends"]
        prev = chain(dep, seen + (tid,)) if dep else []
        return prev + [tid]

    chains = {tid: chain(tid) for tid in tasks}
    longest = max(chains.values(), key=lambda c: sum(tasks[i]["te"] for i in c))
    span = sum(tasks[i]["te"] for i in longest)
    oncrit = set(longest)

    rng = random.Random(20260816)
    sims = [_predictive(tasks[i], draws, rng) for i in longest]
    totals = sorted(sum(c) for c in zip(*sims))
    q = lambda f: totals[min(len(totals) - 1, int(f * len(totals)))]

    print(f"  critical path  {' -> '.join(longest)}")
    print(f"    te (sum of three-point)      {span:>7.2f} h")
    print(f"    50% done by                  {q(.50):>7.2f} h")
    print(f"    99% done by                  {q(.99):>7.2f} h")
    print(f"     1% done by                  {q(.01):>7.2f} h")
    print()
    print(f"  {'':<4} {'task':<42} {'o':>6} {'m':>6} {'p':>6} {'te':>6} {'slack':>7}")
    for tid, t in sorted(tasks.items(), key=lambda x: (x[0] not in oncrit, x[0])):
        on = tid in oncrit
        slack = 0.0 if on else span - sum(tasks[i]["te"] for i in chains[tid])
        print(f"  {'path' if on else '':<4} {t['what'][:42]:<42} {t['o']:>6.2f} {t['m']:>6.2f} "
              f"{t['p']:>6.2f} {t['te']:>6.2f} {slack:>7.2f}")
    done = [v for v in _plan_tasks().values() if v["done"]]
    if done:
        print()
        for d in sorted(done, key=lambda x: x["done"]):
            print(f"  done {d['what'][:42]:<42} {d['done']}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    r = sub.add_parser("report")
    r.add_argument("--since", type=int, default=90)
    sub.add_parser("path")
    sub.add_parser("verify")
    a = p.parse_args()
    if a.cmd == "build":
        print(f"booked {build()} sessions into {LEDGER.relative_to(ROOT)}")
        return 0
    if a.cmd == "report":
        return report(a.since)
    if a.cmd == "path":
        return path()
    return 1 if verify() else 0


if __name__ == "__main__":
    sys.exit(main())
