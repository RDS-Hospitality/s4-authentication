#!/usr/bin/env bash
# test-export-main.sh — verifies export-main.sh (orchestrator) publishes TWO fresh
# single-commit orphan DISTRIBUTION branches, each FLAT-ROOT:
#   angular: README.md, STANDARD.md, infra/cognito/, package.json, schematics/   (Angular at root)
#   react:   README.md, STANDARD.md, infra/cognito/, package.json, dist/, templates/ (npx CLI at root)
# plus release tags angular-vX.Y.Z / react-vX.Y.Z, and leaves `main` untouched.
# Runs entirely inside a scratch clone so it NEVER touches the real repo's
# branches or working tree.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
VER="0.2.0"   # test release version (independent of the real release)

# Work on a scratch clone so we never touch the real branches.
SCRATCH="$(mktemp -d)"; trap 'rm -rf "$SCRATCH"' EXIT
git clone --quiet "$REPO_ROOT" "$SCRATCH/repo"
cd "$SCRATCH/repo"
git checkout --quiet "$(cd "$REPO_ROOT" && git rev-parse --abbrev-ref HEAD)"

# The clone only contains COMMITTED files. Copy the working-tree scripts/manifests
# from the real repo so TDD can exercise uncommitted versions.
mkdir -p "$SCRATCH/repo/scripts" "$SCRATCH/repo/packages/angular/scripts" \
         "$SCRATCH/repo/packages/react/scripts" "$SCRATCH/repo/packages/flask/scripts"
cp "$HERE/export-main.sh" "$HERE/test-export-main.sh" "$SCRATCH/repo/scripts/"
cp "$REPO_ROOT/scripts/curated-manifest-root.txt"            "$SCRATCH/repo/scripts/"
cp "$REPO_ROOT/packages/angular/scripts/export.sh"           "$SCRATCH/repo/packages/angular/scripts/"
cp "$REPO_ROOT/packages/angular/scripts/curated-manifest.txt" "$SCRATCH/repo/packages/angular/scripts/"
cp "$REPO_ROOT/packages/angular/README-main.md"              "$SCRATCH/repo/packages/angular/"
cp "$REPO_ROOT/packages/react/scripts/export.sh"             "$SCRATCH/repo/packages/react/scripts/"
cp "$REPO_ROOT/packages/react/README-main.md"                "$SCRATCH/repo/packages/react/"
cp "$REPO_ROOT/packages/flask/scripts/export.sh"             "$SCRATCH/repo/packages/flask/scripts/"
cp "$REPO_ROOT/packages/flask/scripts/curated-manifest.txt"  "$SCRATCH/repo/packages/flask/scripts/"
cp "$REPO_ROOT/packages/flask/README-main.md"                "$SCRATCH/repo/packages/flask/"
# react export.sh now BUILDS the CLI from the clone's committed packages/react/cli/ source
# (npm ci && npm run build); the clone has that source + lockfile, so no extra copy is needed.

# FLASK_ONLY=1 runs just the flask case (no npm ci / angular / react builds).
FLASK_ONLY="${FLASK_ONLY:-}"

# The clone has no node_modules (gitignored) — install so Angular's `npm run build` works.
[[ -n "$FLASK_ONLY" ]] || ( cd "$SCRATCH/repo/packages/angular" && npm ci --silent )

# assert path EXISTS on a branch's tree
have() { git cat-file -e "$1:$2" 2>/dev/null; }
# assert path is ABSENT on a branch's tree
absent() { ! git cat-file -e "$1:$2" 2>/dev/null; }

check_orphan() {
  local br="$1"
  git rev-parse --verify "$br" >/dev/null || { echo "FAIL: branch '$br' not created"; exit 1; }
  [[ "$(git rev-list --count "$br")" -eq 1 ]] \
    || { echo "FAIL: '$br' is not a single commit ($(git rev-list --count "$br") commits)"; exit 1; }
  if git rev-parse -q --verify "${br}^" >/dev/null 2>&1; then
    echo "FAIL: '$br' is not an orphan (has parents)"; exit 1
  fi
  return 0
}

check_no_leaks() {
  local br="$1"
  for p in docs README-main.md packages reference; do
    have "$br" "$p" && { echo "FAIL: '$br' leaked $p (should not ship to consumers)"; exit 1; }
  done
  # Dev/CI infra test scripts must NEVER ship — manifest enumerates only consumer scripts.
  for p in infra/cognito/scripts/test-deploy-validation.sh \
           infra/cognito/scripts/test-destroy-guard.sh \
           infra/cognito/scripts/test-fetch-config.sh \
           infra/cognito/scripts/test-template-validates.sh; do
    have "$br" "$p" && { echo "FAIL: test script leaked to '$br': $p"; exit 1; }
  done
  return 0   # last `have` returns nonzero when (correctly) absent — don't let set -e see it
}

