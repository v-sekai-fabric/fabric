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

### Driving Godot locally

`vsekai-godot-mcp` is the local harness for anything Godot, and it is available here rather
than being something to build each time. Vendor it into a project as
`addons/vsekai_godot_mcp` from the repository's `addon-root` branch — Godot only scans
`res://addons/*/plugin.cfg`, so the whole repository subtreed puts it one level too deep and
the editor never finds it.

Both halves run at once, on purpose:

- the **editor plugin** on `127.0.0.1:8788` — the scene as edited, `play_main`, `stop`
- **`MCPRuntime`**, autoloaded into the running game, on `8789` — the scene as it actually is

Two ports because pressing play in an open editor is the ordinary case. When they shared 8788
the game lost the bind, printed `listen failed`, and a client went on questioning the editor
while believing it had reached the game — wrong answers rather than an error. `--mcp-port=` or
`GODOT_MCP_PORT` moves the runtime one.

**Ask the running game, not the editor, when the question is what arrived.** A node's real
transform is the difference between "the packet decoded" and "the object is where the service
put it", and nothing above the socket can tell you the second. The editor answers what the
scene was authored as, which is a different question and often the wrong one.

`claude mcp add --scope project --transport http godot http://127.0.0.1:8788/mcp` registers it,
and `.mcp.json` here already carries that entry.

Two things it will not do. `screenshot` captures the **editor viewport**, not the running game's
window, so it is evidence about the editor and nothing else. And driving the runtime bridge hard
has killed it mid-session — the editor's survived, the game's stopped answering — so a bridge
that goes quiet is a restart rather than a finding about the code under test.

## Checks

- A check MUST **fail the build**. A check that prints and returns zero is not a check, it is
  a log line, and nobody reads the log of a build that passed.
- Assert the **defining property**, not a consequence of it. Ask what would still be true if
  the thing were replaced by something wrong, and test whatever answers no.
- A gate MUST be shown to fail. Break the thing on purpose, watch the build go red, put it
  back. A gate never seen failing is a gate nobody has evidence works.
- Assert the property **where it is consumed**, not only where it is defined. A dependency's
  own tests do not run in your build.
- When the thing under test changes, the gate changes with it. A gate carried across a
  replacement becomes a test that only passes for what was removed.

All five of these were learned in one day, from one bug, and every one of them was already
nominally covered by something that passed.

`Shared.hilbert3D` was not a Hilbert curve. Walking the codes in order, 87.5% of consecutive
pairs were not adjacent cells -- worse locality than the Morton it was chosen over, at five
times the cost. It survived because everything being checked passed: it was a clean bijection,
it round-tripped, `hilbert_of_aabb` carried a `CRASH_COND` round-trip witness that fired on
every call and never once failed, and the docstring cited a paper. None of that distinguishes a
Hilbert curve from any other bijection. The defining property was asserted nowhere, so it was
wrong in five copies at once and in two languages.

**The consequence is not the property.** A round trip closing proves the pair are inverses; it
says nothing about which curve they are. A bijection proves no collisions; it says nothing about
locality. Both are worth asserting and neither is the thing.

`PredictiveBVH::insert` passed a space-filling code of `0u` for every node. The tree's whole
design is to radix-sort by that code, so it sorted a constant and fell back to insertion order.
It returned correct results throughout, which is why it went unnoticed -- the defect was in
ordering quality, and nothing asserted the codes were ever distinct.

**A check that reports is worse than no check**, because it reads as coverage. `CodeGen.lean`
verified its forward and inverse round-tripped at build time. When the forward moved upstream
and the inverse did not, it found the mismatch, printed `HILBERT INVERSE: 7 FAILURES`, and
exited zero. The build was green with a broken pair in it. It now throws.

**Where the check runs is part of the check.** `lean-shared-core` gates its curve correctly and
that gate did its job -- and it runs nowhere near the failure it needed to catch, because
`lake-manifest.json` pins by rev. An upstream fix merged, the pin did not move, and the
consumer sat on the old code with nothing to notice. Assert the contract against whatever is
actually pinned; `PredictiveBvh.core.CurveContract` is the pattern.

**Verify the gate by breaking the thing.** Every gate written that day was confirmed by staling
the manifest, rebuilding, and watching it go red before being put back. Two readings during that
were confidently wrong from stale `.olean` files pointing in opposite directions, so force the
rebuild before believing any result -- including a result you like.

And when the curve was replaced, its contiguity gate had to be deleted rather than kept: Morton
fails it by design. A gate that outlives what it was written for is a test that passes only for
the thing you removed, which is where this started.

## Taking inventory

A workspace of twenty-eight repositories loses work on disk, not in review. Before changing
lanes, after any long task, and before saying what is left to do, take stock — from the
repositories, never from memory.

```sh
cd P:/fabric-gyre-meta
for d in */; do d=${d%/}; [ -d "$d/.git" ] || continue; cd "$d"
  u=$(git status --porcelain | grep -c '^??')
  m=$(git status --porcelain | grep -vc '^??')
  b=$(git branch --show-current)
  up=$(git rev-parse --verify -q "origin/$b" >/dev/null 2>&1 || echo NO-UPSTREAM)
  ah=$(git rev-list --count "origin/$b..HEAD" 2>/dev/null || echo ?)
  [ "$u$m$ah" != "000" -o -n "$up" ] && printf '%-28s %-30s untracked=%-4s modified=%-4s ahead=%-4s %s\n' \
    "$d" "$b" "$u" "$m" "$ah" "$up"
  cd ..
done
```

