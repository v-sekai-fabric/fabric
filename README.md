# fabric-gyre-meta

A [meta](https://github.com/mateodelnorte/meta) repo that groups the gyre
dependencies, so one command checks them all out and one command runs git
across all of them. Nothing is vendored and nothing is a submodule — this
repo holds only the `.meta` manifest, and each child keeps its own history
in its own remote.

## Projects

| Project | Branch to work on | Purpose |
|---|---|---|
| [fabric-godot-core](https://github.com/v-sekai-multiplayer-fabric/fabric-godot-core) | [`gyre`](https://github.com/v-sekai-multiplayer-fabric/fabric-godot-core/tree/gyre) | The engine fork. `gyre` is the ref everything downstream pins. |
| [godot-images](https://github.com/v-sekai-multiplayer-fabric/godot-images) | `main` | Builds the engine — editor and `template_release` — and publishes to GHCR. Pinned to `fabric-godot-core` @ `gyre`. |
| [fabric-store-domain](https://github.com/v-sekai-multiplayer-fabric/fabric-store-domain) | `main` | The store domain. |

`fabric-godot-core`'s default branch is `master`, so a fresh clone lands
there and has to be moved to `gyre` — the checkout step below does that.

## Setup

Requires Node.js.

```sh
npm i -g meta
git clone https://github.com/v-sekai-multiplayer-fabric/fabric-gyre-meta.git
cd fabric-gyre-meta
meta git update                       # clone every project named in .meta
git -C fabric-godot-core checkout gyre
```

`meta git update` clones what is missing and leaves what is already there
alone, so it is also the way to pick up a project added to `.meta` later.

## Everyday use

`meta git <cmd>` runs the git command in this repo and in every project:

```sh
meta git status
meta git pull
meta git checkout -b my-feature       # same branch name across all three
```

`meta exec` runs anything else:

```sh
meta exec "git log --oneline -5"
meta exec "just --list" --include-only godot-images
```

Both print output grouped per project and keep going when one project
fails, so a command that does not apply everywhere is not fatal.

## Adding a project

Add it to `.meta` and add its directory to `.gitignore`:

```sh
meta project import <name> https://github.com/v-sekai-multiplayer-fabric/<name>.git
```

`meta project import` edits `.meta` for you; the `.gitignore` line is
manual. Commit both — a child directory committed into this repo would
turn the checkout into a copy that drifts.
