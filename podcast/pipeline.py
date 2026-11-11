"""Les neuf étapes du PDF au script dialogué, avec traçabilité et mémoire."""
import json
from itertools import groupby
from pathlib import Path
import re
import time

from llm import Cancelled, RepetitionError
from pdfs import extract, fragments
from storage import fingerprint, read, write, write_text

SOURCE_PAGE_MODE = 'pdf-page-v1'

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
            data, markdown = getattr(self,f'step{number}')()
            if self.cancelled.is_set():
                raise Cancelled()
            write_text(self.project/'etapes'/f'{number:02}.md','# '+STEPS[number-1]+'\n\n'+markdown)
            write(self.project/'etapes'/f'{number:02}.json',{'step':number,'title':STEPS[number-1],
                  'created':time.time(),'data':data})
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

    def summarize_part(self, doc, part):
        summaries, ideas, empty_excerpts = [], [], []
        for index, (page,chunk) in enumerate(page_fragments(part['blocks']),1):
            self.progress(f'{doc["id"]} — partie {part["number"]}, page {page}, fragment {index}')
            value = self.summary_excerpt(doc['id'],part['number'],page,chunk)
            summaries.append(value['summary'])
            if not value['ideas']:
                empty_excerpts.append({'page':page,'summary':value['summary']})
            for idea in value['ideas']:
                ideas.append({'statement':idea['statement'],'explanation':idea['explanation'],
                              'pages':[page],'id':f'{doc["id"]}-P{part["number"]}-I{len(ideas)+1:03}',
                              'document':doc['id']})
        return {'number':part['number'],'summary':'\n\n'.join(summaries),'ideas':ideas,
                'excerpts_without_ideas':empty_excerpts}

    def step2(self):
        source = self.saved(1)
        documents, notes = [], []
        for doc in source['documents']:
            parts = []
            for part in doc['parts']:
                title = f'{doc["id"]} — partie {part["number"]}'
                value = self.unit(2,f'{doc["id"]}-P{part["number"]}',title,part,
                                  lambda:self.summarize_part(doc,part),part_markdown)
                parts.append(value)
                notes.append('## '+title+'\n\n'+part_markdown(value))
            documents.append({'id':doc['id'],'name':doc['name'],'parts':parts})
        return {'documents':documents},'\n\n'.join(notes)

    def step3(self):
        data = self.saved(2)
        notes = []
        for doc in data['documents']:
            facts = [i for p in doc['parts'] for i in p['ideas']]
            def validate(v):
                text(v,'text')
            value = self.ask_unit(3,doc['id'],doc['name'],'pdf_synthesis',{'document':doc['id'],'parts':doc['parts']},
                '''Compile les trois résumés de ce PDF en une synthèse pédagogique continue.
                Rétablis les transitions, réunis les doublons et conserve les différences, limites
                et relations causales. Structure : {"text":"synthèse"}. Les idées sources restent
                conservées dans un registre séparé ; n'invente aucune information.''',validate,lambda v:v['text'])
            doc['synthesis'] = value['text']
            notes.append(f'## {doc["id"]} — {doc["name"]}\n\n'+value['text']+'\n\n### Registre complet des idées extraites\n\n'+idea_markdown(facts))
        return data,'\n\n'.join(notes)

    def step4(self):
        data = self.saved(3)
        ideas = all_ideas(data)
        if not ideas:
            raise ValueError('Aucune idée explicative n’a été extraite. Consultez les résumés de l’étape 2 avant de refaire cette étape ou de choisir un autre modèle.')
        wanted = [i['id'] for i in ideas]
        compact = [{'id':i['id'],'statement':i['statement']} for i in ideas]
        def validate_groups(v):
            if not isinstance(v.get('groups'),list) or not v['groups']:
                raise ValueError('Définir des groupes thématiques.')
            seen = []
            for g in v['groups']:
                text(g,'title');strings(g.get('idea_ids'));seen.extend(g['idea_ids'])
            ids_exact(seen,wanted)
        groups = self.client.ask('global_groups',{'ideas':compact},
            '''Ordonne toutes les idées de tous les PDF en groupes thématiques, selon une progression
            de causes, problèmes et solutions. Des idées redondantes peuvent partager un groupe,
            mais chaque identifiant doit apparaître exactement une fois. N'efface pas les contradictions.
            Structure : {"groups":[{"title":"thème", "idea_ids":["identifiants"]}]}''',validate_groups)
        registry = {i['id']:i for i in ideas}
        notes = []
        for number,group in enumerate(groups['groups'],1):
            self.progress('Texte commun — '+group['title'])
            ids = group['idea_ids']
            result = self.ask_unit(4,f'G{number}',group['title'],'global_text',{'group':group,'ideas':[registry[i] for i in ids], 'audience':self.config['audience']},
                '''Rédige un texte pédagogique suivi regroupant ces idées. Relie les causes et les
                conséquences, explicite les prérequis, rapproche les doublons sans perdre les nuances.
                Mentionne les contradictions si elles existent. Chaque idée doit être citée dans le texte
                par [IDENTIFIANT] ; ces références servent au contrôle et ne seront pas lues dans le dialogue.
                Structure : {"text":"texte avec références"}.''',lambda v:citations(v,ids),lambda v:v['text'])
            group['text'] = result['text']
            notes.append('## '+group['title']+'\n\n'+group['text'])
        result = {'groups':groups['groups'],'ideas':ideas,'documents':[{'id':d['id'],'name':d['name']} for d in data['documents']]}
        return result,'\n\n'.join(notes)+'\n\n## Sources et idées\n\n'+idea_markdown(ideas)

    def step5(self):
        data = self.saved(4)
        ids = [i['id'] for i in data['ideas']]
        def validate(v):
            text(v,'central_question')
            if not isinstance(v.get('chapters'),list) or not v['chapters'] or len(v['chapters'])>20:
                raise ValueError('Définir entre 1 et 20 chapitres.')
            seen, chapter_ids = [], []
            for c in v['chapters']:
                for key in ('id','title','question','known','new','why_next'):
                    text(c,key)
                if not re.fullmatch(r'C[0-9]{1,2}',c['id']):
                    raise ValueError('Les chapitres doivent porter les identifiants C1, C2…')
                chapter_ids.append(c['id'])
                strings(c.get('idea_ids'))
                if not c['idea_ids']:
                    raise ValueError('Chaque chapitre doit porter au moins une idée.')
                seen.extend(c['idea_ids'])
                if type(c.get('target_words')) is not int or not 50<=c['target_words']<=4000:
                    raise ValueError('Budget de mots invalide.')
            if len(chapter_ids)!=len(set(chapter_ids)):
                raise ValueError('Identifiants de chapitre répétés.')
            if not isinstance(v.get('exclusions'),list):
                raise ValueError('Liste exclusions requise, éventuellement vide.')
            for e in v['exclusions']:
                text(e,'idea_id');text(e,'reason');seen.append(e['idea_id'])
            ids_exact(seen,ids)
        value = self.client.ask('plan',{'groups':[{'title':g['title'],'idea_ids':g['idea_ids']} for g in data['groups']],
            'ideas':[{'id':i['id'],'statement':i['statement']} for i in data['ideas']], 'audience':self.config['audience'],
            'target_minutes':self.config['minutes'],'approximate_total_words':self.config['minutes']*145},
            '''Construis le plan d'un podcast autour d'une question centrale et de questions qui
            s'enchaînent. Chaque chapitre résout un problème préparant le suivant. Pour chacun,
            indique ce que l'auditeur sait déjà, ce qu'il apprend et le lien suivant.
            Affecte chaque idée exactement une fois à un chapitre. Si la durée impose de laisser
            une idée hors podcast, déclare son identifiant dans exclusions avec un motif explicite.
            Répartis le budget de mots de manière réaliste ; ne remplis pas la durée par des répétitions.
            Structure : {"central_question":"...", "chapters":[{"id":"C1","title":"...",
            "question":"...","known":"...","new":"...","why_next":"...","idea_ids":["..."],
            "target_words":400}],"exclusions":[{"idea_id":"...","reason":"..."}]}''',validate)
        lines = ['Question centrale : '+value['central_question']]
        for c in value['chapters']:
            lines.append(f'## {c["id"]} — {c["title"]}\n\nQuestion : {c["question"]}\n\nDéjà acquis : {c["known"]}\n\nÀ apprendre : {c["new"]}\n\nSuite : {c["why_next"]}\n\nBudget : {c["target_words"]} mots\n\nIdées : '+', '.join(c['idea_ids']))
        if value['exclusions']:
            lines.append('## Idées conservées dans le dossier mais hors podcast\n\n'+'\n'.join('- '+e['idea_id']+' : '+e['reason'] for e in value['exclusions']))
        return value,'\n\n'.join(lines)

    def step6(self):
        plan, data = self.saved(5), self.saved(4)
        registry = {i['id']:i for i in data['ideas']}
        chapters, notes = [], []
        for c in plan['chapters']:
            def validate(v):
                if not isinstance(v.get('items'),list):
                    raise ValueError('Liste items requise.')
                for item in v['items']:
                    text(item,'idea_id');text(item,'sentence')
                ids_exact([i['idea_id'] for i in v['items']],c['idea_ids'])
            value = self.ask_unit(6,c['id'],c['title'],'key_sentences',{'chapter':c,'ideas':[registry[i] for i in c['idea_ids']]},
                '''Pour chaque idée de ce chapitre, écris une phrase complète exprimant son apport
                essentiel, avec son rôle causal si pertinent. Une phrase par idée, sans perdre les conditions.
                Structure : {"items":[{"idea_id":"...","sentence":"..."}]}''',validate,
                lambda v:'\n\n'.join('- '+i['sentence']+' ['+i['idea_id']+']' for i in v['items']))
            chapters.append({'id':c['id'],'items':value['items']})
            notes.append('## '+c['title']+'\n\n'+'\n'.join('- '+i['sentence']+' ['+i['idea_id']+']' for i in value['items']))
        return {'chapters':chapters},'\n\n'.join(notes)

    def step7(self):
        plan, keys, facts = self.saved(5), self.saved(6), self.saved(4)
        registry = {i['id']:i for i in facts['ideas']}
        result, notes = [], []
        for index,c in enumerate(plan['chapters']):
            def validate(v):
                citations(v,c['idea_ids']);text(v,'transition')
            value = self.ask_unit(7,c['id'],c['title'],'explanation',{'chapter':c,'key_sentences':keys['chapters'][index]['items'],
                'ideas':[registry[i] for i in c['idea_ids']], 'previous':plan['chapters'][index-1]['new'] if index else None,
                'audience':self.config['audience']},
                '''Transforme les phrases essentielles en explication pédagogique continue, sans personnages.
                Conserve tous les points et leurs liens. Définis les termes avant de les utiliser.
                Écris une transition d'une phrase rappelant le point précédent et annonçant la question
                actuelle ; pour le premier chapitre, introduis la question. Cite chaque idée [IDENTIFIANT].
                Structure : {"transition":"une phrase", "text":"explication sourcée"}.''',validate,
                lambda v:v['transition']+'\n\n'+v['text'])
            result.append({'id':c['id'],**value})
            notes.append('## '+c['title']+'\n\n'+value['transition']+'\n\n'+value['text'])
        return {'chapters':result},'\n\n'.join(notes)

    def step8(self):
        plan, explanations, facts = self.saved(5), self.saved(7), self.saved(4)
        registry = {i['id']:i for i in facts['ideas']}
        memory = {'explained_ideas':{},'definitions':{},'examples':[],'open_questions':[],'last_turns':[]}
        chapters, memories = [], []
        for index,c in enumerate(plan['chapters']):
            self.progress('Dialogue — '+c['title'])
            def validate(v):
                dialogue_valid(v,self.config['speakers'],c['idea_ids'])
                update = v.get('memory_update')
                if not isinstance(update,dict) or not isinstance(update.get('definitions'),dict):
                    raise ValueError('Mémoire definitions requise.')
                if any(not isinstance(k,str) or not isinstance(val,str) for k,val in update['definitions'].items()):
                    raise ValueError('Définitions textuelles requises.')
                strings(update.get('examples'));strings(update.get('open_questions'))
            outline = {'central_question':plan['central_question'],
                       'chapters':[{'id':ch['id'],'title':ch['title']} for ch in plan['chapters']]}
            value = self.ask_unit(8,c['id'],c['title'],'dialogue',{'plan':outline,'chapter':c,'explanation':explanations['chapters'][index],
                'ideas':[registry[i] for i in c['idea_ids']], 'memory':continuity(memory,c),'speakers':self.config['speakers'],
                'audience':self.config['audience']},DIALOGUE_PROMPT,validate,
                lambda v:script_markdown([{'title':c['title'],**v}],self.config['speakers']),budget=6000)
            update = value.pop('memory_update')
            chapters.append({'id':c['id'],'title':c['title'],**value})
            memory['explained_ideas'].update({i:registry[i]['statement'] for i in c['idea_ids']})
            memory['definitions'].update(update['definitions'])
            memory['examples'] = list(dict.fromkeys(memory['examples']+update['examples']))
            memory['open_questions'] = update['open_questions']
            memory['last_turns'] = value['turns'][-4:]
            memory['next_chapter'] = plan['chapters'][index+1]['id'] if index+1<len(plan['chapters']) else None
            snapshot = json.loads(json.dumps(memory))
            memories.append({'chapter':c['id'],'memory':snapshot})
            # Un état de mémoire consultable est enregistré même si le chapitre suivant échoue.
            write(self.project/'memoire'/f'{c["id"]}.json',snapshot)
        return {'chapters':chapters,'memories':memories},script_markdown(chapters,self.config['speakers'])

    def step9(self):
        plan, draft, facts = self.saved(5), self.saved(8), self.saved(4)
        registry = {i['id']:i for i in facts['ideas']}
        chapters, issues = [], []
        for index,c in enumerate(plan['chapters']):
            self.progress('Révision — '+c['title'])
            def validate(v):
                dialogue_valid(v,self.config['speakers'],c['idea_ids'])
                strings(v.get('issues'))
            value = self.ask_unit(9,c['id'],c['title'],'review',{'chapter':c,'draft':draft['chapters'][index],
                'ideas':[registry[i] for i in c['idea_ids']], 'previous_memory':continuity(draft['memories'][index-1]['memory'],c) if index else {},
                'previous_revised_turns':continuity({'last_turns':chapters[-1]['turns']},c)['last_turns'] if chapters else [],
                'next':plan['chapters'][index+1] if index+1<len(plan['chapters']) else None,
                'speakers':self.config['speakers'],'audience':self.config['audience']},
                '''Révise ce chapitre dans la continuité du podcast. Corrige les répétitions inutiles,
                ruptures de raisonnement, termes non définis et écarts aux sources. Conserve toutes les
                idées affectées au chapitre et les réserves scientifiques. Chaque réplique doit apporter
                une question, une explication, un exemple ou une précision. Garde une transition d'une phrase.
                Ne réintroduis pas tout le podcast. Ne fabrique pas de nouveaux faits. Si un problème reste
                incertain, indique-le dans issues. Structure : {"opening_transition":"...",
                "turns":[{"speaker":"nom autorisé","text":"...","idea_ids":["..."]}],
                "issues":["constat ou modification effectuée"]}.''',validate,
                lambda v:script_markdown([{'title':c['title'],**v}],self.config['speakers']),budget=6000)
            issues.extend({'chapter':c['id'],'note':note} for note in value.pop('issues'))
            chapters.append({'id':c['id'],'title':c['title'],**value})
        spoken = script_plain(chapters,self.config['speakers'])
        words = len(spoken.split())
        expected = {i for c in plan['chapters'] for i in c['idea_ids']}
        covered = {i for c in chapters for turn in c['turns'] for i in turn['idea_ids']}
        result = {'chapters':chapters,'issues':issues,'covered_idea_ids':sorted(covered),
                  'expected_idea_ids':sorted(expected),'all_planned_ids_present':covered==expected,
                  'excluded_ideas':plan['exclusions'],'word_count':words,'estimated_minutes':round(words/145,1),
                  'target_minutes':self.config['minutes'],'markdown':script_markdown(chapters,self.config['speakers']),
                  'plain_text':spoken,
                  'note':'La présence des identifiants ne garantit pas à elle seule la fidélité scientifique. Vérifiez le script avec les sources. La durée est une estimation à 145 mots/minute.'}
        notes = result['markdown']+'\n\n---\n\n'+f'{words} mots — environ {result["estimated_minutes"]} min à 145 mots/minute.\n\n'+result['note']
        result['duration_warning'] = not self.config['minutes']*.7<=words/145<=self.config['minutes']*1.3
        if result['duration_warning']:
            notes += '\n\n**Durée à ajuster :** le script est sensiblement plus court ou plus long que la durée visée. Revoyez les budgets du plan ou régénérez le dialogue.'
        if issues:
            notes += '\n\n## Rapport de révision\n\n'+'\n'.join('- '+i['chapter']+' : '+i['note'] for i in issues)
        return result,notes


def part_markdown(part):
    result = part['summary']+'\n\n'+idea_markdown(part['ideas'])
    if part['excerpts_without_ideas']:
        result += '\n\n### Extraits sans idée retenue — à vérifier\n\n'+'\n'.join(
            f'- Page {e["page"]} : '+e['summary'] for e in part['excerpts_without_ideas'])
    return result


def idea_markdown(ideas):
    return '\n\n'.join(f'- **[{i["id"]}]** {i["statement"]}\n  {i["explanation"]}\n  Source : {i["document"]}, pages '+', '.join(map(str,i['pages'])) for i in ideas)


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
