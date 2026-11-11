"""Prépare une archive sans projets, PDF utilisateurs, environnements ni secrets."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parent


def main():
    files=sorted([p for p in ROOT.glob('*.py')]+[p for p in (ROOT/'web').glob('*') if p.is_file()]+
                 [p for p in (ROOT/'tests').glob('*.py')]+[ROOT/n for n in ('README.md','LIRE-MOI.txt','requirements.txt','installer.ps1','Installer-Windows.cmd','Lancer-Podcast.cmd','.gitignore')])
    document=['# Sources complètes — Podcast pédagogique 0.1.0','',
              'Application indépendante du dépôt de doublage. Voir README.md pour le fonctionnement et les limites.',
              'Les tests automatisés utilisent un Ollama simulé ; la qualité Mistral et Windows restent à vérifier.', '']
    manifest={}
    for path in files:
        raw=path.read_bytes();text=raw.decode('utf-8-sig');name=path.relative_to(ROOT).as_posix()
        if re.search(r'hf_[A-Za-z0-9]{20,}',text):raise RuntimeError('Jeton potentiel dans '+name)
        manifest[name]=hashlib.sha256(raw).hexdigest()
        longest=max((len(v) for v in re.findall(r'`+',text)),default=0);fence='`'*max(3,longest+1)
        language={'.py':'python','.js':'javascript','.css':'css','.html':'html','.ps1':'powershell','.cmd':'bat'}.get(path.suffix,'text')
        document.extend(['## '+name,'',fence+language,text.rstrip(),fence,''])
    source=ROOT/'SOURCE-COMPLET.md';source.write_text('\n'.join(document),encoding='utf-8')
    checksum=ROOT/'SHA256SUMS.txt';checksum.write_text('\n'.join(v+'  '+n for n,v in manifest.items())+'\n',encoding='utf-8')
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    target=output/'PodcastPedago-Windows.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files+[source,checksum]:archive.write(path,'PodcastPedago/'+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert not any('/donnees/' in n or '/.venv/' in n or '/.runtime/' in n for n in archive.namelist())
    info={'file':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'source_files':len(files)}
    (output/'release.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps(info))


if __name__=='__main__':main()
