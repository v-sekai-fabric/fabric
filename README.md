# fabric

A [meta](https://github.com/mateodelnorte/meta) repo that groups the gyre
dependencies, so one command checks them all out and one command runs git
across all of them.

## Setup

```sh
npm i -g meta # Requires Node.js.
git clone https://github.com/v-sekai-multiplayer-fabric/fabric.git
cd fabric
meta git update                       # clone every project named in .meta
```
