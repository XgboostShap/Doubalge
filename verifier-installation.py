"""Diagnostic réel des bibliothèques et du calcul CUDA ; aucune clé enregistrée."""
import argparse
import importlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-cuda', action='store_true')
    args = parser.parse_args()
    result = dict(python=platform.python_version(), system=platform.system(), machine=platform.machine(), cuda=False, modules={})
    for module in ('torch','torchaudio','numpy','pyannote.audio','cv2','PIL','imageio_ffmpeg','soundfile','scipy','demucs','yt_dlp'):
        loaded = importlib.import_module(module)
        result['modules'][module] = str(getattr(loaded, '__version__', 'import OK'))
    import torch
    if torch.cuda.is_available():
        try:
            x = torch.ones((256, 256), device='cuda')
            result['cuda'] = bool((x @ x).sum().item() > 0)
            result['gpu'] = torch.cuda.get_device_name()
        except Exception:
            result['cuda'] = False
    if args.require_cuda and not result['cuda']:
        print('Le calcul CUDA a échoué. Repli CPU requis.')
        return 2
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-version'], check=True, stdout=subprocess.DEVNULL)
    if os.name == 'nt':
        node = Path(__file__).parent / '.runtime/node/node.exe'
        result['node'] = subprocess.check_output([str(node), '--version'], text=True).strip()
    target = Path(__file__).parent / '.runtime/installation.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Diagnostic terminé. Calcul : ' + ('CUDA' if result['cuda'] else 'CPU'))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
