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
                # `path` is optional and defaults to the name, which is what repo does.
                "path": p.get("path") or p.get("name"),
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

    # The sentence introducing the table counts its rows in words, and adding a row
    # does not update it. That went stale once already: the table grew to six while
    # the prose still said five, and every other check here passed, because they all
    # compare the rows and none of them reads the number.
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    n = re.search(r"The (\w+) that do not", flat(rtext))
    if not n:
        bad.append("README: no 'The <n> that do not' sentence to check")
    elif words.get(n.group(1).lower()) != len(actual):
        bad.append(f"README says '{n.group(1)}' exceptions, the manifest has {len(actual)}")
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


README_MAX = 40

# A mirror's README is upstream's. Editing it forks a document this project does not
# own, so the limit does not reach one. Each entry states the evidence rather than an
# opinion: two carry GitHub's fork flag, and the third carries upstream's own README.
MIRRORS = {
    # This project owns the Windows builds here and none of the code, so the README
    # is upstream's to write. GitHub carries the fork flag.
    "datasource-foundationdb": "apple/foundationdb",
    "idtx-flow": "Immersive-Data-Center-Management/idtx-flow",
    # No fork flag, and the README is still upstream's: it opens "# Godot Engine" and
    # links godotengine.org nineteen times.
    "entities-godot": "godotengine/godot",
}
OUR_REMOTE = "v-sekai-multiplayer-fabric"

# Names that are not this repository's to change, so recomposition gives way rather than
# forcing a rename. `path` and `name` are independent in repo -- a project sits on its side
# either way -- so recomposition is a convention this repository imposes and these are where
# it costs more than it is worth. This replaces the old `vendor/` prefix exemption, which
# excused a directory rather than a fact: `vendor/` said where code came from, and where it
# came from is not a position in the code. Each entry states its reason.
FIXED_NAMES = {
    "cassie": "the academic CASSIE project's Unity application; the name is the paper's",
    "cassie-data": "the sketch dataset recorded for that paper",
    "idtx-flow": "Immersive-Data-Center-Management/idtx-flow, mirrored",
    "LabRCSF": "meshula/LabRCSF; we have no admin on it, so we cannot rename it",
    # A repository name is also a published address when it serves Pages, and GitHub does
    # not redirect a Pages URL on rename. This one was renamed to contract-manuals and every
    # published RFD link 404'd until it was renamed back; check_pages_names is the gate.
    "multiplayer-fabric-manuals": "it publishes GitHub Pages, whose URL contains the name",
}


def _workspace_root():
    """Where the children sit.

    `repo init` puts this repository in `.repo/manifests` and the children two levels
    above it. A plain clone has them beside it. Both layouts are real, so this asks
    which one it is in rather than assuming.
    """
    if ROOT.name == "manifests" and ROOT.parent.name == ".repo":
        return ROOT.parent.parent
    return ROOT


def check_readme_length(mtext, rtext):
    """Every README this project is the primary source for stays under 40 lines.

    A README that grows past a screen stops being read, and the part nobody reads is
    the part that goes stale without anybody noticing. The limit applies to the git
    repositories on this project's own remote, and skips a mirror, whose README
    belongs to its upstream.

    A child that is not cloned is skipped rather than reported. This check therefore
    holds where it runs, which is every workspace that has the child on disk.
    """
    _, _, projects = parse_manifest(mtext)
    bad = []
    n = len(rtext.splitlines())
    if n >= README_MAX:
        bad.append(f"README.md is {n} lines, limit {README_MAX - 1}")
    ws = _workspace_root()
    for p in projects:
        if p["remote"] != OUR_REMOTE or p["name"] in MIRRORS:
            continue
        rp = ws / p["path"] / "README.md"
        if not rp.exists():
            continue
        n = len(rp.read_text(encoding="utf-8", errors="replace").splitlines())
        if n >= README_MAX:
            bad.append(f"{p['path']}/README.md is {n} lines, limit {README_MAX - 1}")
    return bad


