"""Vignettes du lecteur impro, dessinées localement dans les images du MP4."""
from __future__ import annotations

import base64
from io import BytesIO
import math
import os
from pathlib import Path


def portrait_state(intervals, identifier, t, removed):
    active = [i for i in intervals if i['character'] == identifier and i['start'] <= t < i['end']]
    soon = not active and any(i['character'] == identifier and i['start']-1.5 <= t < i['start'] for i in intervals)
    role = 'À vous' if identifier in removed else 'Film'
    caption = role + (' ?' if any(not i['reviewed'] for i in active) else '') if active else role + ' · Bientôt' if soon else None
    return (1. if active or soon and t % .5 < .25 else .35), caption


def plan_state(cuts, t):
    next_cut = next((c for c in cuts if t < c['time']+.25), None)
    if next_cut is None:
        return None, 0, ''
    active = next_cut['time'] <= t < next_cut['time']+.25
    soon = next_cut['time']-.5 <= t < next_cut['time']
    opacity = 1. if active or soon and t % .5 < .25 else .35
    return next_cut, opacity, 'Changement de plan' if active else 'Plan imminent' if soon else 'Prochain plan'


def font(size):
    from PIL import ImageFont
    for name in [str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/'segoeui.ttf'),
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'Arial.ttf']:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


