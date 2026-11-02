"""Rendu local H.264/AAC, sans analyse IA ni service distant."""
from __future__ import annotations

import base64
import math
from pathlib import Path
import subprocess
import threading
import wave

from export_html import valider_corrections

PROFILES = {'mail': (640, 360, 450, 64), 'standard': (1280, 720, 1800, 96)}


class Cancelled(Exception):
    pass


def run(command, cancel, progress=None, duration=1, cwd=None):
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding='utf-8', errors='replace', cwd=cwd) as process:
        def stop():
            while process.poll() is None:
                if cancel.wait(.1):
                    if process.poll() is None:
                        process.terminate()
                    return
        watcher = threading.Thread(target=stop, daemon=True)
        watcher.start()
        tail = []
        for line in process.stdout:
            tail = (tail + [line])[-20:]
            if progress and line.startswith('out_time_us='):
                try:
                    progress(min(.99, float(line.split('=')[1]) / 1e6 / duration))
                except ValueError:
                    pass
        code = process.wait()
        watcher.join()
        if cancel.is_set():
            raise Cancelled()
        if code:
            raise RuntimeError('FFmpeg : ' + ''.join(tail)[-2000:])


def write_media(value, path):
    if not isinstance(value, str) or ';base64,' not in value or not value.startswith('data:'):
        raise ValueError('Média intégré manquant.')
    path.write_bytes(base64.b64decode(value.split(',', 1)[1], validate=True))


def union(ranges):
    result = []
    for a, b in sorted(ranges):
        if b <= a:
            continue
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return result


def windows(intervals, mix, duration):
    # Même règle que DoubalgeAudio.windows : une voix retirée prime au chevauchement.
    removed = set(mix['removedCharacters'])
    wanted = [[0, duration]] if mix['keepUnknown'] else union(
        (i['start'], i['end']) for i in intervals
        if i['character'] is not None and i['character'] not in removed)
    blocked = union((i['start'], i['end']) for i in intervals
                    if (i['character'] in removed if i['character'] is not None else not mix['keepUnknown']))
    result, first = [], 0
    for a, b in wanted:
        cursor = a
        while first < len(blocked) and blocked[first][1] <= cursor:
            first += 1
        for left, right in blocked[first:]:
            if left >= b:
                break
            if left > cursor:
                result.append([cursor, min(left, b)])
            cursor = max(cursor, right)
            if cursor >= b:
                break
        if cursor < b:
            result.append([cursor, b])
    return result


def mix_audio(dialogue, background, output, intervals, mix, duration, cancel):
    import numpy as np
    ranges = windows(intervals, mix, duration)
    with wave.open(str(dialogue), 'rb') as voice, wave.open(str(background), 'rb') as bed, wave.open(str(output), 'wb') as dest:
        rate = voice.getframerate()
        dest.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        offset, count = 0, math.ceil(duration * rate)
        while offset < count:
            if cancel.is_set():
                raise Cancelled()
            n = min(8192, count - offset)
            def samples(source):
                raw = np.frombuffer(source.readframes(n), dtype='<i2').astype(np.float64)
                return np.pad(raw, (0, n * 2 - len(raw))).reshape(n, 2)
            v, b = samples(voice), samples(bed)
            times = (np.arange(n) + offset) / rate
            gain = np.zeros(n)
            for start, end in ranges:
                if end < times[0] or start > times[-1]:
                    continue
                fade = min(.01, (end - start) / 2)
                gain = np.maximum(gain, np.clip(np.minimum((times-start)/fade, (end-times)/fade), 0, 1))
            mixed = v * gain[:, None] + (b if mix['keepAmbience'] else 0)
            dest.writeframes(np.clip(mixed, -32768, 32767).astype('<i2').tobytes())
            offset += n


def render(document, request, directory, cancel, progress):
    import sys
    root = Path(__file__).resolve().parent.parent
    modules = root/'projet' if (root/'projet'/'commun.py').exists() else root
    sys.path.insert(0, str(modules))
    from commun import FFMPEG
    edits = valider_corrections(request['edits'], document['source_sha256'], document['duration'],
                               document['analysis_id'], {p['id'] for p in document['characters']})
    if len(edits['audioMix']['removedCharacters']) not in (1, 2):
        raise ValueError('Choisissez une ou deux voix à doubler.')
    if not document.get('duoAudio'):
        raise ValueError('Les pistes dialogue et ambiance sont nécessaires.')
    profile = PROFILES[request['profile']]
    directory = Path(directory).resolve()
    progress(.01)
    video = directory / 'source.mp4'
    write_media(document.get('improMedia', document['media']), video)
    for name, key in [('dialogue', 'dialogue'), ('background', 'background')]:
        source, wav = directory / (name+'.m4a'), directory / (name+'.wav')
        write_media(document['duoAudio'][key], source)
        run([FFMPEG, '-v', 'error', '-y', '-i', str(source), '-ac', '2', '-ar', '24000', '-c:a', 'pcm_s16le', str(wav)], cancel)
    progress(.08)
    mixed = directory / 'mix.wav'
    mix_audio(directory/'dialogue.wav', directory/'background.wav', mixed, edits['intervals'],
              edits['audioMix'], edits['duration'], cancel)
    from mp4_visuals import encode_video
    encode_video(document, edits, video, mixed, directory/'entrainement.mp4', profile,
                 cancel, progress, FFMPEG)
    output = directory/'entrainement.mp4'
    progress(1.)
    return output
