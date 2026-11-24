# Releasing

How to publish a release of an s4-auth framework adapter, and what to do when one is wrong.
This is a contributor standard: follow it for every release.

## Versions and tags

Each framework versions on its own: `angular`, `react` and `flask`. A version is semver
(`X.Y.Z`, no `v` prefix; `export-main.sh` rejects `v0.4.0`). Releasing one framework does not
release the others.

A release produces two refs on the remote:

- the distribution branch `<fw>` (a single-commit orphan with the framework at its root, rebuilt on
  every release), and
- an annotated tag `<fw>-vX.Y.Z` pointing at that commit.

`main` is the source trunk and is never published from directly.

## Who may release

Anyone with push access to the repository, from a clean checkout of `main` whose changes are
already merged. The export copies files from your working tree, so uncommitted edits would be
shipped under the tag. Do not run it from a branch named after a distribution branch; the script
refuses.

## Steps

Replace `<fw>` with `angular`, `react` or `flask` and `X.Y.Z` with the new version.

1. Add the entry to `CHANGELOG.md` under the version heading, and commit it to `main`.
2. Run the pre-push safety check (secrets, large files, unsafe patterns) on what you are about to push.
3. Run the export tests: `bash scripts/test-export-main.sh`. To exercise only the flask case
   (skips the npm builds), run `FLASK_ONLY=1 bash scripts/test-export-main.sh`.
4. Build the release locally: `bash scripts/export-main.sh --only <fw> --version X.Y.Z`.
   This moves the local branch `<fw>` and creates the local annotated tag `<fw>-vX.Y.Z`.
   Without `--only` it builds `angular` and `react` (not `flask`). The PowerShell twin is
   `scripts/export-main.ps1 -Only <fw> -Version X.Y.Z`.
5. Push the branch: `git push --force-with-lease origin <fw>`. The branch is rebuilt as a new
   orphan each release, so this is a forced update by design; `--force-with-lease` keeps it from
   overwriting a push you have not seen.
6. Push the tag: `git push origin <fw>-vX.Y.Z`.
7. Verify with `git ls-remote --tags origin` that the new tag is there and that every older tag
   still resolves to the commit it pointed at before.

What the script guarantees:

- It writes refs only after every requested framework has built cleanly; a refusal leaves no refs changed.
- Re-running with the same version and identical content re-uses the existing tag and does not mint a new one.
- Running with the same version and different content is refused ("already published with
  different content"). Bump the version.
- Concurrent runs are serialised with a lock.

## Tags are immutable

The repository has a ruleset, `protect-release-tags`, on `refs/tags/**` with the rules `deletion`,
`update` and `non_fast_forward` and no bypass actors. Nobody, including admins, can delete or
move a tag.

A bad release is therefore fixed forward: publish a new patch version with the fix, and add a
line to the changelog marking the bad version (for example "0.4.1 supersedes 0.4.0, which
shipped X"). Never try to re-tag.

## Never delete and recreate the repository

Deleting and recreating the repository orphans every commit that consumers have pinned. In 2026-07
a consumer's lockfile pinned a commit that no longer existed after a recreate: `npm ci` failed
because it installs exactly the locked commit, while `npm install` re-resolved and appeared to
work. If a repository-level change is needed (rename, transfer), use GitHub's own rename/transfer,
which keeps history and redirects.

## Consumer guidance

- Pin a tag, never a branch. The branch tip changes on every release and is rebuilt as an orphan.
- npm consumers install `github:RDS-Hospitality/s4-authentication#<fw>-vX.Y.Z` (or the
  `git+https://...#<fw>-vX.Y.Z` form shown in the README). After changing the pinned tag,
  re-resolve the lockfile with `npm install` and commit it.
- pip consumers pin `@<fw>-vX.Y.Z`, as in
  `pip install "git+https://github.com/RDS-Hospitality/s4-authentication.git@flask-vX.Y.Z"`.
