[CmdletBinding()]
param(
    [string]$PythonPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$ReleaseVersion = "2.0.0-rc.1"
$ArtifactBaseName = "LEQI-Region-Changer-V$ReleaseVersion-win64"
$VenvPath = Join-Path $ProjectRoot ".venv-build"
$BuildPath = Join-Path $ProjectRoot "build"
$DistPath = Join-Path $ProjectRoot "dist"
$ReleasePath = Join-Path $ProjectRoot "release"
$PackagePath = Join-Path $BuildPath $ArtifactBaseName
$ZipPath = Join-Path $ReleasePath "$ArtifactBaseName.zip"
$ReleaseExePath = Join-Path $ReleasePath "LEQI Region Changer.exe"
$ChecksumPath = Join-Path $ReleasePath "SHA256SUMS.txt"
$SpecPath = Join-Path $ProjectRoot "LEQI Region Changer.spec"
$ProfilesPath = Join-Path $ProjectRoot "profiles"
$ThirdPartyLicensesPath = Join-Path $ProjectRoot "THIRD_PARTY_LICENSES"
$ZipBuilderPath = Join-Path $ProjectRoot "tools\build_zip.py"

function Assert-ProjectChildPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $rootWithSeparator = $ProjectRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $fullPath.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the project: $fullPath"
    }
    if ($fullPath.Equals($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify the project root itself."
    }
}

function Remove-ProjectItem {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    Assert-ProjectChildPath -Path $Path
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $Executable $($Arguments -join ' ')"
    }
}

function Get-BootstrapPython {
    if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
        $explicitPython = [System.IO.Path]::GetFullPath($PythonPath)
        if (-not (Test-Path -LiteralPath $explicitPython -PathType Leaf)) {
            throw "The requested Python executable does not exist: $explicitPython"
        }
        return @($explicitPython)
    }

    $launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        return @($launcher.Source, "-3")
    }

    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        return @($python.Source)
    }

    throw "Python 3 was not found. Install a 64-bit Python for Windows first."
}

function Assert-Amd64Pe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 64 -or $bytes[0] -ne 0x4D -or $bytes[1] -ne 0x5A) {
        throw "Built file is not a valid PE executable: $Path"
    }
    $peOffset = [System.BitConverter]::ToInt32($bytes, 0x3C)
    if ($peOffset -lt 0 -or $peOffset + 6 -gt $bytes.Length) {
        throw "Built file has an invalid PE header offset: $Path"
    }
    $machine = [System.BitConverter]::ToUInt16($bytes, $peOffset + 4)
    if ($machine -ne 0x8664) {
        throw "Built executable is not AMD64/x64 (PE machine 0x$($machine.ToString('X4')))."
    }
}

function Invoke-ExeSelfTest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Argument
    )

    $process = Start-Process -FilePath $Path -ArgumentList $Argument -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) {
        throw "Executable test $Argument failed with exit code $($process.ExitCode): $Path"
    }
}

function Set-ReproducibleTimestamps {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    Assert-ProjectChildPath -Path $Path
    $fixedTimestamp = [System.DateTimeOffset]::FromUnixTimeSeconds(1784592000).UtcDateTime
    Get-ChildItem -LiteralPath $Path -Recurse -Force | ForEach-Object {
        $_.LastWriteTimeUtc = $fixedTimestamp
    }
    (Get-Item -LiteralPath $Path -Force).LastWriteTimeUtc = $fixedTimestamp
}

if ($env:OS -ne "Windows_NT") {
    throw "This release build supports Windows x64 only."
}

$PreviousSourceDateEpoch = $env:SOURCE_DATE_EPOCH
$PreviousPythonHashSeed = $env:PYTHONHASHSEED
$PreviousDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$env:SOURCE_DATE_EPOCH = "1784592000"
$env:PYTHONHASHSEED = "0"
$env:PYTHONDONTWRITEBYTECODE = "1"

