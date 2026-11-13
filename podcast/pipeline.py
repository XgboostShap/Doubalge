"""Les neuf étapes du PDF au script dialogué, avec traçabilité et mémoire."""
import json
from itertools import groupby
from pathlib import Path
import re
import time

from llm import Cancelled, InvalidResponseError, ModelError, RepetitionError, ResponseLimitError
from pdfs import extract, fragments
import quality
import editorial
from storage import fingerprint, read, write, write_text

SOURCE_PAGE_MODE = 'pdf-page-v1'
SUMMARY_QUALITY_MODE = quality.VERSION
EDITORIAL_MODE = editorial.VERSION

STEPS = [
    'Découper chaque PDF en trois parties', 'Résumer les trois parties',
    'Compiler une synthèse par PDF', 'Construire le texte commun',
    'Créer le plan pédagogique', 'Écrire une phrase par idée importante',
    'Relier les idées en explications', 'Rédiger le dialogue avec mémoire',
    'Réviser le script complet',
]


def text(value, key):
    if not isinstance(value, dict) or not isinstance(value.get(key),str) or not value[key].strip():
        raise ValueError('Texte manquant : '+key)


def strings(values):
    if not isinstance(values,list) or any(not isinstance(v,str) for v in values):
        raise ValueError('Liste de textes requise.')


def ids_exact(actual, expected):
    strings(actual)
    if len(actual)!=len(set(actual)) or set(actual)!=set(expected):
        raise ValueError('Les identifiants doivent couvrir exactement les idées demandées, sans doublon ni invention. Attendus : '+', '.join(expected))


def citations(value, expected):
    text(value,'text')
    found = re.findall(r'\[([A-Z][A-Z0-9-]*-I\d+)\]',value['text'])
    if set(found)!=set(expected):
        raise ValueError('Citer chaque idée attendue dans le texte avec [IDENTIFIANT]. Attendus : '+', '.join(expected))


def all_ideas(data):
    return [idea for doc in data['documents'] for part in doc['parts'] for idea in part['ideas']]


def model_idea(idea):
    return {k:idea[k] for k in ('id','statement','explanation','document','pages') if k in idea}


def page_fragments(blocks):
    """Chaque requête d'extraction porte sur une seule page connue du PDF."""
    for page, group in groupby(blocks,key=lambda b:b['page']):
        if type(page) is not int or page<1:
            raise ValueError('Numéro de page invalide dans le texte extrait du PDF.')
        for chunk in fragments(list(group)):
            yield page,chunk


def dialogue_valid(value, allowed_speakers, wanted):
    text(value,'opening_transition')
    if not isinstance(value.get('turns'),list) or not value['turns']:
        raise ValueError('Le dialogue doit contenir des répliques.')
    covered = set()
    for turn in value['turns']:
        text(turn,'speaker');text(turn,'text')
        if turn['speaker'] not in allowed_speakers:
            raise ValueError('Intervenant inconnu : '+turn['speaker'])
        strings(turn.get('idea_ids'))
        if not set(turn['idea_ids']).issubset(wanted):
            raise ValueError('Une réplique référence une idée étrangère au chapitre.')
        covered.update(turn['idea_ids'])
    if covered!=set(wanted):
        raise ValueError('Le dialogue doit traiter toutes les idées affectées à ce chapitre.')


def continuity(memory, chapter):
    """Fiche bornée pour le prochain appel ; la mémoire complète reste sur disque."""
    def brief(value, limit=180):
        value = str(value)
        return value if len(value)<=limit else value[:limit-1]+'…'
    terms = set(re.findall(r'\w{4,}',json.dumps(chapter,ensure_ascii=False).lower()))
    definitions = list(memory.get('definitions',{}).items())
    relevant = [pair for pair in definitions if terms & set(re.findall(r'\w{4,}',pair[0].lower()))]
    chosen = dict((relevant[-4:]+definitions[-8:]))
    explained = list(memory.get('explained_ideas',{}).items())[-12:]
    return {'explained_ideas':{k:brief(v) for k,v in explained},
            'definitions':{brief(k,80):brief(v) for k,v in chosen.items()},
            'examples':[brief(v) for v in memory.get('examples',[])[-3:]],
            'open_questions':[brief(v) for v in memory.get('open_questions',[])[-4:]],
            'last_turns':[{'speaker':brief(t['speaker'],80),'text':brief(t['text'],240)}
                          for t in memory.get('last_turns',[])[-2:]],
            'next_chapter':memory.get('next_chapter'),
            'note':'Fiche abrégée de continuité, pas un historique de conversation. '
                   'Les textes et mémoires complets sont conservés dans les fichiers du projet.',
            'archived_counts':{'ideas':len(memory.get('explained_ideas',{})),
                               'definitions':len(definitions),'examples':len(memory.get('examples',[]))}}