def check_path_recomposes(mtext, _rtext):
    """A directory and its child MUST recompose to the repository name.

    `1-transport/gateway` is `transport-gateway`, and the leading digit sorts the ring
    rather than naming anything. This is what stops the checkout drifting from the names
    RFD 0111 decided: a path that no longer rebuilds its own name means one of the two
    moved without the other.

    The exceptions are in FIXED_NAMES, and each is a fact rather than a taste: that
    name belongs to another organisation, so no rename here can make the path rebuild it.
    Every other project was renamed to match the side it sits on.
    """
    _, _, projects = parse_manifest(mtext)
    bad = []
    for p in projects:
        path = p["path"]
        if p["name"] in FIXED_NAMES:
            continue
        if "/" in path:
            d, child = path.split("/", 1)
            rebuilt = re.sub(r"^\d-", "", d) + "-" + child
        else:
            rebuilt = path
        if rebuilt != p["name"]:
            bad.append(f"{path} rebuilds to {rebuilt}, but the repository is {p['name']}")
    return bad


def check_manifest_does_not_check_itself_out(mtext, _rtext):
    """No project may take `path="."`, because it gives repo two copies of this repository.

    This check previously required the opposite, and was wrong. `repo init` already clones
    this repository to `.repo/manifests` and reads the manifest from there, so a self-entry
    produces a second working copy at the workspace root: edits to `./default.xml` are
    invisible to repo, which never reads that file, and `repo sync` treats the root as a
    project and checks the manifest revision out over whatever is there.

    Both halves fired. A manifest rewrite at the root changed nothing, and the next sync
    discarded it along with an uncommitted README and reset HEAD, leaving a committed but
    unpushed CITATION.cff reachable only from the reflog.

    So the rule is one working copy of this repository, and it is the one repo reads.
    """
    _, _, projects = parse_manifest(mtext)
    return [f'{p["name"]} takes path=".", which gives repo a second working copy of this '
            "repository at the workspace root; edits there are ignored and then overwritten"
            for p in projects if p["path"] == "."]