Then separate the real from the noise, because most of what it prints is noise. A Windows
checkout of a repository with shell scripts in it reports a hundred files `modified` that are
`mode change 100755 => 100644` and zero insertions. `git diff --stat` tells them apart in one
line, and an inventory that does not do that buries three real items under three hundred.

**Rank by risk of loss, not by value.** In order:

1. **Untracked files.** They survive nothing — not a stash, not a branch switch, not a `clean`.
   An untracked file is the only state here with no copy anywhere.
2. **Committed but unpushed**, and branches with no upstream.
3. **Pushed but no pull request**, then open pull requests, then stacks waiting to merge.
4. Everything else, by value.

A thing that exists in one place is worth more attention than a thing that is merely important.

This is written down because it was learned twice in one day. Three files implementing an
interactor sat untracked for hours across two status reports that both claimed to say what was
outstanding. And a pull request was opened describing a test harness whose file had never been
pushed — the description was accurate about the work and wrong about the repository, which is
the failure a reviewer cannot catch.

## Ordering work: PERT and the critical path

Taking inventory says what is open. To decide what to do next, draw the dependency graph and
estimate each task three ways. Do NOT invent a value score and rank by it — a made-up number
divided by another made-up number produces arithmetic that looks objective and only launders
whatever order was already preferred.

**Estimate each task three ways**, because a single number hides how little is known:

    te = (o + 4m + p) / 6

optimistic, most likely, pessimistic. The spread is the useful part. A task estimated
`1h / 2h / 12h` is not a two-hour task, it is an unknown wearing one, and the honest response is
to shrink the pessimistic case first — usually by running the smallest thing that would tell you
which end of the range is real.

### Take the three points from git, not from a feeling

Guessed estimates are the same failure as a made-up score, one step further in. Derive them from
what this org has actually done: group each repository's commits into sessions, where a gap of
more than four hours means somebody went away rather than worked slowly, and take percentiles of
session length by size.

    git -C <repo> log --since=6.months --pretty=%ct --numstat

**Measured across every checkout here, 475 sessions over six months:**

| session size | n | o (p10) | m (p50) | p (p90) | te |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2–4 commits | 220 | 0.02 h | 1.05 h | 3.91 h | **1.35 h** |
| 5–9 commits | 66 | 1.14 h | 3.86 h | 8.61 h | **4.20 h** |
| 10–24 commits | 102 | 1.95 h | 8.14 h | 16.31 h | **8.47 h** |
| 25+ commits | 87 | 8.90 h | 14.68 h | 21.10 h | **14.79 h** |

Size a task by the commits it will take — which is a guess about *shape*, and a far easier one
than a guess about hours — and read the row.

Re-derive the table rather than trusting these numbers forever; they are this org, this year,
this way of working.

**Check that the evidence measures the thing.** Merged-PR cycle time was tried first and is
useless here: across 387 merged pull requests the median is **under six minutes**, because a
pull request is opened and merged by the same person in one motion. That measures how long a
review sits, and in a solo workflow the answer is zero. Commit cadence measures work; PR age
measures process. Picking the wrong one produces confident numbers about nothing.

**Expect the correction to be large and in one direction.** Estimates made by feel on this
workspace ran two to four times optimistic against the table — a "half hour" probe sits in the
2–4 commit row at `te` 1.35 h with a p90 near four hours. Optimism is the normal direction, so a
sanity check that only ever confirms the guess is not being run properly.

**Then find the critical path.** The longest chain of dependent tasks is the earliest the whole
thing can finish. Only two facts matter after that:

- Work **on** the path: every hour saved is an hour off the finish.
- Work **off** it has slack: it can be done late, in parallel, or by somebody else, and finishing
  it early buys nothing at all.

That is the whole ranking, and it comes from the graph rather than from a preference. A task can
be genuinely important and have slack — say so and let it wait, rather than promoting it because
it feels urgent.

**Dependencies must be checked, not assumed.** The cheapest thing an inventory does is delete an
edge. Comparing physics topologies against a counting sink turned out to need no transport at
all, so an entire transport lane left the critical path — visible only by reading what the
benchmark actually calls, not by thinking about what a networking comparison ought to need.

**Where the graph forks on an unknown, the probe that resolves it is on the critical path.** If
one branch of the plan depends on a property nothing has measured — determinism, a rate, a
limit — the measurement precedes both branches, because until it lands every downstream estimate
has a pessimistic case that includes "and then throw it away".

## Comments

- Match the comment density of FoundationDB, which is 12 to 14 percent of non-blank lines in
  `fdbserver`, `fdbclient` and `flow` at 7.3. Comment why the code does a thing, not what it
  does.

Most of this workspace is above that today. It comes down as files are touched, not in a sweep:
a commit that only reflows comments costs a review and proves nothing.

## How to deploy Godot Engine

- `scons production=yes precision=double debug_symbols=yes accesskit=yes`