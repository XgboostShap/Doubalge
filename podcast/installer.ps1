$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    throw 'Cette distribution est prevue pour Windows 10/11 x64 (Intel ou AMD).'
}
$appDir = $PSScriptRoot
$runtime = Join-Path $appDir '.runtime'
New-Item -ItemType Directory -Force $runtime | Out-Null
$uv = Join-Path $runtime 'uv.exe'
if (-not (Test-Path $uv)) {
    Write-Host 'Telechargement du gestionnaire Python officiel uv.'
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/astral-sh/uv/releases/tags/0.13.7' -Headers @{'User-Agent'='PodcastPedago-Installer'}
    $asset = $release.assets | Where-Object { $_.name -eq 'uv-x86_64-pc-windows-msvc.zip' } | Select-Object -First 1
    if (-not $asset) { throw 'Distribution officielle uv introuvable.' }
    if ($asset.digest -notmatch '^sha256:([a-fA-F0-9]{64})$') { throw 'Empreinte officielle uv absente.' }
    $expected = $Matches[1]
    if (-not $asset.browser_download_url.StartsWith('https://github.com/astral-sh/uv/releases/download/')) { throw 'URL de distribution inattendue.' }
    $archive = Join-Path $runtime 'uv.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $archive
    if ((Get-FileHash -Algorithm SHA256 $archive).Hash.ToLower() -ne $expected.ToLower()) { throw 'Le telechargement uv est incomplet ou son empreinte est incorrecte.' }
    $extract = Join-Path $runtime 'uv-extract'
    Expand-Archive -Path $archive -DestinationPath $extract -Force
    $exe = Get-ChildItem $extract -Recurse -Filter 'uv.exe' | Select-Object -First 1
    if (-not $exe) { throw 'Executable uv absent de l archive.' }
    Copy-Item $exe.FullName $uv -Force
}
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
$env:UV_CACHE_DIR = Join-Path $runtime 'cache'
$env:UV_PYTHON_BIN_DIR = Join-Path $runtime 'bin'
Write-Host 'Installation de Python 3.12 dans le dossier de l application.'
& $uv python install 3.12 --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { throw 'Installation de Python interrompue. Verifiez la connexion puis relancez.' }
$venv = Join-Path $appDir '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    & $uv venv --python 3.12 --managed-python $venv
    if ($LASTEXITCODE -ne 0) { throw 'Creation de l environnement Python impossible.' }
}
& $uv pip install --python $python -r (Join-Path $appDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installation des dependances impossible. Relancez pour reprendre.' }
& $uv pip check --python $python
if ($LASTEXITCODE -ne 0) { throw 'Les dependances ne sont pas coherentes.' }
& $python -c "from pypdf import PdfReader; import app; print('Programme importe correctement.')"
if ($LASTEXITCODE -ne 0) { throw 'La verification du programme a echoue.' }
Write-Host 'Pret. Ouvrez Lancer-Podcast.cmd.' -ForegroundColor Green
Write-Host 'Pour la redaction, Ollama doit etre ouvert avec un modele Mistral installe.'
