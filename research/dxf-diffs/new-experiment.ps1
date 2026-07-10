[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^RE-\d{4}$')]
    [string]$Id,

    [Parameter(Mandatory = $true)]
    [string]$Title,

    [Parameter(Mandatory = $true)]
    [string]$HostEntity,

    [string]$Status = 'planned',
    [string]$AutoCADVersion = 'TBD',
    [string]$DxfSaveFormat = 'TBD',
    [string]$ChangeType = 'TBD',
    [string]$FieldType = 'TBD',
    [string[]]$TargetEzdxfModules = @('TBD')
)

$ErrorActionPreference = 'Stop'

function New-Slug {
    param([string]$Value)

    $slug = $Value.ToLowerInvariant() -replace '[^a-z0-9]+', '-'
    $slug = $slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($slug)) {
        throw 'Title produced an empty slug.'
    }
    return $slug
}

function Ascii-Write {
    param(
        [string]$Path,
        [string]$Content
    )

    Set-Content -LiteralPath $Path -Value $Content -Encoding ASCII
}

function Escape-TableCell {
    param([string]$Value)

    return $Value.Replace('|', '\|')
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$slug = New-Slug -Value $Title
$folderName = "$Id-$slug"
$experimentDir = Join-Path $root $folderName
$indexPath = Join-Path $root 'index.md'

if (Test-Path -LiteralPath $experimentDir) {
    throw "Experiment folder already exists: $experimentDir"
}

if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "Missing index file: $indexPath"
}

$indexContent = Get-Content -LiteralPath $indexPath -Raw
if ($indexContent -match [regex]::Escape("| $Id |")) {
    throw "Experiment id already exists in index: $Id"
}

New-Item -ItemType Directory -Path $experimentDir | Out-Null

$targetModulesYaml = ($TargetEzdxfModules | ForEach-Object { "  - $_" }) -join "`r`n"
$targetModulesTable = ($TargetEzdxfModules -join ', ')

$metaYaml = @"
id: $Id
title: $Title
status: $Status
host_entity: $HostEntity
autocad_version: $AutoCADVersion
dxf_save_format: $DxfSaveFormat
change_type: $ChangeType
field_type: $FieldType
source_artifacts:
  baseline_before_dxf: TBD
  edited_after_dxf: TBD
  baseline_before_normalized_dxf: TBD
  edited_after_normalized_dxf: TBD
target_dxfpy_modules:
$targetModulesYaml
notes:
  - Fill in source artifact paths after the experiment runs.
"@

$procedure = @"
# Procedure

1. Describe how the baseline DXF was generated.
2. Describe the exact AutoCAD or AutoLISP change.
3. Record the DXF save format.
4. Describe how the diff was produced.

Files used in the final comparison:

- Baseline: TBD
- Edited: TBD
"@

$findings = @"
# Findings

## Summary

Replace with a short description of the confirmed structural change.

## Confirmed Changes

1. TBD

## Key Excerpts

Example excerpt:

    TBD

## Interpretation

- TBD

## Likely dxfpy Targets

$(($TargetEzdxfModules | ForEach-Object { "- $_" }) -join "`r`n")

## Non-Goals From This Experiment

- TBD
"@

$notes = @"
# Notes

## Noise Observed

- TBD

## Open Questions

1. TBD

## Recommended Follow-Up Experiments

1. TBD
"@

Ascii-Write -Path (Join-Path $experimentDir 'meta.yaml') -Content $metaYaml.TrimStart()
Ascii-Write -Path (Join-Path $experimentDir 'procedure.md') -Content $procedure.TrimStart()
Ascii-Write -Path (Join-Path $experimentDir 'findings.md') -Content $findings.TrimStart()
Ascii-Write -Path (Join-Path $experimentDir 'notes.md') -Content $notes.TrimStart()

$row = "| $(Escape-TableCell $Id) | $(Escape-TableCell $Title) | $(Escape-TableCell $Status) | $(Escape-TableCell $HostEntity) | $(Escape-TableCell $AutoCADVersion) | $(Escape-TableCell 'TBD') | $(Escape-TableCell $targetModulesTable) |"
Add-Content -LiteralPath $indexPath -Value $row -Encoding ASCII

Write-Host "Created experiment scaffold: $experimentDir"
Write-Host "Appended index row for $Id"
