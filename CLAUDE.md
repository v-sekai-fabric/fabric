# fabric-gyre-meta

Conventions for every project in this workspace. A `CLAUDE.md` in a parent directory loads for
the directories under it, so these hold in each repository `.meta` names without being copied
into any of them. A repository's own `CLAUDE.md` says what that repository is; this says how
work is done across all of them.

## The manifest

- `.meta` MUST state every value it depends on, including the ones that are obvious and the
  ones a tool would default for you. Today that is the branch: `--branch main <url>`, never a
  bare `<url>`.

A value left out is not absent, it is decided somewhere else. An entry with no branch clones
whatever the remote's HEAD happens to be, which the manifest does not record and the remote can
change on its own, so two checkouts made a month apart can differ with nothing here to compare.

Writing the obvious ones is the whole point. If only the unusual entries carry a branch, a
missing one means "the default, probably" and a present one means "look closer", and neither is
checkable. Two of the twenty-eight are already not what a reader would guess —
`fabric-godot-core` tracks `gyre` while its own default is `master`, and `lean-http3-queue`
defaults to `master` unlike every other `lean-*`. Stating all of them makes those two ordinary
lines rather than discoveries, and makes the next one visible in a diff.

## Commits

- Commit style: sentence case. Do not use a `type(scope):` prefix.
- Split a branch by concern, not by the order the work happened in. A commit is one idea and
  the whole of it: if a later commit fixes what an earlier one broke, they were one commit.
- Every commit MUST pass CI on its own, not only the last one. This decides some splits for
  you rather than leaving them to taste — a constant and the CI numbers derived from it cannot
  be separated, because neither half passes alone.

A branch split the way the work happened reads as a diary and reviews as one. The reader cannot
tell which commit is the idea and which is the repair, and bisect lands on commits that never
worked.

## Pull requests

- Open a pull request as a **draft** while anything about it is still in flight: a commit not
  pushed, a check not run, a number not yet checked.
- Mark it **ready for review** only when the branch is complete and its checks are green. Ready
  means ready to merge, and nothing else says so.
- A draft cannot be merged by accident, which is the whole point. Ready is a claim, so do not
  make it early and then keep pushing.

The state is the signal because nothing else is. A branch that looks finished and a branch that
is finished are the same branch to a reader, and a pull request whose commits are still arriving
will be merged without them — the merge takes what is there at that moment, not what the author
meant to include. Two commits in this workspace have already been lost that way: a proof merged
without the theorem it was written for, and a rewrite merged before it was rewritten. Neither
review could have caught it, because in both cases what was on screen was correct and what was
missing had not been pushed yet.

After a merge, check that the commits reached the target branch rather than that they were
pushed. `git log origin/main..<branch>` should be empty. `gh pr view --json commits` says what
the merge actually took, and it is the number to trust.

## Citation

- Every repository MUST carry a `CITATION.cff`, and its `references:` MUST name what the
  repository is built on: the designs it implements, the code it clones or vendors, and the
  repositories its constants are read from.
- Add the reference in the same commit that adds the dependency. A `CITATION.cff` written once
  and never touched again is a worse claim than none, because it reads as current.

Fourteen repositories here already have one and the rest do not, which makes the file look like a
habit of the `lean-*` hexagons rather than a rule. It is a rule, and the reason is what the
manifest's reason is: a value left out is not absent, it is recorded somewhere else. Provenance
stated only in prose is stated once, in whichever paragraph happened to need it, and a reader
asking "what is this made of" has to read the whole `README.md` and trust that nothing was
dropped. `fabric-physics-service` is the case that makes it plain — a clone of one repository,
vendoring a second and a third, implementing somebody else's published design, against numbers
proved in four Lean hexagons. None of that is visible in a dependency file, because there is no
dependency file that could hold a journal article.

## Where a thing is built and run

- Build and test **locally** by default. Reach for CI when the work overflows what this machine
  has — cores, wall clock, memory, disk, or the platforms it is not — and then let the cloud
  scale it out.
- Do NOT push a branch so that CI will compile it for you when the machine in front of you can.
  CI is the overflow, not the first attempt.
- Cap a long compile so the machine stays usable. `-j4` for a Godot build here, not `-j16`: the
  desk is also what the headset is plugged into and what a test client runs on.

Local is cheaper for a reason that has nothing to do with who pays for the runner. A local build
is **incremental** and a CI build is always cold. The Godot editor build in `fabric-godot-core`
is the case that shows it: an interrupted run left 2389 objects and a 19 MB `.sconsign5.dblite`,
so resuming cost minutes where CI would have started from nothing on every push. The second run
of anything is where local wins, and there is always a second run.

The feedback loop is the other half. A failure on this machine is a file and a line, now, with
the tree still in the state that produced it. The same failure in CI is a log to download, a
tree you cannot poke at, and a queue between every attempt — so a two-line fix costs a
round-trip instead of a rebuild.

And some things simply cannot go to CI. `fabric-wt-harness` drives the transport against a
Godot server on loopback, and `bench_players` measures a pinned core; a shared runner whose
neighbour is busy is not a core worth recording. That is why `bench_players` reports the budget
and only asserts it under `--gate`.

CI earns its keep where the machine runs out: the platforms this desk is not (Linux, macOS,
Android, web), the matrix that would take all afternoon serially, and the check that the branch
builds somewhere other than where it was written. `fabric-godot-core`'s `runner.yml` triggers on
any push to any branch, so that is available the moment it is wanted — after the local run, not
instead of it.

## Comments

- Match the comment density of FoundationDB, which is 12 to 14 percent of non-blank lines in
  `fdbserver`, `fdbclient` and `flow` at 7.3. Comment why the code does a thing, not what it
  does.

Most of this workspace is above that today. It comes down as files are touched, not in a sweep:
a commit that only reflows comments costs a review and proves nothing.

## How to deploy Godot Engine

- `scons production=yes precision=double debug_symbols=yes accesskit=yes`