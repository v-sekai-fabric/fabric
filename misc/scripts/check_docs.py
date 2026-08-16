#!/usr/bin/env python3
"""Machine-check every claim README.md makes against default.xml, .gitignore and the remotes.

The manifest is the source of truth; the README is prose about it. Any disagreement is a
README bug. Run with no arguments to check, or --self-test to run each check against
deliberately broken input and prove it fails there.

    python3 misc/scripts/check_docs.py
    python3 misc/scripts/check_docs.py --self-test
    python3 misc/scripts/check_docs.py --local-only   # commit-time subset; the rest run at pre-push

Paths resolve from the repository root, not the working directory, so it runs from anywhere.

Exits non-zero on drift. An unmet precondition (no network, missing file) is a FAIL, never
a skip: a silent skip reads exactly like a pass.
"""

import collections
import concurrent.futures as cf
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "default.xml"
README = ROOT / "README.md"


def flat(text):
    """Collapse whitespace so a line wrap in the README cannot defeat a check."""
    return re.sub(r"\s+", " ", text)


def parse_manifest(text):
    root = ET.fromstring(text)
    remotes = {r.get("name"): r.get("fetch") for r in root.iter("remote")}
    projects = []
    for p in root.iter("project"):
        projects.append(
            {
                "name": p.get("name"),
                "remote": p.get("remote"),
                "revision": p.get("revision"),
                "org": (remotes.get(p.get("remote")) or "").rsplit("/", 1)[-1],
                "url": f"{remotes.get(p.get('remote'))}/{p.get('name')}.git",
            }
        )
    return root, remotes, projects


# --- checks: each takes (manifest_text, readme_text) and returns a list of failures -------


def check_counts(mtext, rtext):
    _, remotes, projects = parse_manifest(mtext)
    bad = []
    m = re.search(r"(\d+) projects across (\d+) GitHub orgs", flat(rtext))
    if not m:
        return ["README: no 'N projects across M GitHub orgs' sentence to check"]
    if int(m.group(1)) != len(projects):
        bad.append(f"README says {m.group(1)} projects, manifest has {len(projects)}")
    if int(m.group(2)) != len(remotes):
        bad.append(f"README says {m.group(2)} orgs, manifest has {len(remotes)} remotes")
    return bad


def check_revision_table(mtext, rtext):
    """The README lists only the projects that do NOT track the modal branch."""
    _, _, projects = parse_manifest(mtext)
    modal = collections.Counter(p["revision"] for p in projects).most_common(1)[0][0]
    m = re.search(r"Most projects track `(\w[\w.-]*)`", flat(rtext))
    if not m:
        return ["README: no 'Most projects track `x`' sentence to check"]
    bad = []
    if m.group(1) != modal:
        bad.append(f"README says most track {m.group(1)}, manifest's modal branch is {modal}")
    rows = set(re.findall(r"^\| `([\w.-]+)` \| `([^`]+)` \|$", rtext, re.M))
    actual = {(p["name"], p["revision"]) for p in projects if p["revision"] != modal}
    bad += [f"README documents {t}, not an exception in the manifest" for t in sorted(rows - actual)]
    bad += [f"manifest has exception {t}, README omits it" for t in sorted(actual - rows)]
    return bad


def check_explicit_attrs(mtext, _rtext):
    root, _, projects = parse_manifest(mtext)
    bad = [
        f"project {p['name']} missing {k}"
        for p in projects
        for k in ("remote", "revision")
        if not p[k]
    ]
    dflt = root.find("default")
    if dflt is not None:
        bad += [
            f"<default> carries {k}; it must inherit nothing"
            for k in ("remote", "revision")
            if dflt.get(k)
        ]
    return bad


def check_sync_j(mtext, _rtext):
    root, _, _ = parse_manifest(mtext)
    dflt = root.find("default")
    if dflt is None or not dflt.get("sync-j"):
        return ["<default> has no sync-j; without it repo fetches serially (jobs_network=1)"]
    return []


def check_revisions_exist(mtext, _rtext):
    _, _, projects = parse_manifest(mtext)
    bad = []
    with cf.ThreadPoolExecutor(16) as ex:
        for p, out in zip(projects, ex.map(_ls_remote, projects)):
            if out is None:
                bad.append(f"{p['name']}: cannot reach {p['url']}")
            elif not out:
                bad.append(f"{p['name']}: branch {p['revision']} does not exist on remote")
    return bad


def _ls_remote(p):
    out = subprocess.run(
        ["git", "ls-remote", "--heads", p["url"], p["revision"]],
        capture_output=True, text=True, timeout=120,
    )
    return None if out.returncode != 0 else out.stdout.strip()


def check_gitignore_covers_projects(mtext, _rtext):
    """Every child dir must be ignored, or a clone shows up as untracked in this repo."""
    _, _, projects = parse_manifest(mtext)
    return [
        f"{p['name']} is not gitignored"
        for p in projects
        if subprocess.run(
            ["git", "check-ignore", "-q", p["name"] + "/"], cwd=ROOT
        ).returncode
    ]