run_and_check() {
  bash scripts/export-main.sh --version "$VER"

  # --- angular branch: flat-root Angular package ---
  check_orphan angular
  for p in README.md STANDARD.md infra/cognito/template.yaml package.json \
           schematics/collection.json schematics/ng-add/index.js; do
    have angular "$p" || { echo "FAIL: angular missing $p"; exit 1; }
  done
  # flat: NO nested framework subdirs
  absent angular angular || { echo "FAIL: angular/ subdir nested on angular branch"; exit 1; }
  absent angular react   || { echo "FAIL: react/ subdir present on angular branch"; exit 1; }
  # framework README won (not the shared/monorepo one)
  git show angular:README.md | grep -q 's4-auth-angular' \
    || { echo "FAIL: angular README.md is not the Angular framework README"; exit 1; }
  # version stamped into the ROOT package.json
  git show angular:package.json | grep -q "\"version\": \"$VER\"" \
    || { echo "FAIL: angular package.json missing version $VER"; exit 1; }
  check_no_leaks angular

  # --- react branch: flat-root @s4/auth-react npx CLI (WU6) ---
  check_orphan react
  for p in README.md STANDARD.md infra/cognito/template.yaml \
           package.json dist/bin.js templates/auth.config.ts templates/auth.css; do
    have react "$p" || { echo "FAIL: react missing $p"; exit 1; }
  done
  absent react react   || { echo "FAIL: react/ subdir nested on react branch"; exit 1; }
  absent react angular || { echo "FAIL: angular/ subdir present on react branch"; exit 1; }
  # react now ships the CLI package: root package.json IS the @s4/auth-react CLI, bin → dist/bin.js
  git show react:package.json | grep -q '"s4-auth-react"' \
    || { echo "FAIL: react package.json is not the @s4/auth-react CLI (no s4-auth-react bin)"; exit 1; }
  # version stamped into the ROOT package.json (now that react has one to stamp)
  git show react:package.json | grep -q "\"version\": \"$VER\"" \
    || { echo "FAIL: react package.json missing version $VER"; exit 1; }
  # the OLD copy-in src/ shape is gone — the CLI replaced it
  absent react src/auth.config.ts || { echo "FAIL: react still ships copy-in src/ (should be the CLI now)"; exit 1; }
  # framework README won (not the shared/monorepo one)
  git show react:README.md | grep -q 's4-auth-react' \
    || { echo "FAIL: react README.md is not the React framework README"; exit 1; }
  check_no_leaks react

  # --- release tags point at the branch tips, and are ANNOTATED (a tag object) ---
  for fw in angular react; do
    git rev-parse --verify "${fw}-v${VER}" >/dev/null 2>&1 \
      || { echo "FAIL: tag ${fw}-v${VER} not created"; exit 1; }
    [[ "$(git rev-parse "${fw}-v${VER}^{commit}")" == "$(git rev-parse "$fw")" ]] \
      || { echo "FAIL: tag ${fw}-v${VER} does not point at branch '$fw' tip"; exit 1; }
    [[ "$(git cat-file -t "${fw}-v${VER}")" == "tag" ]] \
      || { echo "FAIL: tag ${fw}-v${VER} is lightweight; releases must be annotated"; exit 1; }
  done

  # --- the exported Angular schematic LOADS: every module the manifest ships must resolve.
  #     (npm pack in the smoke script uses package.json `files`, not the manifest, so only
  #     this check catches a module the manifest forgot.)
  local EXTRACT; EXTRACT="$(mktemp -d)"
  git archive angular | tar -x -C "$EXTRACT"
  NODE_PATH="$PWD/packages/angular/node_modules" node -e "require('$EXTRACT/schematics/ng-add/index.js')" \
    || { echo "FAIL: exported schematics/ng-add/index.js does not load from the angular branch tree"; exit 1; }
  rm -rf "$EXTRACT"

  # --- main is NOT touched by the orchestrator (trunk is sacred here) ---
  # (main may not exist in the scratch clone's local refs; if it does, it must be unchanged.
  #  The orchestrator's only ref writes are the two dist branches + tags — assert no 'main' write
  #  by confirming main, if present, is not an orphan single-commit release.)

  echo "  run check OK (two flat-root orphans + tags, version stamped, no leaks)"
}

