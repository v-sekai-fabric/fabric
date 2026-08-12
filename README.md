# fabric-gyre-meta

A [meta](https://github.com/mateodelnorte/meta) repo that groups the gyre
dependencies, so one command checks them all out and one command runs git
across all of them.

## Setup

Requires Node.js.

```sh
npm i -g meta
git clone https://github.com/v-sekai-multiplayer-fabric/fabric-gyre-meta.git
cd fabric-gyre-meta
meta git update                       # clone every project named in .meta
```

`meta git update` clones what is missing and leaves what is already there
alone, so it is also the way to pick up a project added to `.meta` later.

`fabric-godot-core`'s default branch is `master`, so its `.meta` entry carries a
`--branch gyre` prefix in front of the URL and a fresh checkout lands on `gyre`
with no manual step. A copy cloned before this is left alone, so it still has to
be moved with `git -C fabric-godot-core checkout gyre`.