class Pipeline:
    validate_dialogue = staticmethod(dialogue_valid)
    def __init__(self, project, client, cancelled=None, progress=None):
        self.project = Path(project)
        self.client = client
        self.cancelled = cancelled or client.cancelled
        self.progress = progress or (lambda message:None)
        self.meta = read(self.project/'projet.json')
        self.config = self.meta['settings']

    def saved(self, step):
        return read(self.project/'etapes'/f'{step:02}.json')['data']

    def unit(self, step, key, title, inputs, produce, render):
        """Le JSON validé est le marqueur de fin, écrit après son Markdown."""
        if self.cancelled.is_set():
            raise Cancelled()
        if not re.fullmatch(r'[A-Za-z0-9-]+',key):
            raise ValueError('Identifiant de partie invalide.')
        path = self.project/'etapes'/'parties'/f'{step:02}-{key}.json'
        signature = fingerprint({'version':1,'inputs':inputs,'settings':self.config,
                                 'generation':self.meta.get('cache_generation','initial')})
        if path.exists():
            saved = read(path)
            if saved.get('fingerprint')==signature:
                value = saved['data']
                if not path.with_suffix('.md').exists():
                    write_text(path.with_suffix('.md'),'# '+title+'\n\n'+render(value))
                self.progress('Reprise — partie déjà enregistrée : '+title)
                return value
        value = produce()
        if self.cancelled.is_set():
            raise Cancelled()
        write_text(path.with_suffix('.md'),'# '+title+'\n\n'+render(value))
        write(path,{'step':step,'title':title,'fingerprint':signature,'data':value})
        self.progress('Partie enregistrée en Markdown — '+title)
        return value

    def ask_unit(self, step, key, title, task, payload, instructions, validate, render, budget=4000):
        return self.unit(step,key,title,{'task':task,'payload':payload,'instructions':instructions,'budget':budget},
                         lambda:self.client.ask(task,payload,instructions,validate,budget),render)

    def run(self, first=1, until=9):
        if not 1<=first<=until<=9:
            raise ValueError('Étapes invalides.')
        if first>1 and not (self.project/'etapes'/f'{first-1:02}.json').exists():
            raise ValueError('Terminez les étapes précédentes avant de continuer.')
        for number in range(first,until+1):
            if self.cancelled.is_set():
                raise Cancelled()
            self.progress(f'Étape {number}/9 — {STEPS[number-1]}')
            try:
                data, markdown = getattr(self,f'step{number}')()
            except ModelError as error:
                raise type(error)(f'Étape {number}/9 — {STEPS[number-1]} : '+str(error)) from error
            if self.cancelled.is_set():
                raise Cancelled()
            write_text(self.project/'etapes'/f'{number:02}.md','# '+STEPS[number-1]+'\n\n'+markdown)
            write(self.project/'etapes'/f'{number:02}.json',{'step':number,'title':STEPS[number-1],
                  'created':time.time(),'data':data})
            if number==2:
                self.meta['summary_quality']=quality.VERSION
                self.meta['summary_warnings']=sum(len(p.get('uncertain_ideas',[])) for d in data['documents'] for p in d['parts'])
                write(self.project/'projet.json',self.meta)
        if until==9:
            final = self.saved(9)
            folder = self.project/'exports';folder.mkdir(exist_ok=True)
            write_text(folder/'podcast.md',final['markdown'])
            write_text(folder/'podcast.txt',final['plain_text'])
            write(folder/'podcast.json',final)

    def step1(self):
        docs, notes = [], []
        if not self.meta['pdfs']:
            raise ValueError('Ajoutez au moins un PDF.')
        for i, source in enumerate(self.meta['pdfs'],1):
            self.progress('Extraction du PDF '+str(i)+'/'+str(len(self.meta['pdfs'])))
            doc = extract(self.project/'sources'/source['file'],f'PDF{i}',source['name'])
            docs.append(doc)
            notes.append(f'## {doc["id"]} — {doc["name"]}\n')
            for part in doc['parts']:
                notes.append(f'- Partie {part["number"]} : pages '+', '.join(map(str,part['pages']))+f', {sum(len(b["text"]) for b in part["blocks"])} caractères.')
            if doc['empty_pages']:
                notes.append('\n**À vérifier : pages sans texte extractible** : '+', '.join(map(str,doc['empty_pages']))+'. Images ou pages scannées non analysées.')
            notes.append('')
        return {'documents':docs},'\n'.join(notes)

    def summary_excerpt(self, doc, part, page, chunk, depth=0):
        def validate(value):
            text(value,'summary')
            if not isinstance(value.get('ideas'),list):
                raise ValueError('Extraire les idées importantes dans une liste ideas.')
            for idea in value['ideas']:
                text(idea,'statement');text(idea,'explanation')
        try:
            return self.client.ask('part_summary',{'document':doc,'part':part,'source_page':page,'blocks':chunk},
                '''Résume cet extrait en conservant les liens entre les concepts : pourquoi,
                comment, causes, conséquences, définitions, chiffres et réserves. Ne te limite pas à des mots-clés.
                Structure : {"summary":"explication suivie", "ideas":[{"statement":"idée en une phrase",
                "explanation":"explication et liens causaux"}]}.
                Extrais toutes les idées essentielles du texte fourni dans blocks, sans inventer
                de compléments. Cet extrait provient d'une seule page, indiquée par source_page.
                Le logiciel ajoutera lui-même les références : ne génère pas de numéros de page.
                Si l'extrait ne contient que couverture, sommaire ou bibliographie sans idée
                explicative, renvoie ideas:[] et explique sa nature dans summary, sans inventer.
                La compilation suivante reliera les pages et les trois parties du document.''',validate)
        except RepetitionError:
            # Réduire réellement l'entrée si la reprise locale n'a pas suffi.
            # Aucun caractère ni numéro de page n'est perdu dans le découpage.
            size = sum(len(b['text']) for b in chunk)
            if depth>=3 or size<512:
                raise
            if len(chunk)>1:
                halves = [chunk[:len(chunk)//2],chunk[len(chunk)//2:]]
            else:
                block = chunk[0];middle = len(block['text'])//2
                halves = [[{**block,'text':block['text'][:middle]}],
                          [{**block,'text':block['text'][middle:]}]]
            self.progress(f'Page {page} : lecture en deux extraits plus courts après répétition…')
            results = [self.summary_excerpt(doc,part,page,half,depth+1) for half in halves]
            return {'summary':'\n\n'.join(v['summary'] for v in results),
                    'ideas':[idea for v in results for idea in v['ideas']]}

    def previous_part(self, doc, part, source_signature):
        path=self.project/'reprises'/'02.json'
        if path.exists():
            snapshot=read(path)
            if (snapshot.get('source')==source_signature and
                    snapshot.get('generation')==self.meta.get('cache_generation','initial')):
                for previous_doc in snapshot['data']['documents']:
                    if previous_doc['id']==doc['id']:
                        return next((p for p in previous_doc['parts'] if p['number']==part['number']),None)
        # Compatibilité avec une partie achevée en 0.1.4, avant l'amélioration.
        path=self.project/'etapes'/'parties'/f'02-{doc["id"]}-P{part["number"]}.json'
        legacy_signature=fingerprint({'version':1,'inputs':part,'settings':self.config,
                                      'generation':self.meta.get('cache_generation','initial')})
        if path.exists():
            saved=read(path)
            if saved.get('fingerprint')==legacy_signature:return saved['data']
        return None

    def structured_summary(self, key, title, items, terms, details=False):
        text,identities=editorial.summary(items)
        result={'text':text,'warnings':[],'summary_ids':identities}
        return result if details else text

    def review_candidates(self, payload, batch, raw):
        ambiguous=[i for i in batch if quality.ambiguous_subject(i['statement'])]
        uncertain=[{'id':i['id'],'reason':'À vérifier : le sujet de l’énoncé initial est indéterminé. '
                    'Une correction automatique pourrait attribuer l’effet au mauvais mécanisme.'} for i in ambiguous]
        candidates=[i for i in batch if i not in ambiguous]
        if not candidates:return {'kept':[],'excluded':uncertain}
        payload={**payload,'candidates':[i for i in payload['candidates'] if i['id'] in {c['id'] for c in candidates}]}
        failure=None
        try:
            response=self.client.ask('review_facts',payload,quality.REVIEW_PROMPT,quality.validate_review_envelope,budget=3000)
            decisions=response['decisions']
        except (InvalidResponseError,RepetitionError,ResponseLimitError) as error:
            decisions={};failure=error
        kept=[];excluded=uncertain[:]
        for candidate in candidates:
            identity=candidate['id'];initial=decisions.get(identity)
            one={**payload,'candidates':[i for i in payload['candidates'] if i['id']==identity]}
            def produce():
                problem=failure
                try:
                    result={'decisions':{identity:initial}}
                    quality.validate_review(result,[candidate],raw,payload.get('glossary'))
                    return quality.review_result(result)
                except (ValueError,KeyError,TypeError) as error:problem=problem or error
                # Une réponse globale inutilisable est reprise par idée. Pour une
                # idée déjà seule, l'échec de génération reste borné à cet appel.
                if failure is None or len(candidates)>1:
                    self.progress('Relecture individuelle — '+identity)
                    try:
                        result=self.client.ask('review_facts',one,quality.REVIEW_PROMPT+
                            '\nCorrige uniquement cette idée. Le contrôle a relevé : '+str(problem)[:500],
                            lambda v:quality.validate_review(v,[candidate],raw,payload.get('glossary')),budget=1500)
                        return quality.review_result(result)
                    except (InvalidResponseError,RepetitionError,ResponseLimitError,ValueError) as error:problem=error
                return {'kept':[],'excluded':[{'id':identity,'reason':'À vérifier : contrôle individuel non concluant. '+str(problem)[:500]}]}
            result=self.unit(2,'Verify-'+identity,'Appui source — '+identity,
                {'protocol':quality.VERSION,'payload':one,'initial':initial},produce,review_markdown)
            kept.extend(result['kept']);excluded.extend(result['excluded'])
        if kept:
            checked=self.check_support(kept,payload.get('source_page'))
            kept=checked['kept'];excluded.extend(checked['excluded'])
        return {'kept':kept,'excluded':excluded}

    def check_support(self, facts, page):
        """Deuxième lecture : les citations appuient-elles le sens de chaque idée ?"""
        local={f'I{n}':fact for n,fact in enumerate(facts,1)}
        entries=[{'ref':ref,'statement':f['statement'],'explanation':f['explanation'],
                  'evidence':f['evidence']} for ref,f in local.items()]
        payload={'source_page':page,'facts':entries}
        def produce():
            try:
                response=self.client.ask('fact_support',payload,quality.SUPPORT_PROMPT,quality.validate_support,budget=1800)
                verdicts=response['verdicts']
            except (InvalidResponseError,RepetitionError,ResponseLimitError) as error:
                verdicts={};self.progress('Seconde lecture à reprendre : '+str(error)[:200])
            kept=[];excluded=[]
            for ref,fact in local.items():
                verdict=verdicts.get(ref)
                try:quality.validate_support({'verdicts':{ref:verdict}},[ref])
                except ValueError:
                    try:
                        value=self.client.ask('fact_support',{'source_page':page,'facts':[entries[int(ref[1:])-1]]},
                            quality.SUPPORT_PROMPT,lambda v:quality.validate_support(v,[ref]),budget=600)
                        verdict=value['verdicts'][ref]
                    except (InvalidResponseError,RepetitionError,ResponseLimitError,ValueError) as error:
                        verdict={'status':'uncertain','reason':'Seconde lecture non concluante. '+str(error)[:300]}
                if verdict['status']=='supported' and quality.copied_support_reason(verdict,fact):
                    verdict={'status':'uncertain','reason':'Le motif de seconde lecture recopie l’affirmation sans justifier son appui dans les citations.'}
                if verdict['status']=='supported':kept.append({**fact,'support_reason':verdict['reason']})
                else:
                    label='citations en contradiction avec l’idée' if verdict['status']=='contradicted' else 'citations insuffisantes pour confirmer l’idée'
                    excluded.append({'id':fact['id'],'reason':'À vérifier : '+label+'. '+verdict['reason']})
            return {'kept':kept,'excluded':excluded}
        return self.unit(2,'Support-'+facts[0]['id'],'Seconde lecture des citations — page '+str(page),
            {'protocol':'source-support-v2','quality':quality.VERSION,'payload':payload,'facts':facts,'prompt':quality.SUPPORT_PROMPT},produce,review_markdown)

    def summarize_part(self, doc, part, pages, terms, previous=None):
        ideas, empty_excerpts, excluded, page_notes = [], [], [], []
        old={}
        if previous:
            by_id={i['id']:i for i in previous.get('excluded_ideas',[])+previous.get('ideas',[])}
            for idea in by_id.values():
                if idea.get('pages'):
                    owner=min(idea['pages'])
                    old.setdefault(owner,[]).append({**idea,'pages':[owner]})
        next_id=max([int(i['id'].rsplit('I',1)[1]) for values in old.values() for i in values]+[0])
        # Les pages peuvent avoir plusieurs fragments. Les candidats existants ne
        # sont révisés qu'une fois sur la page complète, sans mélange de provenance.
        source_chunks = ([(page,[b for b in part['blocks'] if b['page']==page])
                          for page in dict.fromkeys(b['page'] for b in part['blocks'])]
                         if previous else list(page_fragments(part['blocks'])))
        for index, (page,chunk) in enumerate(source_chunks,1):
            self.progress(f'{doc["id"]} — partie {part["number"]}, page {page}, fragment {index}')
            kind=pages[page]
            if kind['kind']!='content':
                page_notes.append({'page':page,'kind':kind['kind'],'reason':kind['reason']})
                excluded.extend({**i,'reason':kind['reason']} for i in old.get(page,[]))
                continue
            candidates=old.get(page)
            if candidates is None:
                value=self.summary_excerpt(doc['id'],part['number'],page,chunk)
                if not value['ideas']:empty_excerpts.append({'page':page,'summary':value['summary']})
                candidates=[]
                for idea in value['ideas']:
                    next_id+=1
                    candidates.append({'id':f'{doc["id"]}-P{part["number"]}-I{next_id:03}',
                                       'statement':idea['statement'],'explanation':idea['explanation'],'pages':[page]})
            # Chaque contrôle reçoit un texte source court. Un candidat ancien
            # reste consultable dans les archives même s'il est écarté ici.
            for number,batch in enumerate(quality.batches(candidates,max_chars=6000,max_items=6),1):
                raw=' '.join(b['text'] for b in chunk)
                payload={'source_page':page,'source_text':raw,
                         'candidates':[{'id':i['id'],'statement':i['statement'],'explanation':i['explanation']} for i in batch],
                         'glossary':quality.relevant_terms(terms,raw)}
                reviewed=self.unit(2,f'{doc["id"]}-P{part["number"]}-F{index}R{number}',
                    f'{doc["id"]} — contrôle page {page}',{'protocol':quality.VERSION,'payload':payload,'prompt':quality.REVIEW_PROMPT},
                    lambda:self.review_candidates(payload,batch,raw),review_markdown)
                originals={i['id']:i for i in batch}
                for fact in reviewed['kept']:
                    fact=quality.normalize_terminology(fact,raw)
                    ideas.append({'id':fact['id'],'statement':fact['statement'],'explanation':fact['explanation'],
                                  'pages':[page],'document':doc['id'],'status':fact['status'],'review_reason':fact['reason'],
                                  'support_reason':fact.get('support_reason',''),
                                  'evidence':[{'page':page,'quote':quality.source_quote(q)} for q in fact['evidence']]})
                excluded.extend({**originals[i['id']],'reason':i['reason']} for i in reviewed['excluded'])
        # Fusion seulement des formulations strictement identiques : pas de
        # rapprochement approximatif qui pourrait effacer une nuance scientifique.
        unique={}
        for idea in ideas:
            duplicate=(quality.normalized(idea['statement']),quality.normalized(idea['explanation']))
            if duplicate in unique:
                kept=unique[duplicate]
                kept['pages']=sorted(set(kept['pages']+idea['pages']))
                kept['evidence']+=idea['evidence']
                excluded.append({**idea,'reason':'Doublon exact regroupé avec '+kept['id'],'duplicate_of':kept['id']})
            else:unique[duplicate]=idea
        ideas=list(unique.values())
        ideas,editorial_warnings=editorial.annotated(self,ideas,step=2,key=f'Roles-{doc["id"]}-P{part["number"]}-')
        key=f'{doc["id"]}-P{part["number"]}'
        summary=(self.structured_summary(key,f'{doc["id"]} — partie {part["number"]}',
                   [{'id':i['id'],'statement':i['statement'],'explanation':i['explanation'],'role':i['role'],'importance':i['importance']} for i in ideas],terms,details=True)
                 if ideas else {'text':'Aucune idée explicative retenue. Consultez le rapport des éléments écartés et les pages sources.','warnings':[]})
        uncertain=[i for i in excluded if re.search(r'à vérifier|incertain|insuffisant|non concluant',i['reason'],re.I)]
        return {'number':part['number'],'summary':summary['text'],'synthesis_warnings':summary['warnings'],
                'editorial_warnings':editorial_warnings,
                'ideas':ideas,'quality_version':quality.VERSION,
                'excerpts_without_ideas':empty_excerpts,'excluded_ideas':excluded,'page_notes':page_notes,
                'uncertain_ideas':uncertain,
                'quality_note':'Citations exactes et seconde lecture automatique de leur appui aux idées. Ces contrôles ne garantissent pas la fidélité scientifique ; une relecture reste nécessaire.'}

    def step2(self):
        source = self.saved(1)
        source_signature=fingerprint(source)
        documents, notes = [], []
        for doc in source['documents']:
            pages=quality.catalog(doc);terms=quality.glossary(pages)
            parts = []
            for part in doc['parts']:
                title = f'{doc["id"]} — partie {part["number"]}'
                previous=self.previous_part(doc,part,source_signature)
                value = self.unit(2,f'{doc["id"]}-P{part["number"]}',title,
                                  {'source':part,'quality_version':quality.VERSION,'glossary':terms},
                                  lambda:self.summarize_part(doc,part,pages,terms,previous),part_markdown)
                parts.append(value)
                notes.append('## '+title+'\n\n'+part_markdown(value))
            if terms:
                notes.append('## '+doc['id']+' — lexique repris du PDF\n\n'+'\n'.join(
                    '- **'+term+'** : '+' / '.join(e['definition']+' (page '+str(e['page'])+')' for e in entries)
                    for term,entries in sorted(terms.items())))
            documents.append({'id':doc['id'],'name':doc['name'],'parts':parts,'glossary':terms})
        return {'documents':documents,'quality_version':quality.VERSION},'\n\n'.join(notes)

    def step3(self):
        return editorial.compile_documents(self)

    def compile_pdf(self, document, parts, terms):
        return {'text':'\n\n'.join('### Partie '+str(p['number'])+'\n\n'+p['summary'] for p in parts),
                'warnings':[],'provisional':False}

    def step4(self):
        return editorial.common(self)

    def common_text(self, group, ideas, step=4, context=None):
        value={'text':'\n\n'.join(editorial.passage(i)+' ['+i['id']+']' for i in ideas),'warnings':[]}
        if context is not None:value['transition']=editorial.chapter_transition(group,context.get('previous'))
        return value

    def classify_batch(self, batch, number):
        def produce():
            local={f'I{n}':idea for n,idea in enumerate(batch,1)}
            payload={'ideas':[{'ref':ref,'statement':i['statement']} for ref,i in local.items()]}
            warnings=[]
            try:
                value=self.client.ask('global_groups',payload,
                    '''Classe chaque idée dans un thème court et précis, en français. Réutilise
                    exactement le même titre pour les idées d'un même thème. Les thèmes seront
                    ordonnés dans le plan. Le logiciel conserve les identifiants du PDF : ne les
                    recopie pas. Réponds avec une affectation par référence courte fournie.
                    Structure : {"assignments":{"I1":"titre du thème","I2":"titre du thème"}}.''',
                    lambda v:quality.validate_reference_map(v,'assignments'))
                assignments=value['assignments']
            except (InvalidResponseError,RepetitionError) as error:
                assignments={}
                warnings.append(f'Lot {number} : classement automatique non concluant ; les idées sont conservées dans un groupe provisoire. '+str(error)[:300])
            foreign=set(assignments)-set(local)
            if foreign:warnings.append(f'Lot {number} : références étrangères ignorées ; aucune idée source ajoutée ou supprimée.')
            groups={};unassigned=[]
            for ref,idea in local.items():
                title=assignments.get(ref)
                if not isinstance(title,str) or not title.strip() or len(title.strip())>160:
                    unassigned.append(idea['id']);continue
                title=title.strip()
                groups.setdefault(title,{'title':title,'idea_ids':[]})['idea_ids'].append(idea['id'])
            result=list(groups.values())
            if unassigned:
                result.append({'title':f'Idées du lot {number} — classement à revoir','idea_ids':unassigned})
                warnings.append('Références conservées dans un groupe provisoire : '+', '.join(unassigned))
            ids_exact([identity for g in result for identity in g['idea_ids']],[i['id'] for i in batch])
            return {'groups':result,'warnings':warnings}
        return self.unit(4,f'Lot{number}','Classement des idées — lot '+str(number),
            {'protocol':'local-references-v1','ideas':batch},produce,group_markdown)

    def plan_unit(self, key, title, task, payload, instructions, validate, fallback, budget, bindings=None):
        def produce():
            try:
                value=self.client.ask(task,payload,instructions,validate,budget=budget)
                return {'value':value,'warnings':[]}
            except (InvalidResponseError,RepetitionError,ResponseLimitError) as error:
                return {'value':fallback,'warnings':[title+' : proposition provisoire à relire. '+str(error)[:300]]}
        return self.unit(5,key,title,{'protocol':'bounded-plan-v1','task':task,'payload':payload,
            'instructions':instructions,'budget':budget,'bindings':bindings},produce,
            lambda v:json.dumps(v['value'],ensure_ascii=False,indent=2)+
                ('\n\n### À relire\n\n'+'\n'.join('- '+w for w in v['warnings']) if v['warnings'] else ''))

    def step5(self):
        return editorial.plan(self)

    def step6(self):
        return editorial.sentences(self)

    def chapter_sentences(self, chapter, ideas):
        return {'items':[{'idea_id':i['id'],'sentence':i['statement'],'source_hash':editorial.source_hash(i)}
                         for i in ideas],'warnings':[]}

    def step7(self):
        return editorial.explanations(self)

    def step8(self):
        return editorial.dialogue(self)

    def step9(self):
        return editorial.review(self)


def part_markdown(part):
    counts=f'{len(part["ideas"])} idées retenues'
    if part.get('quality_version'):
        counts+=f' · {sum(i.get("status")=="corrected" for i in part["ideas"])} corrections proposées · {len(part.get("uncertain_ideas",[]))} idées à vérifier'
    result = counts+'\n\n'+part['summary']+'\n\n### Registre détaillé des idées retenues\n\n'+idea_markdown(part['ideas'])
    if part.get('synthesis_warnings'):result+='\n\n'+synthesis_warning_markdown(part['synthesis_warnings'])
    if part.get('page_notes'):
        result+='\n\n### Pages classées hors contenu explicatif\n\n'+'\n'.join(
            f'- Page {p["page"]} : '+p['reason'] for p in part['page_notes'])
    if part.get('excluded_ideas'):
        result+='\n\n### Idées écartées ou regroupées — motifs\n\n'+'\n'.join(
            '- ['+i['id']+'] '+i['statement']+' — '+i['reason'] for i in part['excluded_ideas'])
    if part['excerpts_without_ideas']:
        result += '\n\n### Extraits sans idée retenue — à vérifier\n\n'+'\n'.join(
            f'- Page {e["page"]} : '+e['summary'] for e in part['excerpts_without_ideas'])
    if part.get('quality_note'):result+='\n\n'+part['quality_note']
    return result


def synthesis_warning_markdown(warnings):
    lines=['### Formulations de synthèse à vérifier','']
    for item in warnings:
        lines.append('- '+item.get('section','Synthèse')+' : '+item['reason'])
        if item.get('original'):
            lines.extend(['','Texte automatique non retenu :','',*('> '+line for line in item['original'].splitlines()),''])
    return '\n'.join(lines)


def checked_summary_markdown(packet):
    result=quality.section_markdown(packet['sections'])
    if packet['warnings']:result+='\n\n'+synthesis_warning_markdown(packet['warnings'])
    return result


def compilation_markdown(packet):
    result=('**Compilation provisoire à relire — les sources ont été conservées.**\n\n' if packet['provisional'] else '')+packet['text']
    if packet['warnings']:result+='\n\n'+synthesis_warning_markdown(packet['warnings'])
    return result


def review_markdown(value):
    return '\n\n'.join('- ['+i['id']+'] '+i['statement']+'\n  '+i['explanation']+'\n  Appui source : '+
                      ' / '.join(i['evidence'])+'\n  '+i['status']+' : '+i['reason'] for i in value['kept'])+(
                      '\n\n### Écartés\n\n'+'\n'.join('- '+i['id']+' : '+i['reason'] for i in value['excluded'])
                      if value['excluded'] else '')


def group_markdown(value):
    result='\n\n'.join('## '+g['title']+'\n\n'+', '.join(g['idea_ids']) for g in value['groups'])
    if value['warnings']:result+='\n\n### Classement à vérifier\n\n'+'\n'.join('- '+w for w in value['warnings'])
    return result


def sentences_markdown(value):
    result='\n\n'.join('- '+i['sentence']+' ['+i['idea_id']+']' for i in value['items'])
    if value['warnings']:result+='\n\n### Formulations à vérifier\n\n'+'\n'.join('- '+w for w in value['warnings'])
    return result


def idea_markdown(ideas):
    lines=[]
    for i in ideas:
        line=f'- **[{i["id"]}]** {i["statement"]}\n  {i["explanation"]}\n  Source : {i["document"]}, pages '+', '.join(map(str,i['pages']))
        if i.get('evidence'):
            line+='\n  Appui source : '+' / '.join('« '+e['quote']+' » (page '+str(e['page'])+')' for e in i['evidence'])
        if i.get('status')=='corrected':line+='\n  Correction proposée : '+i['review_reason']
        if i.get('support_reason'):line+='\n  Seconde lecture automatique : '+i['support_reason']
        lines.append(line)
    return '\n\n'.join(lines)


def script_markdown(chapters,speakers):
    lines = []
    for c in chapters:
        lines.extend(['## '+c['title'],'',f'**{speakers[0]} :** '+c['opening_transition'],''])
        for turn in c['turns']:
            lines.extend(['**'+turn['speaker']+' :** '+turn['text'],''])
    return '\n'.join(lines)


def script_plain(chapters,speakers):
    return '\n\n'.join(speakers[0]+' : '+c['opening_transition']+'\n\n'+'\n\n'.join(t['speaker']+' : '+t['text'] for t in c['turns']) for c in chapters)


DIALOGUE_PROMPT = '''Écris ce chapitre du podcast en suivant exactement le plan et l'explication fournie.
Le premier intervenant pose les questions utiles, le deuxième explique, un éventuel troisième apporte
des cas concrets. Chaque échange fait avancer le raisonnement ; les accords qui ne font que répéter
l'autre sont à supprimer. Respecte le budget de mots du chapitre et les connaissances du public.
Utilise la mémoire : ne redéfinis pas inutilement les concepts déjà expliqués et ne recycle pas les exemples.
Commence par une phrase reliant l'acquis précédent à la question actuelle. Garde les citations dans
idea_ids, sans lire leurs identifiants dans les répliques. Chaque idée du chapitre doit être traitée.
Actualise la mémoire avec les définitions introduites, exemples utilisés et questions encore ouvertes.
Structure : {"opening_transition":"une phrase", "turns":[{"speaker":"nom autorisé",
"text":"réplique","idea_ids":["identifiants traités"]}], "memory_update":{
"definitions":{"terme":"définition introduite"},"examples":["exemple"],
"open_questions":["question encore ouverte après ce chapitre"]}}.'''
