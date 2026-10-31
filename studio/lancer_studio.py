"""Analyse locale puis éditeur HTML autonome ; les modules historiques restent inchangés."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import wave
import webbrowser

from export_html import SCHEMA, construire_document, ecrire_json, empreinte, exporter, valider_corrections

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'projet' if (ROOT / 'projet' / 'commun.py').exists() else ROOT


def initialiser():
    os.environ.pop('HF_HUB_OFFLINE', None)
    for name, folder in {'HF_HOME': 'huggingface', 'PYANNOTE_CACHE': 'pyannote',
                         'MPLCONFIGDIR': 'matplotlib', 'TORCH_HOME': 'torch'}.items():
        path = ROOT / '.cache' / folder
        path.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault(name, str(path))
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PROJECT))


def lire_token():
    try:
        token = (ROOT / 'token_hf.txt').read_text(encoding='utf-8-sig').strip()
    except (OSError, UnicodeError) as error:
        raise RuntimeError('Créez token_hf.txt à côté de Lancer-studio.cmd, avec la clé Hugging Face.') from error
    if not token.startswith('hf_') or any(c.isspace() for c in token):
        raise RuntimeError('token_hf.txt doit contenir uniquement votre clé Hugging Face complète.')
    return token


def ffmpeg(arguments: list[str]):
    from commun import FFMPEG
    result = subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', *arguments],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError('FFmpeg : ' + result.stderr[-1500:])


def medias(video: Path, travail: Path):
    sound, muted = travail / 'video-editeur.mp4', travail / 'video-impro.mp4'
    if not sound.exists():
        temporary = travail / 'video-editeur.partial.mp4'
        ffmpeg(['-i', str(video), '-map', '0:v:0', '-map', '0:a:0?',
                '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2',
                '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast', '-crf', '23',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart', str(temporary)])
        temporary.replace(sound)
    if not muted.exists():
        temporary = travail / 'video-impro.partial.mp4'
        ffmpeg(['-i', str(sound), '-map', '0:v:0', '-c:v', 'copy', '-an',
                '-movflags', '+faststart', str(temporary)])
        temporary.replace(muted)
    return sound, muted


def forme_onde(wav: Path, count=1800):
    import numpy as np
    with wave.open(str(wav), 'rb') as audio:
        if audio.getsampwidth() != 2 or audio.getnchannels() != 1:
            raise ValueError('La forme d’onde nécessite l’extrait audio mono PCM 16 bits.')
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(float)
    if not samples.size:
        return [0.0, 0.0]
    peaks = [float(np.max(np.abs(part))) for part in np.array_split(samples, min(count, samples.size))]
    maximum = max(1, max(peaks))
    return [round(value / maximum, 4) for value in peaks]


def verifier_events(data: dict, duration: float):
    import math
    if not isinstance(data.get('events'), list) or len(data['events']) > 10000:
        raise ValueError('Choisissez la timeline.json du traitement, pas un JSON de corrections de l’éditeur.')
    events = []
    for event in data['events']:
        start, end, speaker = event.get('start'), event.get('end'), event.get('speaker')
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or type(speaker) is not int or speaker < 0
                or not 0 <= start < duration or not start < end <= duration + .1):
            raise ValueError('La timeline contient un passage invalide ou hors de cette vidéo.')
        events.append({'start': start, 'end': min(end, duration), 'speaker': speaker})
    return sorted(events, key=lambda event: (event['start'], event['end']))


def traiter(source: str, sortie: Path, timeline: Path | None = None, personnages=0,
            cpu=False, token=None, corrections: Path | None = None, separation=True):
    initialiser()
    from commun import duree_et_taille, est_url
    from telecharge import extrait_audio, telecharge
    from rendu import detecte_plans
    sortie = Path(sortie).resolve()
    sortie.mkdir(parents=True, exist_ok=True)
    travail = sortie / 'travail'
    travail.mkdir(exist_ok=True)
    if est_url(source):
        print('[source] Téléchargement de la vidéo…', flush=True)
        video = Path(telecharge(source, str(travail))).resolve()
    else:
        video = Path(source).expanduser().resolve(strict=True)
    digest = empreinte(video)
    if (sortie / 'timeline.json').exists():
        previous = json.loads((sortie / 'timeline.json').read_text(encoding='utf-8-sig'))
        if previous.get('source_sha256') != digest:
            raise ValueError('Ce dossier de résultat appartient à une autre vidéo. Choisissez un nouveau dossier.')
    marker = travail / 'source.sha256'
    if marker.exists() and marker.read_text(encoding='utf-8').strip() != digest:
        raise ValueError('Ce dossier de travail contient une autre vidéo. Choisissez un nouveau dossier.')
    if not marker.exists() and (travail / 'audio.wav').exists() and not (sortie / 'timeline.json').exists():
        raise ValueError('Un ancien dossier de travail sans identification est présent. Choisissez un nouveau dossier.')
    marker.write_text(digest, encoding='utf-8')
    duration, _, _ = duree_et_taille(str(video))
    import cv2
    capture = cv2.VideoCapture(str(video))
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    capture.release()
    wav = travail / 'audio.wav'
    if not wav.exists():
        extrait_audio(str(video), str(wav))
    print(f'[source] {duration:.2f} secondes ; {fps:.2f} images/s.', flush=True)

    saved = json.loads(Path(timeline).read_text(encoding='utf-8-sig')) if timeline else None
    corrected = json.loads(Path(corrections).read_text(encoding='utf-8-sig')) if corrections else None
    if saved and saved.get('schema') == SCHEMA and 'intervals' in saved:
        if corrected is not None:
            raise ValueError('Choisissez la timeline brute dans le premier champ, ou un seul JSON corrigé.')
        corrected, saved = saved, None
    if corrected is None and saved:
        corrected = saved.get('corrections')
    if corrected is not None:
        known = {f"voice:{e['speaker']}" for e in saved['events']} if saved else None
        if saved and (saved.get('corrections') or {}).get('characters'):
            known.update(p['id'] for p in saved['corrections']['characters'])
        corrected = valider_corrections(corrected, digest, duration,
                                       saved.get('analysis_id') if saved else None, known)
    if saved is not None:
        if saved.get('source_sha256'):
            if saved['source_sha256'] != digest:
                raise ValueError('La timeline appartient à une autre vidéo.')
        elif saved.get('source') != source:
            raise ValueError('Cette ancienne timeline doit avoir exactement la même source vidéo.')
        if saved.get('duration') is not None and abs(float(saved['duration']) - duration) > .12:
            raise ValueError('La durée de la timeline ne correspond pas à cette vidéo.')
        events = verifier_events(saved, duration)
        cuts = saved.get('cuts', [])
        print('[analyse] Timeline existante réutilisée.', flush=True)
    elif corrected is not None:
        events = [{'start': i['start'], 'end': i['end'], 'speaker': int(i['character'].split(':')[1])}
                  for i in corrected['intervals'] if i['character'] is not None]
        cuts = [c['time'] for c in corrected['cuts']]
        print('[analyse] Corrections manuelles réutilisées ; aucune nouvelle attribution IA.', flush=True)
    else:
        import torch
        from pyannote.audio import Pipeline
        from pyannote.audio.core.task import Problem, Resolution, Specifications
        from diarisation import diarise_pyannote
        torch.set_num_threads(min(os.cpu_count() or 1, 4))
        gpu = not cpu and torch.cuda.is_available()
        print('[analyse] ' + (torch.cuda.get_device_name(0) if gpu else 'CPU'), flush=True)
        original = Pipeline.from_pretrained.__func__

        def charger(cls, *args, **kwargs):
            pipeline = original(cls, *args, **kwargs)
            if pipeline is not None and gpu:
                pipeline.to(torch.device('cuda'))
            return pipeline

        Pipeline.from_pretrained = classmethod(charger)
        try:
            with torch.serialization.safe_globals([
                torch.torch_version.TorchVersion, Problem, Resolution, Specifications
            ]):
                events = diarise_pyannote(str(wav), token if token is not None else lire_token(), personnages)
        finally:
            Pipeline.from_pretrained = classmethod(original)
        events = verifier_events({'events': events}, duration)
        # Sauvegarde avant les étapes suivantes : une erreur d’export ne perd plus l’analyse audio.
        ecrire_json(sortie / 'timeline.json', {'source': source, 'source_sha256': digest,
                    'duration': duration, 'events': events, 'cuts': [], 'plans_a_recalculer': True})
        cuts = detecte_plans(str(video))
    if saved and saved.get('plans_a_recalculer'):
        cuts = detecte_plans(str(video))
    analysis = {'analysis_id': corrected['analysis_id'] if corrected else
                (saved.get('analysis_id', uuid.uuid4().hex) if saved else uuid.uuid4().hex),
                'source': source, 'source_sha256': digest,
                'duration': duration, 'fps': fps, 'events': events, 'cuts': cuts}
    if corrected is not None:
        analysis['corrections'] = corrected
        analysis['corrected_only'] = saved is None or saved.get('corrected_only', False)
    ecrire_json(sortie / 'timeline.json', analysis)
    print(f'[analyse] {len(set(e["speaker"] for e in events))} voix ; {len(events)} passages ; {len(cuts)} plans.', flush=True)
    print('[export] Préparation des vidéos de l’éditeur et du lecteur…', flush=True)
    sound, muted = medias(video, travail)
    pistes = None
    if separation:
        from separation_audio import separer
        pistes = separer(video, travail, duration, digest, ffmpeg, cpu)
    document = construire_document(analysis, forme_onde(wav), sound, muted, pistes)
    editor, player = exporter(document, sortie)
    print(f'[terminé] Éditeur : {editor}\n[terminé] Lecteur impro : {player}', flush=True)
    return editor, player


def choisir():
    import tkinter as tk
    from tkinter import filedialog, messagebox
    window = tk.Tk()
    window.title('Doubalge — préparer une scène')
    window.configure(bg='#11151d')
    window.resizable(False, False)
    source, timeline, corrections = tk.StringVar(), tk.StringVar(), tk.StringVar()
    separation = tk.BooleanVar(value=True)
    personnages = tk.IntVar(value=0)
    result = []

    def fichier(variable, title, extensions):
        path = filedialog.askopenfilename(parent=window, title=title, filetypes=extensions)
        if path:
            variable.set(path)

    def lancer():
        if not source.get().strip():
            messagebox.showerror('Source manquante', 'Choisissez une vidéo ou collez une URL YouTube.', parent=window)
            return
        result.append((source.get().strip(), Path(timeline.get()) if timeline.get() else None,
                       Path(corrections.get()) if corrections.get() else None,
                       separation.get(), personnages.get()))
        window.destroy()

    tk.Label(window, text='Préparer une scène', bg='#11151d', fg='white', font=('Segoe UI', 17, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', padx=20, pady=18)
    tk.Label(window, text='Vidéo sur le PC ou URL YouTube', bg='#11151d', fg='#aab8cc').grid(row=1, column=0, columnspan=2, sticky='w', padx=20)
    tk.Entry(window, textvariable=source, width=65).grid(row=2, column=0, padx=(20, 8), pady=8)
    tk.Button(window, text='Choisir une vidéo', command=lambda: fichier(source, 'Vidéo', [('Vidéos', '*.mp4 *.mkv *.mov *.avi *.webm'), ('Tous', '*.*')])).grid(row=2, column=1, padx=(0, 20))
    tk.Label(window, text='Timeline déjà calculée (facultatif, pour éviter une nouvelle analyse)', bg='#11151d', fg='#aab8cc').grid(row=3, column=0, columnspan=2, sticky='w', padx=20, pady=(12, 0))
    tk.Entry(window, textvariable=timeline, width=65).grid(row=4, column=0, padx=(20, 8), pady=8)
    tk.Button(window, text='Choisir le JSON', command=lambda: fichier(timeline, 'Timeline du traitement', [('Timeline', '*.json')])).grid(row=4, column=1, padx=(0, 20))
    tk.Label(window, text='Corrections manuelles (prioritaires, sans nouvelle attribution IA)', bg='#11151d', fg='#aab8cc').grid(row=5, column=0, columnspan=2, sticky='w', padx=20, pady=(12, 0))
    tk.Entry(window, textvariable=corrections, width=65).grid(row=6, column=0, padx=(20, 8), pady=8)
    tk.Button(window, text='Choisir les corrections', command=lambda: fichier(corrections, 'Corrections de l’éditeur', [('JSON corrigé', '*.json')])).grid(row=6, column=1, padx=(0, 20))
    tk.Checkbutton(window, text='Préparer le choix des voix et de l’ambiance', variable=separation,
                   bg='#11151d', fg='white', selectcolor='#252e40', activebackground='#11151d',
                   activeforeground='white').grid(row=7, column=0, columnspan=2, sticky='w', padx=20, pady=8)
    tk.Label(window, text='Nombre de voix attendu (0 = automatique, ignoré si JSON fourni)', bg='#11151d', fg='#aab8cc').grid(row=8, column=0, sticky='w', padx=20)
    tk.Spinbox(window, from_=0, to=20, textvariable=personnages, width=5).grid(row=8, column=1, sticky='w')
    tk.Label(window, text='L’éditeur s’ouvrira dans le navigateur après la préparation.', bg='#11151d', fg='#aab8cc').grid(row=9, column=0, columnspan=2, sticky='w', padx=20, pady=8)
    tk.Button(window, text='Créer l’éditeur', bg='#2967b2', fg='white', command=lancer).grid(row=10, column=0, columnspan=2, sticky='e', padx=20, pady=(8, 20))
    window.mainloop()
    return result[0] if result else None


def main():
    parser = argparse.ArgumentParser(description='Créer l’éditeur et le lecteur impro HTML sur votre PC.')
    parser.add_argument('--video')
    parser.add_argument('--timeline', type=Path)
    parser.add_argument('--corrections', type=Path)
    parser.add_argument('--sans-audio-separe', action='store_true')
    parser.add_argument('--sortie', type=Path)
    parser.add_argument('--cpu', action='store_true')
    parser.add_argument('--personnages', type=int, default=0)
    parser.add_argument('--sans-ouvrir', action='store_true')
    args = parser.parse_args()
    if not args.video:
        selected = choisir()
        if selected is None:
            return
        args.video, args.timeline, args.corrections, separation, args.personnages = selected
        args.sans_audio_separe = not separation
    output = args.sortie or ROOT / 'resultats' / ('edition-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    editor, _ = traiter(args.video, output, args.timeline, args.personnages, args.cpu,
                        corrections=args.corrections, separation=not args.sans_audio_separe)
    if not args.sans_ouvrir:
        webbrowser.open(editor.as_uri())


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'\n[erreur] {error}', file=sys.stderr)
        sys.exit(1)
