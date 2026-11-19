"""Contraintes conservatrices : signaler une ambiguïté, jamais reconstruire un fait."""
import re
import unicodedata
from issues import SourceIssue


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.lower()) if not unicodedata.combining(c))


def constraints(evidence):
    raw=plain(evidence)
    found=[]
    if (re.search(r'\b2\s*d\s+param',raw) or re.search(r'\bo\s*\(\s*n\s*(?:[x×*]\s*)?2\s*d\s*\)',raw)):
        found.append({'kind':'formula','instruction':'Exposant possiblement perdu : ne pas interpréter 2d, n2d ou inventer une puissance. Vérifier visuellement le PDF ou expliquer sans formule.'})
    if re.search(r'\b(?:almost|nearly) all\b|\bpresque tou',raw):
        found.append({'kind':'scope','instruction':'Le résultat porte sur presque tous les cas, pas sur tous les cas.'})
    if re.search(r'\bclassifiers?\b',raw) and re.search(r'\b(?:compar|versus|outperform|evaluat)',raw):
        found.append({'kind':'comparison','instruction':'Une comparaison entre classifieurs ne prouve pas une combinaison de leurs sorties.'})
    if re.match(r'\s*table\s+(?:[ivxlcdm]+|\d+)\b',raw) and len(re.findall(r'\b\d+(?:[.,]\d+)?\b',raw))>=10:
        found.append({'kind':'table','instruction':'Une table de mesures seule ne prouve ni un mécanisme ni une combinaison des résultats. Citer le passage explicatif correspondant.'})
    if re.search(r'\blow computational cost\b',raw):
        found.append({'kind':'cost','instruction':'La méthode proposée est décrite à faible coût de calcul ; ne pas inverser le sens de son effet.'})
    return found


def validate(text,evidence):
    claim=plain(text);source=plain(evidence)
    for rule in constraints(evidence):
        if rule['kind']=='formula' and re.search(
            r'\b2\s*d\b|\bn\s*2\s*d\b|\bdeux\s+(?:fois|multiplie|puissance)|\b2\s*(?:\^|\*\*)\s*d|\bo\s*\(|\b(?:puissance|exposant)\s+d\b',claim):
            raise SourceIssue('La transcription « 2d paramètres » est ambiguë : expliquer la complexité sans interpréter un exposant perdu lors de l’extraction PDF.','formula')
        if rule['kind']=='scope' and re.search(r'\b(?:tous les|toutes les|chaque)\s+(?:jeux?|donnees|cas|experiences|tests|configurations|classif\w*)',claim):
            if not re.search(r'\b(?:presque|quasiment|pratiquement|pas|sauf)\b',claim):
                raise SourceIssue('La source dit « presque tous » : conserver cette réserve dans le résultat.','scope')
        if rule['kind']=='table' and re.search(r'\bcombin\w*|\bpour ameliorer\b|\bce qui (?:explique|permet|entraine)',claim):
            raise SourceIssue('Une table de mesures seule ne soutient pas cette explication ou combinaison : citer le passage explicatif correspondant.','source')
        if rule['kind']=='cost' and re.search(r'\bredu\w*.{0,95}\btests?\b.{0,65}\b(?:ce qui|donc|ainsi).{0,65}\bplus couteu',claim):
            raise SourceIssue('Le passage inverse le coût : la réduction des tests n’est pas présentée comme rendant la méthode proposée plus coûteuse.','source')
        if (rule['kind']=='comparison' and re.search(r'\bcombin\w*.{0,70}\b(?:classif\w*|sorties|predictions)',claim)
            and not re.search(r'\b(?:combin\w*|ensemble\s+of)\b',source)):
            raise SourceIssue('Les citations comparent des classifieurs ; elles ne démontrent pas la combinaison de leurs sorties.','source')
