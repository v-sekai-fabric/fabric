# fabric-gyre-meta

Conventions for every project in this workspace. A `CLAUDE.md` in a parent directory loads for
the directories under it, so these hold in each repository `.meta` names without being copied
into any of them. A repository's own `CLAUDE.md` says what that repository is; this says how
work is done across all of them.

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

## Comments

- Match the comment density of FoundationDB, which is 12 to 14 percent of non-blank lines in
  `fdbserver`, `fdbclient` and `flow` at 7.3. Comment why the code does a thing, not what it
  does.

Most of this workspace is above that today. It comes down as files are touched, not in a sweep:
a commit that only reflows comments costs a review and proves nothing.
