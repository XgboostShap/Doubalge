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


def ass_time(seconds):
    cs = round(seconds * 100)
    return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'


def cues(edits, path):
    text = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n'
            '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
            'Style: Default,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,3,2,0,7,12,12,12,1\n'
            '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    def event(a, b, label, position):
        nonlocal text
        if b > a:
            text += f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{{\\pos(12,{position})}}{label}\n'
    for row, character in enumerate(c for c in edits['characters'] if c['id'] in edits['audioMix']['removedCharacters']):
        label = ''.join(c for c in character['label'] if c not in '{}\\\r\n')[:60]
        ranges = sorted((i['start'], i['end']) for i in edits['intervals'] if i['character'] == character['id'])
        # Balayage des débuts/fins : un seul repère par voix, même en chevauchement.
        changes = {}
        for start, end in ranges:
            for instant, active_delta, upcoming_delta in [(max(0, start-1.5), 0, 1),
                                                          (start, 1, -1), (end, -1, 0)]:
                delta = changes.setdefault(instant, [0, 0])
                delta[0] += active_delta
                delta[1] += upcoming_delta
        points = sorted(changes)
        active = upcoming = 0
        for a, b in zip(points, points[1:]):
            active += changes[a][0]
            upcoming += changes[a][1]
            if active:
                event(a, b, f'{label} : À VOUS', 12+row*55)
            elif upcoming:
                event(a, b, f'{label} : bientôt', 12+row*55)
    for cut in edits['cuts']:
        event(max(0, cut['time']-.5), min(edits['duration'], cut['time']+.15), 'CHANGEMENT DE PLAN', 320)
    path.write_text(text, encoding='utf-8')


def render(document, request, directory, cancel, progress):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from commun import FFMPEG
    edits = valider_corrections(request['edits'], document['source_sha256'], document['duration'],
                               document['analysis_id'], {p['id'] for p in document['characters']})
    if len(edits['audioMix']['removedCharacters']) not in (1, 2):
        raise ValueError('Choisissez une ou deux voix à doubler.')
    if not document.get('duoAudio'):
        raise ValueError('Les pistes dialogue et ambiance sont nécessaires.')
    profile = PROFILES[request['profile']]
    directory = Path(directory).resolve()
    filters = subprocess.run([FFMPEG, '-hide_banner', '-filters'], capture_output=True, text=True).stdout
    if ' ass ' not in filters:
        raise RuntimeError('Ce FFmpeg ne dispose pas de libass pour les repères. Mettez imageio-ffmpeg à jour.')
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
    subtitles = directory / 'cues.ass'
    cues(edits, subtitles)
    width, height, bitrate, audio = profile
    output = directory / 'entrainement.mp4'
    command = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(video), '-i', str(mixed),
               '-map', '0:v:0', '-map', '1:a:0', '-vf',
               f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,ass=filename=cues.ass',
               '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
               '-b:v', f'{bitrate}k', '-maxrate', f'{bitrate}k', '-bufsize', f'{bitrate*2}k',
               '-c:a', 'aac', '-b:a', f'{audio}k', '-ar', '48000', '-ac', '2',
               '-t', str(edits['duration']), '-movflags', '+faststart', '-progress', 'pipe:1', str(output)]
    run(command, cancel, lambda n: progress(.15+.84*n), edits['duration'], cwd=directory)
    progress(1.)
    return output
