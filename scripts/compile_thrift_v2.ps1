$ErrorActionPreference = 'Stop'

$thriftExe = "C:\Users\zarag\Downloads\thrift-0.22.0.exe"
if (!(Test-Path $thriftExe)) {
  throw "Missing thrift compiler at $thriftExe"
}

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$idl = "src\aduib_rpc\proto\aduib_rpc_v2.thrift"
$outDir = "thrift_v2"

if (Test-Path $outDir) {
  Remove-Item -Recurse -Force $outDir
}
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

& $thriftExe --gen py -out $outDir $idl

Write-Output "Generated Thrift v2 python bindings into $outDir"

