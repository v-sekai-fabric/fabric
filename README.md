# fabric

A [repo](https://gerrit.googlesource.com/git-repo) manifest: 52 projects across 5 GitHub orgs, plus the checks and the ledger that say whether the work is moving.

```sh
repo init -u https://github.com/v-sekai-multiplayer-fabric/fabric && repo sync -j8
```

## The layout

`default.xml` gives each project a `path`, so the workspace is one hexagon and the numbered directories are its sides; that file's opening comment names all six. This repository is not among them — `repo init` clones it to `.repo/manifests` and reads the manifest from there, so edit it in that checkout. Every project states its own `remote` and `revision`, so one that omits either fails at `repo init` rather than inheriting a default. Every project tracks its repository's default branch. The zero that do not would be listed here, and the check that keeps this sentence true asks GitHub rather than the manifest.

## The ledger

`ledger/spent.beancount` books hours from git history, allocated so concurrent sessions never count the same wall clock twice. `ledger/planned.beancount` holds the plan in a different commodity, so beancount itself refuses to net an estimate against an hour that was spent.

```sh
python3 misc/scripts/ledger.py report --since 90   # SPENT, by lane
python3 misc/scripts/ledger.py path                # HYPOTHETICAL, the critical path
```

## Checks

`misc/checks` is a mix application, one module per concern, each runnable on its own.

```sh
mix check --fast       # the checkout answers these
mix check --slow       # what only a remote can answer
mix check --self-test  # each must fail on broken input
mix check authority    # one concern, and only it
mix dialyzer           # the gate's own types
```

Every claim above is derived from `default.xml` or the ledger and gated. `CLAUDE.md` says why.
