"""Remplace l’interface d’un éditeur autonome, sans réanalyser ses médias."""
from __future__ import annotations

import argparse
import json
import re
import sys
import webbrowser
from pathlib import Path

from assembler_editeur import assembler
from export_html import SCHEMA, TEMPLATES, serialiser_html, valider_corrections


def actualiser(source: Path, corrections: Path | None = None) -> Path:
    source = source.resolve()
    text = source.read_text(encoding='utf-8-sig')
    match = re.search(r'<script\b[^>]*\bid=["\']editor-data["\'][^>]*>(.*?)</script\s*>', text, re.S | re.I)
    if not match:
        raise ValueError('Choisissez le fichier OSS-editeur.html contenant la vidéo et ses repères.')
    document = json.loads(match[1])
    if document.get('schema') != SCHEMA or not all(k in document for k in (
            'initial', 'initialCuts', 'automatic', 'characters', 'media', 'peaks')):
        raise ValueError('Ce fichier n’est pas un éditeur compatible.')
    if corrections:
        edits = valider_corrections(json.loads(corrections.read_text(encoding='utf-8-sig')),
                                   document['source_sha256'], document['duration'],
                                   document['analysis_id'], {p['id'] for p in document['characters']})
        document['initial'] = edits['intervals']
        document['initialCuts'] = edits['cuts']
        if 'audioMix' in edits:
            document['audioMix'] = edits['audioMix']
        names = {p['id']: p for p in edits.get('characters', [])}
        document['characters'] = [{**p, **names.get(p['id'], {})} for p in document['characters']]
    assembler()
    document['improTemplate'] = (TEMPLATES / 'impro.html').read_text(encoding='utf-8')
    document['showTemplate'] = (TEMPLATES / 'spectacle.html').read_text(encoding='utf-8')
    html = (TEMPLATES / 'editeur.html').read_text(encoding='utf-8').replace('__EDITOR_DATA__', serialiser_html(document))
    stem = source.stem + '-actualise'
    output = source.with_name(stem + '.html')
    suffix = 2
    while output.exists():
        output = source.with_name(f'{stem}-{suffix}.html')
        suffix += 1
    with output.open('x', encoding='utf-8') as stream:
        stream.write(html)
    return output


def choisir():
    import tkinter as tk
    from tkinter import filedialog, messagebox
    window = tk.Tk()
    window.title('Actualiser un éditeur existant')
    window.resizable(False, False)
    source, corrections = tk.StringVar(), tk.StringVar()

    def fichier(variable, title, pattern):
        path = filedialog.askopenfilename(parent=window, title=title, filetypes=[(title, pattern)])
        if path:
            variable.set(path)

    def lancer():
        try:
            if not source.get():
                raise ValueError('Choisissez votre fichier éditeur HTML.')
            result = actualiser(Path(source.get()), Path(corrections.get()) if corrections.get() else None)
            messagebox.showinfo('Éditeur actualisé', f'Nouveau fichier :\n{result}\n\nL’original est conservé.', parent=window)
            webbrowser.open(result.as_uri())
            window.destroy()
        except Exception as error:
            messagebox.showerror('Actualisation impossible', str(error), parent=window)

    tk.Label(window, text='Mettre à jour l’interface sans refaire l’analyse', font=('Segoe UI', 13, 'bold')).grid(row=0, column=0, columnspan=2, padx=18, pady=15)
    tk.Label(window, text='Enregistrez d’abord vos corrections JSON dans l’ancien éditeur.').grid(row=1, column=0, columnspan=2, padx=18, sticky='w')
    for row, variable, title, pattern in [(2, source, 'Éditeur HTML', '*.html'), (4, corrections, 'Corrections JSON (facultatif)', '*.json')]:
        tk.Label(window, text=title).grid(row=row, column=0, columnspan=2, padx=18, pady=(12, 2), sticky='w')
        tk.Entry(window, textvariable=variable, width=65).grid(row=row + 1, column=0, padx=(18, 8), pady=5)
        tk.Button(window, text='Choisir', command=lambda v=variable, t=title, p=pattern: fichier(v, t, p)).grid(row=row + 1, column=1, padx=(0, 18))
    tk.Button(window, text='Créer le nouvel éditeur', command=lancer).grid(row=6, column=0, columnspan=2, sticky='e', padx=18, pady=18)
    window.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('editeur', type=Path, nargs='?')
    parser.add_argument('--corrections', type=Path)
    parser.add_argument('--sans-ouvrir', action='store_true')
    args = parser.parse_args()
    if not args.editeur:
        choisir()
        return
    output = actualiser(args.editeur, args.corrections)
    print(f'Éditeur actualisé : {output}')
    if not args.sans_ouvrir:
        webbrowser.open(output.as_uri())


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'[erreur] {error}', file=sys.stderr)
        sys.exit(1)
