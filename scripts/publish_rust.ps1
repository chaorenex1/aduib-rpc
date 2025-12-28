Param(
    # Publish to crates.io by default. Use -DryRun first.
    [switch]$DryRun,

    # Skip `cargo test` step.
    [switch]$SkipTests,

    # Allow publishing with uncommitted git changes.
    [switch]$AllowDirty,

    # Optional: bump crate version in crates/<pkg>/Cargo.toml before publishing.
    # Example: -Version 0.1.1
    [string]$Version,

    # Optional: create a git tag after version bump/publish.
    [switch]$Tag,

    # Tag prefix (default: aduib-rpc-v).
    [string]$TagPrefix = "aduib-rpc-v",

    # Override package name (defaults to aduib-rpc)
    [string]$Package = "aduib-rpc",

    # Optional: provide token for this process only.
    # Prefer setting env var CARGO_REGISTRY_TOKEN instead of passing on CLI.
    [string]$Token
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$RustSdk = Join-Path $RepoRoot "rust-sdk"
$CrateDir = Join-Path $RustSdk "crates\$Package"
$CrateToml = Join-Path $CrateDir "Cargo.toml"

if ($Token -and $Token.Trim().Length -gt 0) {
    $env:CARGO_REGISTRY_TOKEN = $Token
}

if (-not $env:CARGO_REGISTRY_TOKEN -or $env:CARGO_REGISTRY_TOKEN.Trim().Length -eq 0) {
    Write-Host "Hint: set CARGO_REGISTRY_TOKEN (crates.io API token) before publishing."
}

function Assert-GitClean {
    param([string]$Repo)
    if ($AllowDirty) { return }
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        Write-Host "Warning: git not found; skipping clean working tree check."
        return
    }
    Push-Location $Repo
    try {
        $dirty = (git status --porcelain)
        if ($dirty) {
            throw "Working tree is dirty. Commit/stash changes or pass -AllowDirty."
        }
    } finally {
        Pop-Location
    }
}

function Set-CrateVersion {
    param(
        [Parameter(Mandatory=$true)][string]$TomlPath,
        [Parameter(Mandatory=$true)][string]$NewVersion
    )

    if (-not (Test-Path $TomlPath)) {
        throw "Cargo.toml not found: $TomlPath"
    }

    $content = Get-Content -Raw -LiteralPath $TomlPath
    # Replace the first occurrence of version = "..." under [package].
    # This is intentionally simple and avoids extra dependencies.
    $updated = $content -replace '(?ms)(\[package\][^\[]*?\bversion\s*=\s*")([^"]+)(")', "`${1}$NewVersion`${3}"
    if ($updated -eq $content) {
        throw "Failed to update version in $TomlPath (pattern not found)"
    }
    Set-Content -LiteralPath $TomlPath -Value $updated -Encoding UTF8
}

function New-GitTag {
    param(
        [Parameter(Mandatory=$true)][string]$Repo,
        [Parameter(Mandatory=$true)][string]$Name
    )
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        throw "git not found; cannot create tag."
    }
    Push-Location $Repo
    try {
        git tag $Name
    } finally {
        Pop-Location
    }
}

Push-Location $RustSdk
try {
    Write-Host "Rust SDK dir: $RustSdk"

    if ($Version -and $Version.Trim().Length -gt 0) {
        Assert-GitClean -Repo $RepoRoot
        Write-Host "Bumping crate version to $Version in $CrateToml"
        Set-CrateVersion -TomlPath $CrateToml -NewVersion $Version
    }

    # Basic sanity checks.
    cargo -V | Out-Null

    if (-not $SkipTests) {
        Write-Host "Running cargo test..."
        cargo test
    }

    # Ensure the tarball can be built (catches missing files like proto) before actual upload.
    Write-Host "Running cargo publish --dry-run verification..."
    cargo publish -p $Package --dry-run | Out-Null

    if ($DryRun) {
        Write-Host "Publishing (dry-run) package: $Package"
        cargo publish -p $Package --dry-run
    } else {
        Write-Host "Publishing package: $Package"
        cargo publish -p $Package
    }

    if ($Tag) {
        if (-not ($Version -and $Version.Trim().Length -gt 0)) {
            throw "-Tag requires -Version so the tag name is deterministic."
        }
        $tagName = "$TagPrefix$Version"
        if (-not $AllowDirty) {
            Assert-GitClean -Repo $RepoRoot
        } else {
            Write-Host "Warning: creating tag on current HEAD; uncommitted changes are not included." 
        }
        Write-Host "Creating git tag: $tagName"
        New-GitTag -Repo $RepoRoot -Name $tagName
    }
}
finally {
    Pop-Location
}
