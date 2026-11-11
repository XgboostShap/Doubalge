"""Extraction sourcée et découpage en trois parties sans perte de paragraphes."""
from pathlib import Path
import re


def split_three(blocks):
    if len(blocks) < 3:
        expanded = []
        for b in blocks:
            for sentence in re.split(r'(?<=[.!?])\s+', b['text']):
                if sentence.strip():
                    expanded.append({'page':b['page'], 'text':sentence.strip()})
        blocks = expanded
    if len(blocks) < 3:
        raise ValueError('Le document est trop court pour former trois parties non vides.')
    prefix = [0]
    for b in blocks:
        prefix.append(prefix[-1] + len(b['text']))
    first = min(range(1, len(blocks)-1), key=lambda i:abs(prefix[i]-prefix[-1]/3))
    second = min(range(first+1, len(blocks)), key=lambda i:abs(prefix[i]-2*prefix[-1]/3))
    return [blocks[:first], blocks[first:second], blocks[second:]]


def extract(path, identifier, name):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError(f'{name} est protégé par un mot de passe. Fournissez une copie lisible.')
    if len(reader.pages) > 1000:
        raise ValueError(f'{name} dépasse 1000 pages : choisissez un extrait.')
    blocks, empty = [], []
    for number, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or '').replace('\x00', '').strip()
        if not text:
            empty.append(number)
            continue
        # Les sauts de ligne PDF ne sont pas toujours des paragraphes : conserver
        # de petits blocs évite aussi d'envoyer une page géante au modèle.
        paragraphs = re.split(r'\n\s*\n', text)
        for paragraph in paragraphs:
            words = paragraph.split()
            for start in range(0, len(words), 250):
                piece = ' '.join(words[start:start+250])
                if piece:
                    blocks.append({'page':number, 'text':piece})
    if sum(len(b['text']) for b in blocks) < 100:
        raise ValueError(f'{name} ne contient pas assez de texte extractible. Un PDF scanné doit être passé en OCR auparavant.')
    parts = [{'number':i, 'blocks':part, 'pages':sorted({b['page'] for b in part})}
             for i, part in enumerate(split_three(blocks), 1)]
    return {'id':identifier, 'name':name, 'page_count':len(reader.pages), 'empty_pages':empty, 'parts':parts}


def fragments(blocks, max_chars=10000):
    current, size = [], 0
    for block in blocks:
        if current and size + len(block['text']) > max_chars:
            yield current
            current, size = [], 0
        current.append(block)
        size += len(block['text'])
    if current:
        yield current
