"""Erreurs de validation : séparer le format, les sources et les ressources."""
import json


class SourceIssue(ValueError):
    def __init__(self, message, category='source'):
        super().__init__(message)
        self.category = category


class ReviewRequired(RuntimeError):
    def __init__(self, step, count):
        self.step, self.count = step, count
        super().__init__(f'{count} passage(s) à vérifier à l’étape {step}. '
                         'Les parties validées sont conservées ; ouvrez les vérifications regroupées.')


class DownloadConsentRequired(ValueError):
    pass


def category(error):
    """Conserver la cause précise, y compris après encapsulation par le client."""
    chain = []
    while error is not None and id(error) not in {id(e) for e in chain}:
        chain.append(error)
        error = error.__cause__
    for item in reversed(chain):
        if isinstance(item, SourceIssue):
            return item.category
        name = type(item).__name__
        if name == 'AcronymExpansionError': return 'terminology'
        if name == 'WordCountError': return 'length'
        if name in ('RepetitionError', 'ResponseLimitError', 'RequestBudgetError'): return 'generation'
        if isinstance(item, json.JSONDecodeError) or name == 'TextShapeError': return 'format'
    return 'validation'


def repair_message(error):
    kind = category(error)
    advice = {
        'format': 'Corrige uniquement la structure et renvoie un objet JSON complet.',
        'length': 'Reformule plus brièvement sans couper le texte ni perdre les conditions et réserves.',
        'terminology': 'Reprends le libellé exact du glossaire ou conserve le sigle seul.',
        'formula': 'La transcription de la formule est incertaine. Explique qualitativement le mécanisme sans deviner un exposant.',
        'scope': 'Conserve les limites et le périmètre exacts de la citation ; ne généralise pas le résultat.',
        'source': 'Corrige le sens à partir des seuls extraits fournis. Ne complète pas une preuve absente.',
    }.get(kind, 'Corrige le point signalé en conservant les identifiants, les preuves et la structure demandés.')
    return kind, 'Contrôle refusé : '+str(error)+'. '+advice
