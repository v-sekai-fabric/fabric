# fabric

A [repo](https://gerrit.googlesource.com/git-repo) manifest: 2 projects across 2 GitHub orgs, plus the checks and the ledger that say whether the work is moving.

```sh
repo init -u https://github.com/v-sekai-multiplayer-fabric/fabric
repo sync -j8
```

## Why one

This carried forty-six projects across five GitHub orgs, laid out as a hexagon, with sixteen gates holding its prose to it. All of it was true and none of it delivered: across 479.8 booked hours since 2020, **42.70 reached the mesh**, and the oracle that makes the mesh has never been run end to end.

So the manifest was declared bankrupt rather than trimmed. The other 45 repositories still exist on their remotes and nothing was deleted — they are not checked out, because a checkout claims something is being worked on and 45 of them were not. One comes back when the one below needs it.

## Revisions

Every project states its own `remote` and `revision`, so one that omits either fails at `repo init` rather than inheriting a default. Most projects track `main`, and The zero that do not would be listed here.

## The ledger

`ledger/spent.beancount` books hours from git history, allocated so concurrent sessions in different checkouts are never counted twice. `ledger/planned.beancount` holds the plan in a different commodity, so beancount itself refuses to net an estimate against an hour that was spent.

```sh
python3 misc/scripts/ledger.py report --since 90   # SPENT, by lane
python3 misc/scripts/ledger.py path                # HYPOTHETICAL, the critical path
```

The budget is one week and the scope slides, because the same five tasks cost 13.81 h at the median and 51.24 h at the 99th percentile and no single scope fits both.

## Checks

```sh
python3 misc/scripts/check_docs.py             # all of them
python3 misc/scripts/check_docs.py --self-test # each must fail on broken input
```

Every claim above is derived from `default.xml` or the ledger and gated. `CLAUDE.md` says why.
