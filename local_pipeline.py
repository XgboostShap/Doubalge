"""Traitements isolés : une invocation par tâche, secret reçu sur stdin."""
from __future__ import annotations
import base64
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from commun import FFMPEG, duree_et_taille
from edition import atomic_json, read_json, sha256, validate, initial_edit


def run(args):
    subprocess.run([str(x) for x in args], check=True, stdout=subprocess.DEVNULL)


def device():
    import torch
    if torch.cuda.is_available():
        try:
            x = torch.ones((64, 64), device='cuda')
            (x @ x).sum().item()
            return 'cuda'
        except Exception:
            print('GPU indisponible pour ce calcul : repli CPU.', flush=True)
    return 'cpu'


def analyze(folder, options, token):
    from telecharge import extrait_audio
    p = read_json(folder / 'projet.json')
    source = folder / 'original.mp4'
    if not source.exists():
        from telecharge import telecharge
        telecharge(p['url'], str(folder / 'telechargement'))
        shutil.copyfile(folder / 'telechargement/source.mp4', source)
    duration, width, height = duree_et_taille(str(source))
    if duration <= 0:
        raise ValueError('Vidéo vide')
    fingerprint = sha256(source)
    imported = options.get('corrections')
    if imported:
        # L'empreinte du fichier ORIGINAL est vérifiée avant tout réencodage.
        if imported.get('source_sha256') != fingerprint:
            raise ValueError('Ce JSON ne correspond pas au fichier vidéo original')
        voices = {}
        for row in imported.get('characters', []):
            key = row.get('id')
            import re
            if not re.fullmatch(r'voice:\d{1,4}', str(key)):
                raise ValueError('Identifiant de voix invalide')
            voices[key] = str(row.get('label', key))[:80]
        for row in imported.get('intervals', []):
            key = row.get('character')
            if key is not None:
                import re
                if not re.fullmatch(r'voice:\d{1,4}', str(key)):
                    raise ValueError('Identifiant de voix invalide')
                voices.setdefault(key, 'Voix ' + str(int(key.split(':')[1]) + 1))
        p.update(duration=duration, source_sha256=fingerprint, analysis_id=imported.get('analysis_id'), voices=voices)
        if not isinstance(p['analysis_id'], str) or not p['analysis_id']:
            raise ValueError("Identifiant d'analyse manquant")
        edit = validate(imported, p)
        # Aucune baseline automatique inventée à partir des corrections.
        analysis = dict(imported=True, raw_events=None, intervals=[], cuts=[])
    else:
        print('Extraction audio et diarisation…', flush=True)
        wav = folder / 'audio.wav'
        extrait_audio(str(source), str(wav))
        from diarisation import diarise_pyannote
        selected = device()
        try:
            events = diarise_pyannote(str(wav), token or None, options.get('speakers'), device=selected)
        except Exception:
            if selected == 'cpu':
                raise
            print('Échec de l’analyse GPU : nouvel essai sur CPU.', flush=True)
            events = diarise_pyannote(str(wav), token or None, options.get('speakers'), device='cpu')
        voices = {f"voice:{row['speaker']}": f"Voix {row['speaker'] + 1}" for row in events}
        p.update(duration=duration, source_sha256=fingerprint, analysis_id=uuid.uuid4().hex, voices=voices)
        intervals = [dict(id=uuid.uuid4().hex, start=max(0, row['start']), end=min(duration, row['end']),
                          character=f"voice:{row['speaker']}", reviewed=False) for row in events
                     if row['end'] > row['start'] and row['start'] < duration]
        (folder.parents[1] / 'cache/huggingface/complete.marker').touch()
        print('Détection des changements de plan…', flush=True)
        import cv2
        cap = cv2.VideoCapture(str(source))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        prev, cuts, n, last = None, [], 0, -1.
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                gray = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
                t = n / fps
                if prev is not None and abs(gray.astype('float32') - prev).mean() > 32 and t - last > .25:
                    cuts.append(dict(id=uuid.uuid4().hex, time=round(t, 3), reviewed=False))
                    last = t
                prev, n = gray, n + 1
        finally:
            cap.release()
        analysis = dict(imported=False, raw_events=events, intervals=intervals, cuts=cuts,
                        note='Propositions audio non validées ; plans détectés par différence visuelle.')
        edit = initial_edit(p, analysis)
    # Prévisualisation compatible navigateur ; original conservé séparément.
    print('Préparation du lecteur et de la forme d’onde…', flush=True)
    run([FFMPEG, '-y', '-i', source, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', folder / 'lecture.mp4'])
    waveform(source, folder / 'onde.json')
    p.update(ready=True, revision=p.get('revision', 0) + 1)
    atomic_json(folder / 'analyse.json', analysis)
    atomic_json(folder / 'corrections.json', edit)
    atomic_json(folder / 'projet.json', p)


def waveform(source, target):
    import numpy as np
    result = subprocess.run([FFMPEG, '-v', 'error', '-i', str(source), '-vn', '-ac', '1', '-ar', '2000',
                             '-f', 'f32le', '-'], capture_output=True, check=True)
    samples = np.frombuffer(result.stdout, dtype='<f4')
    size = max(1, int(len(samples) / 2400))
    peaks = [round(float(np.abs(samples[i:i+size]).max()), 4) for i in range(0, len(samples), size)]
    atomic_json(target, peaks)


def separate(folder):
    from duo import prepare_stems
    prepare_stems(folder / 'original.mp4', folder / 'duo-cache', device=device())


def export(folder, options):
    from duo import prepare_audio
    p = read_json(folder / 'projet.json')
    edit = validate(read_json(folder / 'corrections.json'), p)
    if options.get('voice') not in p['voices'] and options.get('mode') != 'silent':
        raise ValueError('Choisir une voix')
    mode = options.get('mode', 'silent')
    if mode not in ('silent', 'play_one', 'keep_one'):
        raise ValueError('Mode audio inconnu')
    kind = options.get('format', 'mp4')
    if kind not in ('mp4', 'html'):
        raise ValueError('Format inconnu')
    if mode != 'silent' and not (folder / 'duo-cache/dialogue.wav').exists():
        separate(folder)
    audio = prepare_audio(folder, p, edit, mode, options.get('voice'))
    ident = uuid.uuid4().hex[:12]
    target = folder / 'exports' / f'impro-{ident}.mp4'
    target.parent.mkdir(exist_ok=True)
    from rendu_local import render
    staging = folder / 'taches' / f'export-{ident}.mp4'
    render(folder / 'original.mp4', staging, p, edit, audio, options)
    os.replace(staging, target)
    if kind == 'html':
        data = base64.b64encode(target.read_bytes()).decode('ascii')
        page = '<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>DoublageBasic — Impro</title><style>body{background:#101723;color:white;font:18px system-ui;margin:2em}video{width:100%;max-height:85vh}</style><h1>DoublageBasic — Impro</h1><video controls playsinline src="data:video/mp4;base64,' + data + '"></video><p>Repères : clignotement avant la parole, lumière fixe pendant. Plan en bas à gauche.</p></html>'
        temporary_html = folder / 'taches' / f'export-{ident}.html'
        temporary_html.write_text(page, encoding='utf-8')
        os.replace(temporary_html, target.with_suffix('.html'))
    print('Export terminé avec la révision ' + str(p['revision']), flush=True)


def main():
    folder = Path(sys.argv[1]).resolve()
    request = json.load(sys.stdin)
    os.environ['MPLCONFIGDIR'] = str(folder.parents[1] / 'cache/matplotlib')
    os.environ['XDG_CACHE_HOME'] = str(folder.parents[1] / 'cache')
    os.environ['HF_HOME'] = str(folder.parents[1] / 'cache/huggingface')
    if (folder.parents[1] / 'cache/huggingface/complete.marker').exists():
        os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TORCH_HOME'] = str(folder.parents[1] / 'cache/torch')
    action, options = request['action'], request.get('options', {})
    if action in ('analyze', 'resume'):
        analyze(folder, options, request.get('token'))
    elif action == 'separate':
        separate(folder)
    elif action == 'export':
        export(folder, options)
    elif action != 'refresh':
        raise ValueError('Action inconnue')

if __name__ == '__main__':
    main()
