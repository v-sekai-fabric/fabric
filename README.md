# fabric

A [repo](https://gerrit.googlesource.com/git-repo) manifest for the gyre dependencies: 46 projects across 5 GitHub orgs, from one command.

## Setup

```sh
brew install repo
mkdir fabric-ws && cd fabric-ws
repo init -u https://github.com/v-sekai-multiplayer-fabric/fabric
repo sync -j8
```

`default.xml` gives each project a `path`, so the workspace is one hexagon and the numbered
directories are its sides; that file's opening comment names all six. `repo sync` leaves detached HEADs, so `repo start <branch> <project>` before editing.

## Revisions

Every project states its own `remote` and `revision`, so one that omits either fails
at `repo init` rather than inheriting a default. Most projects track `main`. The six that do not:

| project | revision |
|---|---|
| `entities-godot` | `gyre` |
| `interactor-triangulation` | `legacy` |
| `datasource-flow` | `main-fabric` |
| `contract-http3-queue` | `master` |
| `cassie-data` | `master` |
| `LabRCSF` | `dev` |

## Checks

```sh
python3 misc/scripts/check_docs.py              # claims, against default.xml and the remotes
python3 misc/scripts/check_docs.py --self-test  # plus: break each claim, require its check to fail
prek run --all-files                            # the offline subset, wired as a hook
```

Sixteen checks, each with a negative control. `CLAUDE.md` says why.
