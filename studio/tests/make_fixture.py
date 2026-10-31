"""Vidéo synthétique et timeline connue pour tester l'édition sans modèle réseau."""
from pathlib import Path
import sys

STUDIO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDIO))
from lancer_studio import initialiser, ffmpeg, forme_onde, medias
from export_html import construire_document, empreinte, exporter


def create(directory):
    initialiser()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / 'source.mp4'
    ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=25',
            '-f', 'lavfi', '-i', 'aevalsrc=0.2*sin(2*PI*110*t)+0.2*sin(2*PI*440*t):s=24000:d=3',
            '-t', '3', '-c:v', 'libx264', '-threads', '2', '-c:a', 'aac', str(source)])
    wav = directory / 'audio.wav'
    ffmpeg(['-i', str(source), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(wav)])
    editor, muted = medias(source, directory)
    data = {'analysis_id': 'test-editeur', 'source_sha256': empreinte(source), 'duration': 3,
            'fps': 25, 'cuts': [.8, 1.8, 2.55], 'events': [
                {'start': .1, 'end': .6, 'speaker': 0},
                {'start': .7, 'end': 1.2, 'speaker': 0},
                {'start': .8, 'end': 1.15, 'speaker': 3},
                {'start': 1.35, 'end': 2.1, 'speaker': 1},
                {'start': 2.25, 'end': 2.8, 'speaker': 2},
            ]}
    for name, frequency in [('dialogue', 440), ('ambiance', 110)]:
        ffmpeg(['-f', 'lavfi', '-i', f'aevalsrc=0.2*sin(2*PI*{frequency}*t):s=24000:d=3',
                '-c:a', 'aac', '-b:a', '96k', str(directory / (name + '.m4a'))])
    document = construire_document(data, forme_onde(wav), editor, muted,
                                    (directory / 'dialogue.m4a', directory / 'ambiance.m4a'))
    return exporter(document, directory)


if __name__ == '__main__':
    print(create(sys.argv[1])[0])
