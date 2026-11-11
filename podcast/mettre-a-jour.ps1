param([string]$Dossier, [switch]$SansLancement)
$ErrorActionPreference = 'Stop'
$sourceDir = $PSScriptRoot
$manifestPath = Join-Path $sourceDir 'manifest-correctif.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Extraire tout le ZIP correctif avant de lancer Mettre-a-jour.cmd.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$allowed = @('app.py','storage.py','pipeline.py','quality.py','llm.py','pdfs.py','web/index.html','web/app.js','web/style.css','Lancer-Podcast.cmd','README.md','README-CORRECTIF.txt','SOURCE-COMPLET.md')
if (-not $manifest.files -or $manifest.files.Count -ne $allowed.Count) { throw 'Le correctif ne contient pas tous les fichiers attendus.' }
$seen = @{}
foreach ($item in $manifest.files) {
    if ($item.path -notin $allowed -or $seen.ContainsKey($item.path)) { throw 'Fichier inattendu ou repete dans le correctif.' }
    $seen[$item.path] = $true
    $source = Join-Path $sourceDir $item.path
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw ('Fichier manquant : ' + $item.path) }
    if ($item.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $item.sha256) { throw ('Fichier incomplet : ' + $item.path) }
}
if ($Dossier) {
    $targetDir = [IO.Path]::GetFullPath($Dossier)
} else {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Choisissez le dossier de PodcastPedago contenant Lancer-Podcast.cmd. Fermez sa fenetre de lancement avant de continuer.'
    $dialog.ShowNewFolderButton = $false
    $candidates = @((Join-Path $env:USERPROFILE 'Downloads\PodcastPedago-Windows\PodcastPedago'), (Join-Path $env:USERPROFILE 'Downloads\PodcastPedago'))
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'Lancer-Podcast.cmd')) { $dialog.SelectedPath = $candidate; break }
    }
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 0 }
    $targetDir = $dialog.SelectedPath
    $dialog.Dispose()
}
foreach ($name in @('Lancer-Podcast.cmd','app.py','pipeline.py','storage.py')) {
    if (-not (Test-Path -LiteralPath (Join-Path $targetDir $name) -PathType Leaf)) { throw 'Choisissez le dossier contenant Lancer-Podcast.cmd et les fichiers Python du programme.' }
}
if ([IO.Path]::GetFullPath($targetDir).TrimEnd('\') -eq [IO.Path]::GetFullPath($sourceDir).TrimEnd('\')) { throw 'Choisissez le dossier de votre installation existante, pas le dossier temporaire du correctif.' }
$targetApp = Join-Path $targetDir 'app.py'
$running = @()
if (Get-Command Get-CimInstance -ErrorAction SilentlyContinue) {
    $running = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and $_.CommandLine.IndexOf($targetApp, [StringComparison]::OrdinalIgnoreCase) -ge 0
    })
}
if ($running.Count -gt 0) { throw 'Fermez la fenetre de lancement de PodcastPedago, puis relancez Mettre-a-jour.cmd.' }
$backupDir = Join-Path $targetDir ('mises-a-jour\sauvegarde-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
$records = @()
foreach ($item in $manifest.files) {
    $destination = Join-Path $targetDir $item.path
    $backup = Join-Path $backupDir $item.path
    $existed = Test-Path -LiteralPath $destination -PathType Leaf
    if ($existed) {
        New-Item -ItemType Directory -Path (Split-Path $backup -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $destination -Destination $backup -Force
    }
    $records += [pscustomobject]@{ Path=$item.path; Destination=$destination; Backup=$backup; Existed=$existed; Hash=$item.sha256 }
}
try {
    foreach ($record in $records) {
        New-Item -ItemType Directory -Path (Split-Path $record.Destination -Parent) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $sourceDir $record.Path) -Destination $record.Destination -Force
        if ((Get-FileHash -LiteralPath $record.Destination -Algorithm SHA256).Hash -ne $record.Hash) { throw ('Verification impossible : ' + $record.Path) }
    }
} catch {
    $failure = $_
    foreach ($record in $records) {
        try {
            if ($record.Existed) { Copy-Item -LiteralPath $record.Backup -Destination $record.Destination -Force }
            elseif (Test-Path -LiteralPath $record.Destination -PathType Leaf) { Remove-Item -LiteralPath $record.Destination -Force }
        } catch { Write-Warning ('Restauration manuelle possible dans : ' + $backupDir) }
    }
    throw $failure
}
if ($SansLancement) {
    Write-Output ('Mise a jour ' + $manifest.version + ' terminee : ' + $targetDir)
} else {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(('Mise a jour ' + $manifest.version + ' terminee. Vos PDF et projets sont conserves. Le programme va rouvrir : verifiez le numero de version en haut, puis cliquez sur Continuer.'), 'PodcastPedago') | Out-Null
    Start-Process -FilePath (Join-Path $targetDir 'Lancer-Podcast.cmd') -WorkingDirectory $targetDir
}
