param([switch]$CPU)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows 64 bits requis.' }
$runtime = Join-Path $PSScriptRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$env:UV_CACHE_DIR = Join-Path $runtime 'uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
$env:PYTHONUTF8 = '1'
function Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Echec de la commande : $Exe (code $LASTEXITCODE)" }
}
function Download-Checked([string]$Url, [string]$Target, [string]$Hash) {
    if (Test-Path -LiteralPath $Target) {
        if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLowerInvariant() -eq $Hash) { return }
        Remove-Item -LiteralPath $Target
    }
    $part = $Target + '.part'
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $part
    if ((Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash) {
        Remove-Item -LiteralPath $part
        throw "Empreinte SHA256 incorrecte : $Url"
    }
    Move-Item -LiteralPath $part -Destination $Target -Force
}
try {
    if (Test-Path '.runtime\installation.json') { Remove-Item -LiteralPath '.runtime\installation.json' }
    Write-Host 'Installation locale de Python, Node et des dependances. Aucun droit administrateur requis.'
    $uvZip = Join-Path $runtime 'uv-0.9.7.zip'
    Download-Checked 'https://github.com/astral-sh/uv/releases/download/0.9.7/uv-x86_64-pc-windows-msvc.zip' $uvZip '5d250c32d3604e28dbe18dc65c668ff628c53e00dde2c642576e831e4a60da64'
    $uvFolder = Join-Path $runtime 'uv'
    Expand-Archive -LiteralPath $uvZip -DestinationPath $uvFolder -Force
    $uv = Join-Path $uvFolder 'uv.exe'
    Checked $uv @('python','install','3.12','--no-progress')
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        Checked $uv @('venv','.venv','--python','3.12','--seed','--no-progress')
    }
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $nodeZip = Join-Path $runtime 'node-v24.11.0.zip'
    Download-Checked 'https://nodejs.org/dist/v24.11.0/node-v24.11.0-win-x64.zip' $nodeZip '1054540bce22b54ec7e50ebc078ec5d090700a77657607a58f6a64df21f49fdd'
    Expand-Archive -LiteralPath $nodeZip -DestinationPath $runtime -Force
    $node = Join-Path $runtime 'node'
    New-Item -ItemType Directory -Force -Path $node | Out-Null
    Copy-Item -LiteralPath (Join-Path $runtime 'node-v24.11.0-win-x64\node.exe') -Destination (Join-Path $node 'node.exe') -Force
    $build = 'cpu'
    if (-not $CPU) {
        $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
        if ($smi) {
            $driver = & $smi.Source --query-gpu=driver_version --format=csv,noheader 2>$null
            if ($LASTEXITCODE -eq 0) {
                foreach ($line in $driver) {
                    $v = $null
                    if ([version]::TryParse($line.Trim(),[ref]$v) -and $v.Major -ge 570) { $build='cu128' }
                }
            }
        }
    }
    Write-Host "Installation PyTorch : $build"
    Checked $uv @('pip','install','--python',$python,'torch==2.8.0','torchaudio==2.8.0','--index-url',"https://download.pytorch.org/whl/$build",'--no-progress')
    Checked $uv @('pip','install','--python',$python,'-r','requirements-local.txt','--no-progress')
    Checked $uv @('pip','check','--python',$python)
    if ($build -ne 'cpu') {
        & $python -X utf8 verifier-installation.py --require-cuda
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Calcul CUDA indisponible : installation du repli CPU.'
            $build = 'cpu'
            Checked $uv @('pip','install','--python',$python,'--reinstall','torch==2.8.0','torchaudio==2.8.0','--index-url','https://download.pytorch.org/whl/cpu','--no-progress')
        }
    }
    Checked $uv @('pip','check','--python',$python)
    Checked $python @('-X','utf8','verifier-installation.py')
    Write-Host 'Installation terminee. Ouvrez Lancer-DoublageBasic.cmd.'
} catch {
    Write-Host ('Installation interrompue : ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Vous pouvez relancer Installer-Windows.cmd pour reprendre.'
    exit 1
}
