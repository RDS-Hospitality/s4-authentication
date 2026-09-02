#!/usr/bin/env bash
# render-reference.sh — regenerate reference/angular-amplify-v6/ from the ng-add templates.
#
# The templates under schematics/ng-add/files/ are what ships (curated-manifest.txt); the
# reference directory is the copy-paste-ready rendering docs/ADOPTION.md points adopters at.
# The two drifted apart (5 of 7 files by 0.3.1) because nothing regenerated the reference.
# This script is that step. `--check` diffs instead of writing and exits 1 on drift — the
# Success Criteria run it; a hand edit to the reference will fail it, which is the point.
#
# Placeholders are rendered with the same fixed values the README documents:
#   userPoolId/clientId/cognitoDomain -> __USER_POOL_ID__ etc. (deploy-time values)
#   providersLiteral -> 'google'   appTitle -> Sign in   postLoginRoute -> /
set -euo pipefail
PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$PKG/../.." && pwd)"
SRC="$PKG/schematics/ng-add/files/src/app"
DST="$REPO_ROOT/reference/angular-amplify-v6"
MODE="${1:-write}"

render() { # $1 = template path, prints rendered content
  sed -e "s|<%= userPoolId %>|__USER_POOL_ID__|g" \
      -e "s|<%= clientId %>|__USER_POOL_CLIENT_ID__|g" \
      -e "s|<%= cognitoDomain %>|__COGNITO_HOSTED_DOMAIN__|g" \
      -e "s|<%= providersLiteral %>|'google'|g" \
      -e "s|<%= appTitle %>|Sign in|g" \
      -e "s|<%= postLoginRoute %>|/|g" "$1"
}

status=0
while IFS= read -r -d '' tpl; do
  rel="${tpl#"$SRC"/}"; rel="${rel%.template}"
  out="$DST/$rel"
  if [[ "$MODE" == "--check" ]]; then
    if [[ ! -f "$out" ]]; then echo "DRIFT: missing $out"; status=1; continue; fi
    if ! diff -q <(render "$tpl") "$out" >/dev/null; then echo "DRIFT: $rel differs from its template"; status=1; fi
  else
    mkdir -p "$(dirname "$out")"
    render "$tpl" > "$out"
    echo "rendered $rel"
  fi
done < <(find "$SRC" -name '*.template' -print0 | sort -z)

if [[ "$MODE" == "--check" ]]; then
  # A reference file with no template is drift in the other direction.
  while IFS= read -r -d '' ref; do
    rel="${ref#"$DST"/}"
    [[ "$rel" == README.md || "$rel" == */.gitkeep || "$rel" == .gitkeep ]] && continue
    [[ -f "$SRC/$rel.template" ]] || { echo "DRIFT: $rel has no template"; status=1; }
  done < <(find "$DST" -type f -print0)
  [[ $status -eq 0 ]] && echo "reference matches templates"
fi
exit $status
