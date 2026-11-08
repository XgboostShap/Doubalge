"""Rendu H.264 des repères avec FFmpeg et frames OpenCV."""
import subprocess
from commun import FFMPEG


def render(source, target, project, edit, audio, options):
    import cv2
    capture = cv2.VideoCapture(str(source))
    width, height = int(capture.get(3)), int(capture.get(4))
    if not capture.isOpened() or not width or not height:
        raise ValueError('Vidéo illisible')
    light = options.get('quality', 'light') == 'light'
    max_width = 480 if light else 1280
    width_out = min(width, max_width) // 2 * 2
    height_out = max(2, round(height * width_out / width) // 2 * 2)
    fps = 25
    command = [FFMPEG, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
               '-s', f'{width_out}x{height_out}', '-r', str(fps), '-i', '-']
    if audio:
        command += ['-i', str(audio)]
    command += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '29' if light else '22', '-pix_fmt', 'yuv420p']
    if audio:
        command += ['-c:a', 'aac', '-ac', '1' if light else '2', '-b:a', '64k' if light else '128k', '-shortest']
    command += ['-movflags', '+faststart', str(target)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    source_fps = capture.get(cv2.CAP_PROP_FPS) or 25
    voices = list(project['voices'])
    chosen = options.get('voice')
    shown = [v for v in voices if ((v == chosen) if options.get('mode') == 'play_one' else (v != chosen) if options.get('mode') == 'keep_one' else True)]
    # Affichage d'une ligne par voix à improviser, sans identité visuelle supposée.
    colors = [(60, 76, 231), (113, 204, 46), (219, 152, 52), (182, 89, 155), (15, 196, 241)]
    index, src_index, frame = 0, -1, None
    try:
        while index / fps < project['duration']:
            t = index / fps
            wanted = int(t * source_fps)
            while src_index < wanted:
                ok, candidate = capture.read()
                src_index += 1
                if not ok:
                    break
                frame = candidate
            if not ok or frame is None:
                break
            image = cv2.resize(frame, (width_out, height_out))
            for n, voice in enumerate(shown):
                relevant = [r for r in edit['intervals'] if r['character'] == voice]
                on = any(r['start'] <= t < r['end'] for r in relevant)
                before = any(r['start'] - 1.5 <= t < r['start'] for r in relevant)
                bright = on or (before and int(t * 6) % 2 == 0)
                color = colors[voices.index(voice) % len(colors)]
                color = color if bright else tuple(int(x * .28) for x in color)
                y = height_out - 22 - n * 25
                cv2.circle(image, (width_out - 22, y), 9, color, -1)
                label = 'V' + voice.split(':')[1]
                # V1 correspond à voice:0.
                label = 'V' + str(int(voice.split(':')[1]) + 1)
                cv2.putText(image, label, (width_out - 67, y + 5), cv2.FONT_HERSHEY_SIMPLEX, .45, (255,255,255), 1)
            cut = any(r['time'] - .5 <= t <= r['time'] + .15 for r in edit['cuts'])
            cv2.circle(image, (20, height_out - 22), 9, (255,255,255) if cut and int(t*8)%2==0 else (65,65,65), -1)
            process.stdin.write(image.tobytes())
            index += 1
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError('Échec du rendu FFmpeg')
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        capture.release()
