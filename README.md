# fabric

A [repo](https://gerrit.googlesource.com/git-repo) manifest that groups the gyre
dependencies, so one command checks them all out and one command runs git across all of
them. 42 projects across 5 GitHub orgs.

## Setup

```sh
brew install repo                 # or: curl the launcher into ~/.local/bin

mkdir fabric-ws && cd fabric-ws
repo init -u https://github.com/v-sekai-multiplayer-fabric/fabric
repo sync -j8                     # clone every project named in default.xml
```

`repo init` checks this repo out into `.repo/manifests` and places the children beside it in
the workspace root. Nothing is vendored here.

## Use

```sh
repo sync -j8                     # bring every child up to its manifest revision
repo status                       # status across all of them
repo forall -c 'git log -1 --oneline'   # run any command in each
repo start <branch> <project>     # start work in a child (sync leaves detached HEADs)
```

`repo sync` parks each project on a detached HEAD at its manifest revision, so `repo start`
before editing. `repo sync -j8` fetches eight projects at a time; add `--partial-clone` at
init for large histories.

## Revisions

Every project states its own `remote` and `revision`. The `<default>` element carries neither,
only `sync-j`, so a project that omits either fails at `repo init` rather than inheriting a
default nobody chose — verified: removing both attributes from one project gives
`fatal: no remote for project <name>`.

Most projects track `main`. The five that do not:

| project | revision |
|---|---|
| `entities-godot` | `gyre` |
| `datasource-flow` | `main-fabric` |
| `lean-http3-queue` | `master` |
| `cassie-data` | `master` |
| `LabRCSF` | `dev` |

Under `meta` these branches had no field to live in — they rode inside the URL string as a
`git clone` branch flag, which `meta` passed through to the shell. `default.xml` gives each
one a `revision` attribute, so the branch is data rather than a smuggled argument.

## Checks

```sh
python3 misc/scripts/check_docs.py              # every README claim, against default.xml and the remotes
python3 misc/scripts/check_docs.py --self-test  # plus: break each claim, require its check to fail
```

Seven checks: every path the README names exists (here, or in the repo it is attributed to),
the counts, the revision exceptions table, the explicit remote/revision invariant, that
`<default>` sets `sync-j` (without it repo fetches serially), that all 42 revisions exist on
their remotes, and that every project directory is gitignored. Each has a negative control.

The hooks are wired with [prek](https://github.com/j178/prek):

```sh
prek install                      # pre-commit and pre-push
prek run --all-files              # the offline subset, now
prek run --hook-stage pre-push --all-files
```

Commit stage runs the offline checks so it stays fast; the network claims and the negative
controls run at pre-push, before anything leaves the machine. `--local-only` prints what it
deferred and where that runs, because a silent skip reads exactly like a pass.
`CLAUDE.md` explains why documentation is held to this.

## Why not `meta`

[mateodelnorte/meta](https://github.com/mateodelnorte/meta) is unmaintained: last non-bot
commit to its default branch 2021-06-08, last npm release 2022-06-19. Two failures cost real
time before this conversion:

- `meta git clone` cannot find its own `meta-git` plugin when both are installed globally. It
  searches `node_modules/.bin` across cwd-ancestors plus npm's global prefix, never `PATH`.
- That failure, and a wrong-subcommand usage error, both **exit 0**. A silent skip reads
  exactly like a pass.

`repo` is maintained by 15 organisations over the last 24 months and is structurally load
bearing for AOSP, which is a sturdier bus factor than a single volunteer maintainer.
