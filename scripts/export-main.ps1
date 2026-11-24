# export-main.ps1 — publish the per-framework distribution branches (angular, react, flask).
# Thin wrapper: delegates to export-main.sh (single source of git logic).
#
# Layout produced:
#   shared root: README.md, STANDARD.md, infra/cognito/
#   angular/:    package.json, schematics/, README.md   (staged by packages/angular/scripts/export.sh)
#   react/:      README.md, src/                        (staged by packages/react/scripts/export.sh)
#
# Usage: export-main.ps1 [-Version X.Y.Z] [-Only angular|react|flask]
#
# SAFETY INVARIANT: the only mutations to real refs are the per-framework `git branch -f <fw>`
# (angular, react, flask) and the optional annotated tag <fw>-vX.Y.Z, both inside export-main.sh.
# `main` is never touched.
[CmdletBinding()]
param(
  [string]$Version,
  [ValidateSet('angular', 'react', 'flask')][string]$Only
)
$ErrorActionPreference = 'Stop'
$sh = Join-Path $PSScriptRoot 'export-main.sh'
$argv = @($sh)
if ($Version) { $argv += @('--version', $Version) }
if ($Only)    { $argv += @('--only', $Only) }

# Prefer a native bash (WSL/Git-Bash) if present; fall back to `wsl bash`.
$bash = Get-Command bash -ErrorAction SilentlyContinue
if ($bash) {
  & $bash.Source @argv
} else {
  & wsl bash @argv
}