# Paths the README names that belong to another repository. These are verified against that
# repo rather than excused: a foreign reference is still a claim. Runtime paths (created by a
# tool, never tracked) are the only things skipped outright.
EXTERNAL = {
    "PITFALLS.md": "weftspun/logbook",
    "todo.md": "weftspun/logbook",
    "weftspun/logbook": None,  # the repo itself
    "dataflow-coco-gemx/check_readme_claims.py": "weftspun/dataflow-coco-gemx",
}
RUNTIME = {".repo/manifests", "node_modules/.bin", ".repo/"}

PATHISH = re.compile(r"`([^`\s]+)`")
FENCE = re.compile(r"```.*?```", re.S)
OWNED_SUFFIXES = (".py", ".xml", ".md", ".json", ".yml", ".yaml", ".toml", ".cfg", ".sh")


def _looks_like_repo_path(tok):
    if tok.startswith(("http", "~", "-", "<", "$", "@")) or ":" in tok or tok.endswith("/"):
        return False
    if tok.endswith(OWNED_SUFFIXES):
        return True
    # A slashed token is only a path if its first segment is really a directory here;
    # this keeps branch names such as feat/turboquant-on-master from being mistaken for one.
    return "/" in tok and (ROOT / tok.split("/")[0]).is_dir()


def check_referenced_paths(_mtext, rtext):
    """Every path the README names must exist -- here, or in the repo it is attributed to.

    Naming a file that is not there is the most common way documentation lies, and an
    allowlist of 'external' names just moves the lie somewhere unchecked.
    """
    # Backticked spans AND the words inside fenced blocks: a command in a code fence that
    # names a script which is not there is the same lie, and the more copy-pasted one.
    tokens = set(PATHISH.findall(rtext))
    for fence in FENCE.findall(rtext):
        tokens.update(fence.split())

    bad = []
    for tok in sorted(tokens):
        if tok in RUNTIME:
            continue
        if tok in EXTERNAL:
            repo = EXTERNAL[tok]
            if repo is None:
                target, path = tok, None
            else:
                target, path = repo, tok.split("/")[-1]
            api = f"repos/{target}" + (f"/contents/{path}" if path else "")
            out = subprocess.run(["gh", "api", api, "--jq", ".name"],
                                 capture_output=True, text=True, timeout=60)
            if out.returncode != 0:
                bad.append(f"README names `{tok}`, absent from {target}")
            continue
        if not _looks_like_repo_path(tok):
            continue
        if not (ROOT / tok).exists():
            bad.append(f"README names `{tok}`, which does not exist in this repo")
    return bad

CHECKS = [
    ("every path the README names exists", check_referenced_paths, "network"),
    ("README counts match the manifest", check_counts, "local"),
    ("README revision exceptions match the manifest", check_revision_table, "local"),
    ("every project states remote and revision", check_explicit_attrs, "local"),
    ("<default> sets sync-j so fetches are not serial", check_sync_j, "local"),
    ("every manifest revision exists on its remote", check_revisions_exist, "network"),
    ("every project directory is gitignored", check_gitignore_covers_projects, "local"),
]

# Each check paired with an edit that must break it. A gate never shown to fail certifies
# nothing -- see the Checks section of CLAUDE.md.
BREAKAGE = {
    "every path the README names exists": ("r", "misc/scripts/check_docs.py", "misc/scripts/nope_docs.py"),
    "README counts match the manifest": ("r", "42 projects across 5", "41 projects across 5"),
    "README revision exceptions match the manifest": ("m", 'revision="gyre"', 'revision="main"'),
    "every project states remote and revision": ("m", ' remote="meshula" revision="dev"', ""),
    "<default> sets sync-j so fetches are not serial": ("m", '<default sync-j="16" />', "<default />"),
    "every manifest revision exists on its remote": ("m", 'revision="dev"', 'revision="no-such-xyz"'),
    "every project directory is gitignored": ("m", 'name="LabRCSF"', 'name="not-ignored-xyz"'),
}


def main():
    mtext, rtext = open(MANIFEST).read(), open(README).read()
    self_test = "--self-test" in sys.argv
    failed = 0

    only_local = "--local-only" in sys.argv
    selected = [c for c in CHECKS if not (only_local and c[2] == "network")]
    deferred = [c[0] for c in CHECKS if only_local and c[2] == "network"]

    for label, fn, _kind in selected:
        bad = fn(mtext, rtext)
        print(f"{'FAIL' if bad else 'ok  '}  {label}")
        for b in bad:
            print(f"        {b}")
        failed += bool(bad)

    if self_test:
        print("\nnegative controls (each check must fail on broken input):")
        for label, fn, _kind in selected:
            which, old, new = BREAKAGE[label]
            m2 = mtext.replace(old, new) if which == "m" else mtext
            r2 = rtext.replace(old, new) if which == "r" else rtext
            if (m2, r2) == (mtext, rtext):
                print(f"FAIL  {label}: breakage pattern no longer matches; control is dead")
                failed += 1
                continue
            if fn(m2, r2):
                print(f"ok    {label} fails on broken input")
            else:
                print(f"FAIL  {label} PASSED on broken input — it is decoration")
                failed += 1

    for label in deferred:
        print(f"defer  {label}  (runs at pre-push, not skipped)")
    print(f"\n{failed} failing check(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