class Visuals:
    def __init__(self, document, edits, width, height):
        from PIL import Image, ImageDraw, ImageOps
        self.width, self.height = width, height
        self.intervals, self.cuts = edits['intervals'], sorted(edits['cuts'], key=lambda c: c['time'])
        self.removed = set(edits['audioMix']['removedCharacters'])
        original = {p['id']: p for p in document['characters']}
        self.people = [{**original[p['id']], **p} for p in edits['characters']]
        self.audio_only = all(not p.get('photo') for p in self.people)
        mobile = width <= 650
        self.bottom = 48 if mobile else 70
        self.gap, self.border = (5 if self.audio_only else 7), 3
        size = 50 if mobile else round(min(85 if self.audio_only else 115, max(48 if self.audio_only else 58, width*(.06 if self.audio_only else .08))))
        # Les très nombreuses voix doivent rester dans l'image.
        available = width*.70 if self.audio_only else height-self.bottom-12
        self.size = max(12, min(size, int((available-self.gap*max(0,len(self.people)-1))/max(1,len(self.people)))))
        self.caption_font = font(10 if mobile else max(10, min(14, round(width*.01))))
        self.tiles = []
        for index, person in enumerate(self.people):
            tile = Image.new('RGB', (self.size, self.size), person['color'])
            if person.get('photo'):
                with Image.open(BytesIO(base64.b64decode(person['photo'], validate=True))) as photo:
                    tile.paste(ImageOps.fit(photo.convert('RGB'), (self.size-6, self.size-6)), (3,3))
            else:
                draw = ImageDraw.Draw(tile)
                draw.text((self.size/2, self.size/2), 'V'+str(index+1), font=font(min(30, self.size//2)), anchor='mm', fill='white', stroke_width=1)
            self.tiles.append(tile)
        self.preview_time = None
        self.preview_image = None

    def caption(self, tile, text):
        from PIL import ImageDraw
        draw = ImageDraw.Draw(tile)
        # La légende peut occuper plusieurs lignes, comme le span HTML du lecteur.
        lines, line = [], ''
        for word in text.split():
            candidate = (line+' '+word).strip()
            if line and draw.textlength(candidate, font=self.caption_font) > tile.width-4:
                lines.append(line)
                line = ''
            while draw.textlength(word, font=self.caption_font) > tile.width-4:
                part = word
                while len(part)>1 and draw.textlength(part, font=self.caption_font) > tile.width-4:
                    part = part[:-1]
                lines.append(part)
                word = word[len(part):]
            line = (line+' '+word).strip()
        if line:
            lines.append(line)
        lines = lines[:3]
        h = min(tile.height, (self.caption_font.size+2)*len(lines)+6)
        draw.rectangle((0,tile.height-h,tile.width,tile.height), fill='#10141b')
        for n, line in enumerate(lines):
            draw.text((tile.width/2,tile.height-h+4+n*(self.caption_font.size+2)), line, font=self.caption_font, anchor='mt', fill='#eef2f9')

    def draw(self, frame, t, preview):
        import cv2
        from PIL import Image, ImageDraw, ImageOps
        image = Image.new('RGB', (self.width,self.height))
        source = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        source = ImageOps.contain(source, (self.width,self.height))
        image.paste(source, ((self.width-source.width)//2,(self.height-source.height)//2))
        right = round(self.width*.015)
        count = len(self.people)
        for n, (person, original) in enumerate(zip(self.people,self.tiles)):
            opacity, caption = portrait_state(self.intervals, person['id'], t, self.removed)
            role = 'À vous' if person['id'] in self.removed else 'Film'
            tile = original.copy()
            self.caption(tile, caption or role+' · '+person['label'])
            x = self.width-right-(count-n)*(self.size+self.gap)+self.gap if self.audio_only else self.width-right-self.size
            y = self.height-self.bottom-self.size if self.audio_only else self.height-self.bottom-self.size-n*(self.size+self.gap)
            self.paste(image, tile, (x,y), opacity)
        cut, opacity, caption = plan_state(self.cuts, t)
        if cut:
            if self.preview_time != cut['time']:
                frame_index = min(max(0,int(preview.get(cv2.CAP_PROP_FRAME_COUNT))-1), int((cut['time']+.08)*preview.get(cv2.CAP_PROP_FPS)))
                preview.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, next_frame = preview.read()
                if not ok:
                    raise RuntimeError('Impossible de lire la vignette du prochain plan.')
                self.preview_image = Image.fromarray(cv2.cvtColor(next_frame,cv2.COLOR_BGR2RGB))
                self.preview_time = cut['time']
            width = 85 if self.width <= 650 else round(min(175,max(90,self.width*.12)))
            tile = Image.new('RGB',(width,round(width*9/16)),'white')
            tile.paste(ImageOps.fit(self.preview_image,(tile.width-6,tile.height-6)),(3,3))
            self.caption(tile,caption)
            self.paste(image,tile,(right,self.height-self.bottom-tile.height),opacity)
        if any(i['character'] is None and i['start'] <= t < i['end'] for i in self.intervals):
            draw = ImageDraw.Draw(image)
            text = 'Voix non attribuée ?'
            box = draw.textbbox((0,0),text,font=self.caption_font)
            x = max(0,self.width-right-self.size-(box[2]+25))
            y = self.height-self.bottom-25
            draw.rectangle((x,y,x+box[2]+14,y+22),fill='#1e2635')
            draw.text((x+7,y+3),text,font=self.caption_font,fill='#ffe044')
        return image.tobytes()

    @staticmethod
    def paste(image, tile, position, opacity):
        from PIL import Image
        image.paste(tile, position, Image.new('L',tile.size,round(opacity*255)))


def encode_video(document, edits, source, mixed, output, profile, cancel, progress, ffmpeg):
    import cv2
    import subprocess
    import threading
    from export_mp4 import Cancelled
    width,height,bitrate,audio = profile
    capture, preview = cv2.VideoCapture(str(source)), cv2.VideoCapture(str(source))
    if not capture.isOpened() or not preview.isOpened():
        capture.release(); preview.release()
        raise RuntimeError('Impossible de lire la vidéo pour dessiner les vignettes.')
    native_fps = capture.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(native_fps) or native_fps <= 0:
        native_fps = 25.
    fps = min(60.,max(25.,native_fps))
    process = None
    watcher = None
    try:
        visuals = Visuals(document,edits,width,height)
        visuals.duration = edits['duration']
        command = [ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
                   '-s',f'{width}x{height}','-r',str(fps),'-i','pipe:0','-i',str(mixed),
                   '-map','0:v:0','-map','1:a:0','-c:v','libx264','-threads','2','-preset','veryfast',
                   '-pix_fmt','yuv420p','-b:v',f'{bitrate}k','-maxrate',f'{bitrate}k','-bufsize',f'{bitrate*2}k',
                   '-c:a','aac','-b:a',f'{audio}k','-ar','48000','-ac','2','-t',str(edits['duration']),
                   '-movflags','+faststart',str(output)]
        with output.with_suffix('.log').open('w+b') as log:
            process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
            def stop():
                while process.poll() is None:
                    if cancel.wait(.1):
                        if process.poll() is None:
                            process.terminate()
                        return
            watcher = threading.Thread(target=stop,daemon=True)
            watcher.start()
            current,frame = -1,None
            try:
                total = math.ceil(edits['duration']*fps)
                for n in range(total):
                    if cancel.is_set():
                        raise Cancelled()
                    t = n/fps
                    target = math.floor(t*native_fps+1e-6)
                    while current < target:
                        ok, candidate = capture.read()
                        if not ok:
                            # Une dernière image est répétée uniquement pour un arrondi de durée.
                            if frame is None or t < edits['duration']-.15:
                                raise RuntimeError('La vidéo se termine avant la durée corrigée.')
                            break
                        frame = candidate
                        current += 1
                    process.stdin.write(visuals.draw(frame,t,preview))
                    if n % 10 == 0:
                        progress(.15+.84*(n+1)/total)
                process.stdin.close()
                code = process.wait()
                if cancel.is_set():
                    raise Cancelled()
                if code:
                    log.seek(0)
                    raise RuntimeError('FFmpeg : '+log.read().decode('utf-8',errors='replace')[-2000:])
            except BrokenPipeError as error:
                if cancel.is_set():
                    raise Cancelled() from error
                log.seek(0)
                raise RuntimeError('FFmpeg : '+log.read().decode('utf-8',errors='replace')[-2000:]) from error
    finally:
        capture.release(); preview.release()
        if process:
            if process.poll() is None:
                process.terminate()
            process.wait()
            try:
                process.stdin.close()
            except OSError:
                pass
        if watcher:
            watcher.join()