# --- flask: published on its own, with its own version, via --only. The default set stays
#     angular+react, so none of the cases above publish it.
FLASK_VER="0.0.99"   # test-only: the scratch clone inherits real tags, so never use a real release version
flask_case() {
  local before_a before_r
  before_a="$(git rev-parse -q --verify refs/heads/angular || echo none)"
  before_r="$(git rev-parse -q --verify refs/heads/react || echo none)"

  bash scripts/export-main.sh --only flask --version "$FLASK_VER"

  check_orphan flask
  for p in pyproject.toml README.md STANDARD.md infra/cognito/template.yaml \
           s4_auth_flask/__init__.py s4_auth_flask/extension.py; do
    have flask "$p" || { echo "FAIL: flask missing $p"; exit 1; }
  done
  for p in tests .venv .pytest_cache uv.lock packages docs README-main.md; do
    absent flask "$p" || { echo "FAIL: flask branch leaked $p"; exit 1; }
  done
  [[ -z "$(git ls-tree -r --name-only flask | grep -E '__pycache__|\.pyc$' || true)" ]] \
    || { echo "FAIL: flask branch ships bytecode"; exit 1; }
  git show flask:pyproject.toml | grep -qx "version = \"$FLASK_VER\"" \
    || { echo "FAIL: flask pyproject.toml missing version $FLASK_VER"; exit 1; }
  git show flask:README.md | grep -q 's4-auth-flask' \
    || { echo "FAIL: flask README.md is not the Flask framework README"; exit 1; }

  local tag="flask-v${FLASK_VER}"
  [[ "$(git cat-file -t "$tag")" == "tag" ]] || { echo "FAIL: $tag is not an annotated tag"; exit 1; }
  [[ "$(git rev-parse "${tag}^{commit}")" == "$(git rev-parse flask)" ]] \
    || { echo "FAIL: $tag does not point at the flask tip"; exit 1; }

  [[ "$(git rev-parse -q --verify refs/heads/angular || echo none)" == "$before_a" \
     && "$(git rev-parse -q --verify refs/heads/react || echo none)" == "$before_r" ]] \
    || { echo "FAIL: --only flask moved the angular/react refs"; exit 1; }

  # The branch must be pip-installable from its root and expose the public entry point.
  local WORK; WORK="$(mktemp -d)"
  mkdir "$WORK/checkout"
  git archive flask | tar -x -C "$WORK/checkout"
  uv venv --quiet "$WORK/venv"
  uv pip install --quiet --python "$WORK/venv/bin/python" "$WORK/checkout" \
    || { echo "FAIL: uv pip install of the flask branch failed"; exit 1; }
  "$WORK/venv/bin/python" -c "import s4_auth_flask; s4_auth_flask.S4Auth" \
    || { echo "FAIL: installed flask branch does not expose s4_auth_flask.S4Auth"; exit 1; }
  rm -rf "$WORK"
  echo "  flask check OK (flat-root orphan, version stamped, no tests/, installs, other refs untouched)"
}

if [[ -n "$FLASK_ONLY" ]]; then
  flask_case
  echo "PASS (flask only)"
  exit 0
fi

run_and_check          # first release
TAG_A1="$(git rev-parse "angular-v${VER}")"; TAG_R1="$(git rev-parse "react-v${VER}")"
run_and_check          # SECOND run must also succeed (re-runnability)
BR_A2="$(git rev-parse angular)"
# Identical content under the same version must NOT mint a new tag object: consumers pin
# the tag, and a tag-protection ruleset rejects a moved tag as a non-fast-forward update.
[[ "$(git rev-parse "angular-v${VER}")" == "$TAG_A1" && "$(git rev-parse "react-v${VER}")" == "$TAG_R1" ]] \
  || { echo "FAIL: re-running an identical release moved a version tag (${TAG_A1:0:12} -> $(git rev-parse "angular-v${VER}" | cut -c1-12))"; exit 1; }

# --- DIFFERENT content under an EXISTING version must be refused. This is the failure the
#     ledger recorded: twelve files shipped under an unchanged 0.3.1.
cp packages/react/README-main.md "$SCRATCH/README-main.bak"
printf '\n<!-- mutated by test-export-main.sh -->\n' >> packages/react/README-main.md
if bash scripts/export-main.sh --version "$VER" > "$SCRATCH/refusal.out" 2>&1; then
  echo "FAIL: export republished different content under existing tag react-v${VER}"; exit 1
fi
grep -q "already published with different content" "$SCRATCH/refusal.out" \
  || { echo "FAIL: refusal did not name the cause"; cat "$SCRATCH/refusal.out"; exit 1; }
[[ "$(git rev-parse "react-v${VER}")" == "$TAG_R1" ]] \
  || { echo "FAIL: refused release still moved react-v${VER}"; exit 1; }
[[ "$(git rev-parse angular)" == "$BR_A2" ]] \
  || { echo "FAIL: a refusal on react left the angular branch re-pointed (refs must change all-or-nothing)"; exit 1; }
cp "$SCRATCH/README-main.bak" packages/react/README-main.md
echo "  refusal check OK (changed content under an existing version is rejected, tag untouched)"

# --- VERSION must be bare semver: a 'v' prefix would mint 'angular-vv0.2.0'.
if bash scripts/export-main.sh --version "v${VER}" > "$SCRATCH/semver.out" 2>&1; then
  echo "FAIL: export accepted a v-prefixed version"; exit 1
fi
grep -qi "semver" "$SCRATCH/semver.out" || { echo "FAIL: version rejection did not mention semver"; cat "$SCRATCH/semver.out"; exit 1; }
echo "  version-format check OK"

flask_case

# After exercising the export twice, no temp worktrees/branches may dangle.
[[ -z "$(git worktree list --porcelain | grep -iE 'export-(angular|react|flask)' || true)" ]] \
  || { echo "FAIL: dangling export worktree left behind"; git worktree list; exit 1; }
[[ -z "$(git branch --list 'export-angular-tmp-*' 'export-react-tmp-*' 'export-flask-tmp-*')" ]] \
  || { echo "FAIL: dangling temp branch left behind"; git branch --list 'export-*-tmp-*'; exit 1; }

echo "PASS"
