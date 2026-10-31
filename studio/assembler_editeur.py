"""Reconstruit le gabarit autonome après une modification du CSS/HTML ou du JS."""
from pathlib import Path


def assembler():
    root = Path(__file__).resolve().parent
    layout = (root / 'editor-layout.html').read_text(encoding='utf-8')
    script = (root / 'editor.js').read_text(encoding='utf-8')
    audio = (root / 'audio.js').read_text(encoding='utf-8')
    text = (layout + '<script id="editor-data" type="application/json">__EDITOR_DATA__</script>'
            + '<script>\n' + audio + '\n' + script + '\n</script></body></html>')
    (root / 'templates' / 'editeur.html').write_text(text, encoding='utf-8')
    player = (root / 'player-layout.html').read_text(encoding='utf-8')
    script = (root / 'player.js').read_text(encoding='utf-8')
    (root / 'templates' / 'impro.html').write_text(
        player + '<script id="impro-data" type="application/json">__IMPRO_DATA__</script>'
        + '<script>\n' + audio + '\n' + script + '\n</script></body></html>', encoding='utf-8')


if __name__ == '__main__':
    assembler()
