"""Reconstruit le gabarit autonome après une modification du CSS/HTML ou du JS."""
from pathlib import Path
import json


def assembler():
    root = Path(__file__).resolve().parent
    layout = (root / 'editor-layout.html').read_text(encoding='utf-8')
    script = (root / 'editor.js').read_text(encoding='utf-8') + '\n' + (root / 'mp4.js').read_text(encoding='utf-8')
    audio = (root / 'audio.js').read_text(encoding='utf-8')
    downloads = (root / 'downloads.js').read_text(encoding='utf-8')
    text = (layout + '<script id="editor-data" type="application/json">__EDITOR_DATA__</script>'
            + '<script>\n' + audio + '\n' + downloads + '\n' + script + '\n</script></body></html>')
    (root / 'templates' / 'editeur.html').write_text(text, encoding='utf-8')
    player = (root / 'player-layout.html').read_text(encoding='utf-8')
    script = (root / 'player.js').read_text(encoding='utf-8')
    (root / 'templates' / 'impro.html').write_text(
        player + '<script id="impro-data" type="application/json">__IMPRO_DATA__</script>'
        + '<script>\n' + audio + '\n' + script + '\n</script></body></html>', encoding='utf-8')
    public = json.dumps((root / 'public-screen.html').read_text(encoding='utf-8'), ensure_ascii=False).replace('<', '\\u003c')
    show_script = (root / 'show.js').read_text(encoding='utf-8').replace('__PUBLIC_TEMPLATE_JSON__', public)
    model = (root / 'show-model.js').read_text(encoding='utf-8')
    show = ((root / 'show-layout.html').read_text(encoding='utf-8')
            + '<script id="show-data" type="application/json">__SHOW_DATA__</script>'
            + '<script>\n' + audio + '\n' + model + '\n' + show_script + '\n</script></body></html>')
    (root / 'templates' / 'spectacle.html').write_text(show, encoding='utf-8')
    (root.parent / 'Spectacle.html').write_text(show.replace('__SHOW_DATA__', json.dumps({
        'schema': 'doublagebasic.show.v1', 'scenes': [], 'autoAdvance': False})), encoding='utf-8')


if __name__ == '__main__':
    assembler()
