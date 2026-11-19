"""Relecture Docling d’une page, facultative, avec ressources déjà présentes."""
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

from llm import Cancelled
from storage import write, write_text


def artifacts():
    return Path(os.environ.get('DOCLING_ARTIFACTS_PATH',str(Path(__file__).resolve().parent/'modeles/docling/artifacts')))


def available():
    return importlib.util.find_spec('docling') is not None and artifacts().is_dir()


def run(pdf,page,target,cancelled,progress):
    if not available():
        raise ValueError('Docling local et ses modèles doivent être préparés séparément. Aucun téléchargement automatique : ouvrez le PDF pour la vérification visuelle.')
    progress('Relecture locale Docling — page '+str(page)+' ; aucun téléchargement')
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lecture-',dir=target.parent) as temporary:
        output=Path(temporary)/'result.json';log=Path(temporary)/'journal.txt'
        env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1',
             'DO_NOT_TRACK':'1','OTEL_SDK_DISABLED':'true','PYTHONDONTWRITEBYTECODE':'1'}
        command=[sys.executable,str(Path(__file__).resolve()),'--worker',str(pdf),str(page),str(artifacts()),str(output)]
        with log.open('wb') as stream:
            process=subprocess.Popen(command,stdout=stream,stderr=stream,env=env)
            try:
                while process.poll() is None:
                    if cancelled.wait(.2):raise Cancelled()
                if process.returncode:
                    raise ValueError('Relecture locale impossible : modèles absents, incompatibles ou page non lisible. Aucun téléchargement autorisé. Détail : '+log.read_text(errors='replace')[-1800:])
                value=json.loads(output.read_text(encoding='utf-8'))
            finally:
                if process.poll() is None:process.kill();process.wait()
        write(target.with_suffix('.json'),value)
        write_text(target,'# Relecture locale — page '+str(page)+'\n\n'+
            'Aide à comparer visuellement avec le PDF. Les formules peuvent rester ambiguës ; cette lecture ne valide aucune idée automatiquement.\n\n'+value['markdown'])
        return value


def offline_worker(pdf,page,models,output):
    """Bloquer les accès Python extérieurs avant d’importer les bibliothèques."""
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',
                      DO_NOT_TRACK='1',OTEL_SDK_DISABLED='true')
    def audit(event,args):
        if event=='socket.getaddrinfo':host=args[0]
        elif event=='socket.connect' and args[0].family in (socket.AF_INET,socket.AF_INET6):host=args[1][0]
        else:return
        if isinstance(host,bytes):host=host.decode()
        try:local=host=='localhost' or ipaddress.ip_address(host).is_loopback
        except ValueError:local=False
        if not local:raise PermissionError('Relecture PDF hors connexion : accès réseau extérieur interdit.')
    sys.addaudithook(audit)
    from docling.datamodel.accelerator_options import AcceleratorDevice,AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter,PdfFormatOption
    options=PdfPipelineOptions(artifacts_path=Path(models),do_ocr=False,do_table_structure=True,
        do_formula_enrichment=True,enable_remote_services=False,
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU,num_threads=4))
    start=time.monotonic()
    converter=DocumentConverter(format_options={InputFormat.PDF:PdfFormatOption(pipeline_options=options)})
    document=converter.convert(Path(pdf),page_range=(page,page),raises_on_error=True).document
    text=document.export_to_markdown(page_no=page)
    if not text.strip():raise ValueError('Aucun texte obtenu pour cette page.')
    write(Path(output),{'engine':'docling','page':page,'sha256':hashlib.sha256(Path(pdf).read_bytes()).hexdigest(),
                        'markdown':text,'seconds':round(time.monotonic()-start,2)})


if __name__=='__main__':
    if len(sys.argv)!=6 or sys.argv[1]!='--worker':raise SystemExit('Commande de relecture interne uniquement.')
    offline_worker(sys.argv[2],int(sys.argv[3]),sys.argv[4],sys.argv[5])