def check_gitignore_covers_projects(mtext, _rtext):
    """Every child dir must be ignored, or a clone shows up as untracked in this repo.

    The checkout directory is `path` where a project states one, so this asks about the
    directory a clone lands in rather than the name it has on the remote. The two differ
    for every project that sits on a side of the hexagon.
    """
    _, _, projects = parse_manifest(mtext)
    return [
        f"{p['path']} is not gitignored"
        for p in projects
        if subprocess.run(
            ["git", "check-ignore", "-q", p["path"] + "/"], cwd=ROOT
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

# --- checks that read a child's documents -------------------------------------------
#
# These scan files in the children rather than text passed in, so a breakage that edits
# the manifest or the README cannot reach them. Every document they read goes through
# _child_docs(), and DOC_OVERRIDE replaces its result. That is what makes their negative
# controls real: the control injects a defective document and the check must go red.

CHILD_DOCS = ("README.md", "CLAUDE.md", "AGENTS.md")
DOC_OVERRIDE = None


def _child_docs(projects):
    """[(project_path, doc_name, text)] for our children, or the injected fixture."""
    if DOC_OVERRIDE is not None:
        return DOC_OVERRIDE
    ws, out = _workspace_root(), []
    for p in projects:
        if p["remote"] != OUR_REMOTE or p["name"] in MIRRORS:
            continue
        for name in CHILD_DOCS:
            f = ws / p["path"] / name
            if f.exists():
                out.append((p["path"], name, f.read_text(encoding="utf-8", errors="replace")))
    return out


def _name_for_path(projects, path):
    for p in projects:
        if p["path"] == path:
            return p["name"]
    return path.rsplit("/", 1)[-1]


def check_retired_words(mtext, _rtext):
    """RFD 0111 retired plane, edge plane, and domain as nouns for a process.

    Only the compounds that RFD 0111 names are matched. "Control plane" and "data plane"
    survive it, because they name a class of traffic rather than a process, so a document
    using either is not a finding.
    """
    _, _, projects = parse_manifest(mtext)
    pats = [
        (r"\bedge planes?\b", "edge plane -> transport layer"),
        (r"\bstore planes?\b", "store plane -> data source"),
        (r"\bplane rules?\b", "plane rule -> interactor rule"),
    ]
    bad = []
    for path, name, text in _child_docs(projects):
        for n, line in enumerate(text.splitlines(), 1):
            for pat, fix in pats:
                if re.search(pat, line, re.I):
                    bad.append(f"{path}/{name}:{n} {fix}")
    return bad


def _org_repo_names():
    out = subprocess.run(
        ["gh", "api", f"orgs/{OUR_REMOTE}/repos?per_page=100", "--paginate", "--jq", ".[].name"],
        capture_output=True, text=True, timeout=180)
    return set(out.stdout.split()) if out.returncode == 0 else set()


def check_names_resolve(mtext, _rtext):
    """No document may name a repository that only answers on a redirect.

    GitHub keeps every old name working, so a rename leaves prose that resolves and is
    wrong, and nothing fails anywhere. RFD 0111 asks for the pins in the same pass as the
    rename, and this is what makes that checkable rather than remembered.
    """
    _, _, projects = parse_manifest(mtext)
    live = _org_repo_names()
    if not live:
        return ["cannot list the organisation's repositories"]
    resolved, bad = {}, []
    for path, name, text in _child_docs(projects):
        # A fenced block is a command or a config, not prose making a claim, and a clone
        # URL that still redirects is somebody's working command line.
        prose = re.sub(r"```.*?```", "", text, flags=re.S)
        # A repository under another owner is that owner's, whatever it is called here.
        # ahujasid/blender-mcp is upstream of transport-blender-mcp, and resolving the bare
        # token against this organisation turns a correct citation into a rename to apply.
        prose = re.sub(rf"github\.com/(?!{re.escape(OUR_REMOTE)}/)[\w.-]+/[\w.-]+", "", prose)
        for tok in sorted(set(re.findall(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+){1,4}\b", prose))):
            if tok in live:
                continue
            if tok not in resolved:
                r = subprocess.run(["gh", "api", f"repos/{OUR_REMOTE}/{tok}", "--jq", ".name"],
                                   capture_output=True, text=True, timeout=30)
                resolved[tok] = r.stdout.strip() if r.returncode == 0 else None
            if resolved[tok] and resolved[tok] != tok:
                bad.append(f"{path}/{name} names {tok}, which is now {resolved[tok]}")
    return sorted(set(bad))


# Google's third-party licence policy, https://opensource.google/documentation/reference/thirdparty/licenses
#
# Notice / permissive / unencumbered ship anywhere. Reciprocal ships but obliges
# source mirroring. Restricted taints and obliges disclosure. The last set cannot
# be used at all. A repository with no licence at all is the worst case of the
# lot: default copyright reserves every right, so nobody may redistribute it, and
# publishing it openly does not change that.
LICENCE_RESTRICTED = {
    "GPL-1.0", "GPL-2.0", "GPL-3.0", "LGPL-2.0", "LGPL-2.1", "LGPL-3.0",
    "CC-BY-SA-4.0", "CERN-OHL-S-2.0",
}
LICENCE_FORBIDDEN = {
    "AGPL-1.0", "AGPL-3.0", "SSPL-1.0", "OSL-3.0", "CPAL-1.0", "EUPL-1.1",
    "EUPL-1.2", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "CC-BY-NC-ND-4.0",
    "Watcom-1.0", "BUSL-1.1",
}
LICENCE_UNSET = {"", "NONE", "NOASSERTION", "null", None}

# Injected by the self-test. A check that asks GitHub cannot be broken by editing
# a file here, so its control replaces the answer instead.
LICENCE_OVERRIDE = None


def _licence_of(org, name):
    if LICENCE_OVERRIDE is not None:
        return LICENCE_OVERRIDE.get(name, "MIT")
    out = subprocess.run(["gh", "api", f"repos/{org}/{name}", "--jq", '.license.spdx_id // "NONE"'],
                         capture_output=True, text=True, timeout=30)
    return out.stdout.strip() if out.returncode == 0 else "NONE"


PAGES_OVERRIDE = None
LEDGER_OVERRIDE = None
SEPARATION_OVERRIDE = None

# One 2-4 commit session is te 1.16 h in the table CLAUDE.md derives from git, and it is
# the smallest unit of real work this organisation does. A month booking less than that to
# the deliverable did not work on it; 0.06 h -- the reading when this check was written --
# is a rename sweep brushing a file, not a session.
MIN_DELIVERY_H = 1.16
DELIVERY_WINDOW_DAYS = 30


def check_plan_and_spend_are_separate(_mtext, _rtext):
    """A planned hour and a spent hour MUST never share an account or a unit.

    The plan estimates work nobody has done, so it books liabilities: an obligation
    outstanding. The ledger books expenses: hours that went somewhere. Put an estimate in
    an expense account and the plan reports itself as progress, which is the failure this
    whole ledger exists to stop, arriving from the inside.

    The unit does most of this work without help: planned hours are PLANNED-HOURS and spent
    hours are HOURS, and beancount will not balance across commodities, so netting one
    against the other fails at parse time with exit 1. This check is the belt to that
    braces -- it reads both files, intersects their account names and their commodities, and
    fails on any overlap, because the day somebody unifies the units to tidy them up is the
    day the tool stops refusing.
    """
    if SEPARATION_OVERRIDE is not None:
        # The check reads two files this repository generates, so no manifest edit can
        # perturb it. The control supplies the overlap instead.
        return [f"{a} carries both planned and spent hours; an estimate reads as progress"
                for a in sorted(SEPARATION_OVERRIDE)]
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import ledger

    def accounts(path):
        out = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            for kind in ("Assets:", "Liabilities:", "Equity:", "Income:", "Expenses:"):
                if s.startswith(kind) or s.startswith("open " + kind):
                    out.add(s.replace("open ", "").split()[0])
        return out

    for f in (ledger.SPENT, ledger.PLANNED):
        if not f.exists():
            return [f"{f.name} is missing"]
    shared = accounts(ledger.SPENT) & accounts(ledger.PLANNED)
    if shared:
        return [f"{a} carries both planned and spent hours; an estimate reads as progress"
                for a in sorted(shared)]
    return []


def check_deliverable_moved(_mtext, _rtext):
    """The deliverable MUST take hours every month, or the build says so.

    Every other check here asks whether a document is true. This one asks whether anything
    was delivered, because those are not the same and the difference is what went wrong:
    over ninety days 21.2% of measured hours went to documents about the mesh and 7.4% to
    the mesh, while every gate stayed green throughout. A green gate closes a check, not a
    deliverable.

    The ledger is read rather than recomputed, so this answers from the file that is
    committed. bean-check says the file is well formed; this says what is in it. Beancount
    is an operating-system tool here the way gcc is -- installed, never vendored, never
    imported -- so a missing bean-check is an unmet precondition and therefore a failure,
    never a skip.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import ledger

    if LEDGER_OVERRIDE is not None:
        hours, window = LEDGER_OVERRIDE
    else:
        if not ledger.SPENT.exists():
            return [f"{ledger.SPENT.name} is missing; nothing counts what was delivered"]
        r = subprocess.run(["bean-check", str(ledger.SPENT)], capture_output=True, text=True)
        if r.returncode != 0:
            first = ((r.stderr or r.stdout).strip().splitlines() or ["?"])[0]
            return [f"bean-check rejects the ledger: {first[:120]}"]
        hours, window = ledger.delivery_hours(DELIVERY_WINDOW_DAYS), DELIVERY_WINDOW_DAYS
    if hours < MIN_DELIVERY_H:
        return [f"{hours:.2f} h booked to the deliverable in {window} days, under "
                f"{MIN_DELIVERY_H} h. Whatever else merged, the thing being built did not move."]
    return []



def check_pages_names(mtext, _rtext):
    """A project that serves GitHub Pages MUST keep the name its published URL contains.

    A repository rename redirects git and the web UI. It does not redirect Pages: the site
    moves to org.github.io/<new-name>/ and every published link 404s, with nothing in the
    repository to notice. That is the failure this exists to stop, and it is not
    hypothetical -- `multiplayer-fabric-manuals` was renamed to `contract-manuals` for the
    hexagon layout and took every published RFD link with it.

    So the name is a published address, and recomposition gives way to it. The check reads
    the URL GitHub actually serves rather than a list kept by hand, because a list is the
    thing that goes stale when Pages is switched on for something new.
    """
    _, _, projects = parse_manifest(mtext)
    bad = []
    for p in projects:
        if p["remote"] != OUR_REMOTE:
            continue
        url = _pages_url(p["org"], p["name"])
        if url is None:
            continue
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        if slug != p["name"]:
            bad.append(f"{p['name']} serves Pages at {url}, whose name is {slug}; "
                       "a Pages URL does not redirect, so the published links are dead")
    return bad


def _pages_url(org, name):
    if PAGES_OVERRIDE is not None:
        return PAGES_OVERRIDE.get(name)
    r = subprocess.run(["gh", "api", f"repos/{org}/{name}/pages", "--jq", ".html_url"],
                       capture_output=True, text=True)
    return r.stdout.strip() or None if r.returncode == 0 else None


def check_licences(mtext, _rtext):
    """Every repository this organisation owns MUST carry a usable licence.

    Checked against Google's third-party policy. A restricted licence taints what
    links it and obliges disclosure; a forbidden one cannot be shipped at all. No
    licence is worse than either: default copyright reserves every right, so an
    unlicensed repository is one nobody may redistribute, including us.
    """
    root, remotes, projects = parse_manifest(mtext)
    org = (remotes.get(OUR_REMOTE) or "").rsplit("/", 1)[-1]
    bad = []
    for p in projects:
        if p["remote"] != OUR_REMOTE or p["name"] in MIRRORS:
            continue
        lic = _licence_of(org, p["name"])
        if lic in LICENCE_UNSET:
            bad.append(f"{p['name']} has no licence; default copyright reserves every right")
        elif lic in LICENCE_FORBIDDEN:
            bad.append(f"{p['name']} is {lic}, which the policy forbids outright")
        elif lic in LICENCE_RESTRICTED:
            bad.append(f"{p['name']} is {lic}, restricted: it taints what links it")
    return sorted(bad)


CHECKS = [
    ("every path the README names exists", check_referenced_paths, "network"),
    ("README counts match the manifest", check_counts, "local"),
    ("README revision exceptions match the manifest", check_revision_table, "local"),
    ("every project states remote and revision", check_explicit_attrs, "local"),
    ("<default> sets sync-j so fetches are not serial", check_sync_j, "local"),
    ("every manifest revision exists on its remote", check_revisions_exist, "network"),
    ("no project checks this repository out twice", check_manifest_does_not_check_itself_out, "local"),
    ("every project directory is gitignored", check_gitignore_covers_projects, "local"),
    ("every README this project owns is under 40 lines", check_readme_length, "local"),
    ("every path recomposes to its repository name", check_path_recomposes, "local"),
    ("no document uses a word RFD 0111 retired", check_retired_words, "local"),
    ("no document names a repository that moved", check_names_resolve, "network"),
    ("every repository we own carries a usable licence", check_licences, "network"),
    ("a project that serves Pages keeps the name its URL contains", check_pages_names, "network"),
    ("the deliverable moved this month", check_deliverable_moved, "local"),
    ("planned and spent hours never share an account", check_plan_and_spend_are_separate, "local"),
]

# Each check paired with an edit that must break it. A gate never shown to fail certifies
# nothing -- see the Checks section of CLAUDE.md.
BREAKAGE = {
    "every path the README names exists": ("r", "misc/scripts/check_docs.py", "misc/scripts/nope_docs.py"),
    "README counts match the manifest": ("r", "45 projects across 5", "44 projects across 5"),
    # Re-adding the self-entry is the defect, so the control adds one.
    "no project checks this repository out twice": (
        "m", '<project name="transport-asset"', '<project name="fabric" path="." remote="v-sekai-multiplayer-fabric" revision="main" />\n  <project name="transport-asset"'),
    # Breaking the count word rather than a row: the row comparison would catch a
    # changed revision anyway, and the word is the half that had no control at all.
    "README revision exceptions match the manifest": ("r", "The six that do not", "The five that do not"),
    "every project states remote and revision": ("m", ' remote="meshula" revision="dev"', ""),
    "<default> sets sync-j so fetches are not serial": ("m", '<default sync-j="16" />', "<default />"),
    "every manifest revision exists on its remote": ("m", 'revision="dev"', 'revision="no-such-xyz"'),
    # The checkout directory is `path`, so the edit that breaks this check moves the clone
    # out of an ignored directory. Editing the name instead leaves `path` ignored and the
    # check passes, which makes the control certify nothing.
    "every project directory is gitignored": ("m", 'path="4-entities/LabRCSF"', 'path="not-ignored-xyz"'),
    # Padding the README past the limit is the failure this gate exists to catch, and
    # it exercises the same line count the real check reads.
    "every README this project owns is under 40 lines": ("r", "## Checks", "## Checks" + "\n" * 45),
    # Moving a project to a directory its name does not rebuild is exactly the drift
    # this gate exists to catch.
    "every path recomposes to its repository name": ("m", 'path="4-entities/images"', 'path="4-entities/pictures"'),
    # The three checks below read a child's documents, which no edit to the manifest or to
    # this repository's README can reach. Their controls inject a defective document
    # instead, so each one is shown failing on the exact defect it exists to catch.
    "no document uses a word RFD 0111 retired": (
        "d", [("1-transport/fanout", "README.md", "An edge plane is a plane with networking.\n")]),
    "every repository we own carries a usable licence": ("l", {"transport-fanout": "AGPL-3.0"}),
    "no document names a repository that moved": (
        "d", [("1-transport/fanout", "README.md", "It reads from fabric-authority-plane every tick.\n")]),
    # Asking GitHub what it serves cannot be perturbed by editing a file here, so the
    # control replaces the answer -- with the exact URL the real rename produced.
    "a project that serves Pages keeps the name its URL contains": (
        "p", {"multiplayer-fabric-manuals":
              "https://v-sekai-multiplayer-fabric.github.io/contract-manuals/"}),
    # The ledger is generated from git, so no edit here can move an hour into or out of a
    # window. The control replaces the reading instead, with the exact one that was true
    # when this check was written: 0.06 h in thirty days.
    "the deliverable moved this month": ("g", (0.06, 30)),
    # Booking a planned hour to the account the ledger spends from is the exact confusion
    # this check exists to stop, so the control makes that edit.
    "planned and spent hours never share an account": ("s", {"Expenses:Delivery:Mesh"}),
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
        global DOC_OVERRIDE, PAGES_OVERRIDE, LEDGER_OVERRIDE, SEPARATION_OVERRIDE
        for label, fn, _kind in selected:
            spec = BREAKAGE[label]
            m2, r2 = mtext, rtext
            DOC_OVERRIDE = PAGES_OVERRIDE = LEDGER_OVERRIDE = None
            SEPARATION_OVERRIDE = None
            if spec[0] == "s":
                SEPARATION_OVERRIDE = spec[1]
            elif spec[0] == "g":
                LEDGER_OVERRIDE = spec[1]
            elif spec[0] == "p":
                PAGES_OVERRIDE = spec[1]
            elif spec[0] == "l":
                # Asking GitHub cannot be perturbed by editing a file here, so the
                # control replaces the answer the check would have received.
                global LICENCE_OVERRIDE
                LICENCE_OVERRIDE = spec[1]
            elif spec[0] == "d":
                # A check that reads a child's documents can only be broken by giving it a
                # broken document. Passing it the real tree would prove nothing.
                DOC_OVERRIDE = spec[1]
            else:
                which, old, new_ = spec
                m2 = mtext.replace(old, new_) if which == "m" else mtext
                r2 = rtext.replace(old, new_) if which == "r" else rtext
                if (m2, r2) == (mtext, rtext):
                    print(f"FAIL  {label}: breakage pattern no longer matches; control is dead")
                    failed += 1
                    continue
            try:
                broke = bool(fn(m2, r2))
            finally:
                DOC_OVERRIDE = None
                LICENCE_OVERRIDE = None
                PAGES_OVERRIDE = None
                LEDGER_OVERRIDE = None
                SEPARATION_OVERRIDE = None
            if broke:
                print(f"ok    {label} fails on broken input")
            else:
                print(f"FAIL  {label} PASSED on broken input — it is decoration")
                failed += 1

    # A document check with no children on disk passes because it saw nothing, which reads
    # exactly like passing because everything was clean. Say which it was.
    seen = len({d[0] for d in _child_docs(parse_manifest(mtext)[2])})
    print(f"note   the document checks scanned {seen} children"
          + ("; a bare clone has none, and they hold where the workspace is" if not seen else ""))

    for label in deferred:
        print(f"defer  {label}  (runs at pre-push, not skipped)")
    print(f"\n{failed} failing check(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
