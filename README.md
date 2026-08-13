# fabric

A [meta](https://github.com/mateodelnorte/meta) repo that groups the gyre
dependencies, so one command checks them all out and one command runs git
across all of them.

## Setup

Requires Node.js.

```sh
npm i -g meta
git clone https://github.com/v-sekai-multiplayer-fabric/fabric.git
cd fabric
meta git update                       # clone every project named in .meta
```

`meta git update` clones what is missing and leaves what is already there
alone, so it is also the way to pick up a project added to `.meta` later.

## The name

RFD 0111 names a git repository by its type first and drops the `fabric-`
prefix, which the organisation name already carries. That leaves the bare
word for the one repository that holds the manifest naming all the others,
so `fabric-gyre-meta`, then `fabric-service-meta`, is now `fabric`.

GitHub redirects both old names, so an existing clone keeps working. It also
keeps pointing at a name nothing here writes down, which is worth correcting
once rather than discovering later:

```sh
git remote set-url origin https://github.com/v-sekai-multiplayer-fabric/fabric.git
```
