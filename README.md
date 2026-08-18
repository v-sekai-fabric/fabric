# fabric

A [repo](https://gerrit.googlesource.com/git-repo) manifest: 54 projects across 5 GitHub orgs.

```sh
repo init -u https://github.com/v-sekai-multiplayer-fabric/fabric && repo sync -j8
```

## The layout

`default.xml` gives each project a `path`, so the workspace is one hexagon and the numbered directories are its sides; that file's opening comment names all six. This repository is not among them — `repo init` clones it to `.repo/manifests` and reads the manifest from there, so edit it in that checkout. Every project states its own `remote` and `revision`, so one that omits either fails at `repo init` rather than inheriting a default. Every project tracks its repository's default branch. The zero that do not would be listed here, and the check that keeps this sentence true asks GitHub rather than the manifest.

## What this repository is not

It holds the manifest and nothing else. The conventions, the ledger that books the hours, the gates that decide whether these documents are true, and the logbook are all one project on the `0-` side: `infrastructure-logbook`, checked out at `0-infrastructure/logbook`. It is a project like any other, so `repo sync` brings it down with the rest and its gates read this file from `.repo/manifests` the way they read every other checkout.

They lived here until the two jobs were told apart. A manifest is read by a tool on every sync; a record is read by people and rewritten as the work moves, and keeping them in one repository meant every entry in the second was a commit against the first.