Push-Location $ProjectRoot
try {
    $bootstrap = @(Get-BootstrapPython)
    $bootstrapExecutable = $bootstrap[0]
    $bootstrapPrefix = @($bootstrap | Select-Object -Skip 1)

    Invoke-Checked -Executable $bootstrapExecutable -Arguments ($bootstrapPrefix + @(
        "-c",
        "import platform, struct, sys; machine = platform.machine().lower(); ok = sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8 and machine in ('amd64', 'x86_64'); raise SystemExit(0 if ok else 'Python 3.12 AMD64/x64 is required.')"
    ))

    New-Item -ItemType Directory -Path $ReleasePath -Force | Out-Null
    foreach ($staleArtifact in @($ZipPath, $ReleaseExePath, $ChecksumPath)) {
        Assert-ProjectChildPath -Path $staleArtifact
        if (Test-Path -LiteralPath $staleArtifact) {
            Remove-Item -LiteralPath $staleArtifact -Force
        }
    }

    Remove-ProjectItem -Path $VenvPath
    Remove-ProjectItem -Path $BuildPath
    Remove-ProjectItem -Path $DistPath

    Invoke-Checked -Executable $bootstrapExecutable -Arguments ($bootstrapPrefix + @(
        "-m",
        "venv",
        $VenvPath
    ))

    $VenvPython = Join-Path $VenvPath "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw "The build environment was not created correctly: $VenvPython"
    }

    Invoke-Checked -Executable $VenvPython -Arguments @(
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-compile",
        "-r",
        (Join-Path $ProjectRoot "requirements-build.txt")
    )

    Set-ReproducibleTimestamps -Path $VenvPath

    Invoke-Checked -Executable $VenvPython -Arguments @(
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-v"
    )

    Invoke-Checked -Executable $VenvPython -Arguments @(
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        $DistPath,
        "--workpath",
        $BuildPath,
        $SpecPath
    )

    $BuiltExe = Join-Path $DistPath "LEQI Region Changer.exe"
    if (-not (Test-Path -LiteralPath $BuiltExe -PathType Leaf)) {
        throw "PyInstaller did not create the expected executable: $BuiltExe"
    }
    if (-not (Test-Path -LiteralPath $ProfilesPath -PathType Container)) {
        throw "The profiles directory is missing: $ProfilesPath"
    }
    if (-not (Test-Path -LiteralPath $ThirdPartyLicensesPath -PathType Container)) {
        throw "The third-party licenses directory is missing: $ThirdPartyLicensesPath"
    }

    Assert-Amd64Pe -Path $BuiltExe
    Invoke-ExeSelfTest -Path $BuiltExe -Argument "--self-test"
    Invoke-ExeSelfTest -Path $BuiltExe -Argument "--ui-smoke-test"

    Remove-ProjectItem -Path $PackagePath
    New-Item -ItemType Directory -Path $PackagePath -Force | Out-Null
    Copy-Item -LiteralPath $BuiltExe -Destination (Join-Path $PackagePath "LEQI Region Changer.exe")
    Copy-Item -LiteralPath $ProfilesPath -Destination (Join-Path $PackagePath "profiles") -Recurse
    Copy-Item -LiteralPath $ThirdPartyLicensesPath -Destination (Join-Path $PackagePath "THIRD_PARTY_LICENSES") -Recurse

    foreach ($documentName in @("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md")) {
        $sourceDocument = Join-Path $ProjectRoot $documentName
        if (-not (Test-Path -LiteralPath $sourceDocument -PathType Leaf)) {
            throw "Required release document is missing: $sourceDocument"
        }
        Copy-Item -LiteralPath $sourceDocument -Destination (Join-Path $PackagePath $documentName)
    }

    Invoke-Checked -Executable $VenvPython -Arguments @(
        $ZipBuilderPath,
        $PackagePath,
        $ZipPath
    )
    Copy-Item -LiteralPath $BuiltExe -Destination $ReleaseExePath

    $zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZipPath).Hash
    $exeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ReleaseExePath).Hash
    Set-Content -LiteralPath $ChecksumPath -Encoding ASCII -Value @(
        "$exeHash  $([System.IO.Path]::GetFileName($ReleaseExePath))",
        "$zipHash  $([System.IO.Path]::GetFileName($ZipPath))"
    )

    Write-Host "Build complete."
    Write-Host "Artifact: $ZipPath"
    Write-Host "Executable: $ReleaseExePath"
    Write-Host "Checksums: $ChecksumPath"
}
finally {
    Pop-Location
    if ($null -eq $PreviousSourceDateEpoch) {
        Remove-Item Env:SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue
    }
    else {
        $env:SOURCE_DATE_EPOCH = $PreviousSourceDateEpoch
    }
    if ($null -eq $PreviousPythonHashSeed) {
        Remove-Item Env:PYTHONHASHSEED -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONHASHSEED = $PreviousPythonHashSeed
    }
    if ($null -eq $PreviousDontWriteBytecode) {
        Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONDONTWRITEBYTECODE = $PreviousDontWriteBytecode
    }
}
