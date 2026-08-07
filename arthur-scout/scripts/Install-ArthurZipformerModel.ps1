[CmdletBinding()]
param(
    [string] $InstallRoot = (Join-Path $env:LOCALAPPDATA 'Arthur\runtime'),
    [string] $ModelDirectory,
    [string] $PythonExecutable = '',
    [string] $WakeWord = 'Arthur',
    [double] $HotwordScore = 2.0,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'

if (-not $PythonExecutable) {
    $localPython = Join-Path (Split-Path -Parent ([System.IO.Path]::GetFullPath($InstallRoot))) 'python\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        $PythonExecutable = $localPython
    } else {
        $command = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $command -or -not $command.Source) {
            throw 'Arthur Python is unavailable. Run install.ps1 -InstallDependencies first.'
        }
        $PythonExecutable = $command.Source
    }
}

if (-not $ModelDirectory) {
    $ModelDirectory = Join-Path $InstallRoot 'models\zipformer-en-balanced-int8'
}

$modelRevision = '9a65b6ea94c311ca770c2bf895b30f456a22d703'
$bpeRevision = 'df8a1ee67abb67244b87d8011ec64ba46c6e97c0'
$modelRepository = 'csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-06-21'
$bpeRepository = 'marcoyang/icefall-libri-giga-pruned-transducer-stateless7-streaming-2023-04-04'

$downloads = @(
    [pscustomobject]@{
        RelativePath = 'encoder-epoch-99-avg-1.int8.onnx'
        Url = "https://huggingface.co/$modelRepository/resolve/$modelRevision/encoder-epoch-99-avg-1.int8.onnx"
        Sha256 = '32C98281C7BD8B63E3E142D007251B37F120572E8FDEA9A4F5A79CE22B10EC4F'
    },
    [pscustomobject]@{
        RelativePath = 'decoder-epoch-99-avg-1.int8.onnx'
        Url = "https://huggingface.co/$modelRepository/resolve/$modelRevision/decoder-epoch-99-avg-1.int8.onnx"
        Sha256 = '093E23C90869898F761F60AA3363F96D43B9C6E5C06A57860C3A5B3407AB8320'
    },
    [pscustomobject]@{
        RelativePath = 'joiner-epoch-99-avg-1.int8.onnx'
        Url = "https://huggingface.co/$modelRepository/resolve/$modelRevision/joiner-epoch-99-avg-1.int8.onnx"
        Sha256 = '831477D390E59A61F1B6A6F763B9903E6C6366FF6034F1DDBA613BE82637122F'
    },
    [pscustomobject]@{
        RelativePath = 'tokens.txt'
        Url = "https://huggingface.co/$modelRepository/resolve/$modelRevision/tokens.txt"
        Sha256 = '49E3C2646595FD907228B3C6787069658F67B17377C60AEB8619C4551B2316FB'
    },
    [pscustomobject]@{
        RelativePath = 'data\lang_bpe_500\bpe.model'
        Url = "https://huggingface.co/$bpeRepository/resolve/$bpeRevision/data/lang_bpe_500/bpe.model"
        Sha256 = 'C53433DE083C4A6AD12D034550EF22DE68CEC62C4F58932A7B6B8B2F1E743FA5'
    }
)

function Get-ArthurSha256 {
    param([string] $Path)

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($sha256.ComputeHash($stream))).Replace('-', '')
        }
        finally {
            $sha256.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Get-VerifiedFile {
    param(
        [pscustomobject] $Download
    )

    $target = Join-Path $ModelDirectory $Download.RelativePath
    if (Test-Path -LiteralPath $target) {
        $currentHash = Get-ArthurSha256 -Path $target
        if ($currentHash -eq $Download.Sha256) {
            Write-Host "[Arthur model] Verified $($Download.RelativePath)"
            return
        }
        if (-not $Force) {
            throw "Hash mismatch for $target. Re-run with -Force to replace it."
        }
    }

    $targetDirectory = Split-Path -Parent $target
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    $partial = "$target.download"
    try {
        Write-Host "[Arthur model] Downloading $($Download.RelativePath)"
        Invoke-WebRequest -Uri $Download.Url -OutFile $partial -UseBasicParsing
        $downloadedHash = Get-ArthurSha256 -Path $partial
        if ($downloadedHash -ne $Download.Sha256) {
            throw "Downloaded hash mismatch for $($Download.RelativePath)"
        }
        Move-Item -LiteralPath $partial -Destination $target -Force
    } finally {
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
    }
}

New-Item -ItemType Directory -Path $ModelDirectory -Force | Out-Null
foreach ($download in $downloads) {
    Get-VerifiedFile -Download $download
}

$bpeModel = Join-Path $ModelDirectory 'data\lang_bpe_500\bpe.model'
$bpeVocab = Join-Path $ModelDirectory 'bpe.vocab'
$vocabGenerator = @'
import pathlib
import sys

import sentencepiece as spm

model_path = pathlib.Path(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
processor = spm.SentencePieceProcessor(model_file=str(model_path))
with output_path.open("w", encoding="utf-8", newline="\n") as handle:
    for index in range(processor.get_piece_size()):
        handle.write(f"{processor.id_to_piece(index)}\t{processor.get_score(index)}\n")
'@
$env:PYTHONNOUSERSITE = '1'
$vocabGenerator | & $PythonExecutable -s - $bpeModel $bpeVocab
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to generate bpe.vocab. Install the sentencepiece Python package.'
}

$hotwordsPath = Join-Path $ModelDirectory 'hotwords.txt'
$hotwordText = "$($WakeWord.ToUpperInvariant()) :$HotwordScore"
Set-Content -LiteralPath $hotwordsPath -Value $hotwordText -Encoding Ascii

$manifest = [ordered]@{
    installedAt = (Get-Date).ToString('o')
    modelRepository = $modelRepository
    modelRevision = $modelRevision
    bpeRepository = $bpeRepository
    bpeRevision = $bpeRevision
    wakeWord = $WakeWord
    hotwordScore = $HotwordScore
    files = @(
        $downloads | ForEach-Object {
            $path = Join-Path $ModelDirectory $_.RelativePath
            [ordered]@{
                path = $_.RelativePath
                sha256 = (Get-ArthurSha256 -Path $path)
            }
        }
    )
}
$manifestPath = Join-Path $ModelDirectory 'arthur-model-manifest.json'
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "[Arthur model] Zipformer ready at $ModelDirectory"
