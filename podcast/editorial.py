"""Contenu ancré aux sources, sélection éditoriale et dialogue traçable."""
import copy
import math
import re

from llm import InvalidResponseError, RepetitionError, ResponseLimitError
from storage import fingerprint, read
import quality

VERSION = 'grounded-editorial-v2'
MAX_QUESTION_WORDS = 20
EXPECTED_QUESTION_WORDS = 12
CHAPTER_OVERHEAD_WORDS = 60
RECOVERABLE = (InvalidResponseError, RepetitionError, ResponseLimitError)
ROLES = ('concept','problem','method','result','application','limit')
LABELS = {'concept':'Les notions pour comprendre','problem':'Le problème à résoudre',
          'method':'Comment fonctionne la méthode','result':'Les résultats et leurs conditions',
          'application':'Les applications concrètes','limit':'Les limites et les points de vigilance'}
QUESTIONS = {'concept':'Peux-tu expliquer cette notion simplement ?',
             'problem':'Quel problème rencontre-t-on et pourquoi est-ce important ?',
             'method':'Comment fonctionne la méthode proposée ?',
             'result':'Qu’observe-t-on dans les conditions décrites ?',
             'application':'À quoi cela sert-il dans le cas présenté ?',
             'limit':'Quelles limites faut-il garder en tête ?'}
QUESTION_VARIANTS = {
    'concept':('Que signifie cette notion ?', 'Comment comprendre ce point ?', 'Quel est le principe à retenir ?'),
    'problem':('Quelle difficulté se pose ici ?', 'Quel est le problème décrit ?', 'Pourquoi ce point pose-t-il problème ?'),
    'method':('Quel est le principe de cette méthode ?', 'Comment procède-t-on dans ce cas ?', 'Peux-tu expliquer cette démarche ?'),
    'result':('Quel résultat a été observé ?', 'Que montre cette observation ?', 'Dans quelles conditions obtient-on ce résultat ?'),
    'application':('Quel usage est présenté ici ?', 'Peux-tu préciser cette application ?', 'Comment utilise-t-on cela dans ce cas ?'),
    'limit':('Quel point de vigilance faut-il retenir ?', 'Quelle réserve est formulée ici ?', 'Pourquoi faut-il rester prudent ?')}

def neutral_question(role, recent):
    used={quality.definition_key(q) for q in recent[-3:]}
    return next(q for q in (QUESTIONS[role],)+QUESTION_VARIANTS[role] if quality.definition_key(q) not in used)

def source_hash(idea):
    return fingerprint({k:idea.get(k) for k in ('id','statement','explanation','document','pages','evidence')})

def passage(idea):
    statement=idea['statement'].strip()
    explanation=idea.get('explanation','').strip()
    if not explanation or quality.normalized(explanation)==quality.normalized(statement):
        return statement.rstrip('. ')+'.'
    if quality.normalized(explanation).startswith(quality.normalized(statement)):
        return explanation
    combined=statement.rstrip('. ')+'. '+explanation
    sentences=[];seen=set()
    for sentence in re.split(r'(?<=[.!?])\s+',combined):
        clean=re.sub(r'^(?:Le texte|Le passage|L.extrait)\s+(?:explique|indique|mentionne|précise)\s+que\s+', '',sentence)
        key=quality.normalized(clean).rstrip('. ')
        if key in seen:continue
        seen.add(key);sentences.append(clean)
    return ' '.join(sentences)

def words(text):
    return len(text.split())

def role_fallback(idea):
    text=quality.definition_key(idea['statement']+' '+idea.get('explanation',''))
    rules=(('limit',r'\b(limite|limites|risque|risques|incertitude|hallucinations|pas encore|ne suffit|inexactitude)\b'),
           ('result',r'\b(experience|experimental|resultat|resultats|mesure|accuracy|precision|demontre)\b'),
           ('method',r'\b(methode|algorithme|strategie|procedure|propose|etape|optimisation)\b'),
           ('application',r'\b(application|gestion|cycle de vie|utilisation|configuration|agent)\b'),
           ('problem',r'\b(probleme|difficulte|defi|degradation|bruit|perte|pertes)\b'))
    role=next((r for r,pattern in rules if re.search(pattern,text)), 'concept')
    detail=bool(re.search(r'\b(figure|table|index|equation|chapitre|appendix)\b',text))
    return {'role':role,'importance':'detail' if detail else 'support',
            'reason':'Classement indicatif par le vocabulaire ; à relire.'}


def document_commentary(text):
    return bool(quality.unusable_fact_text(text) or re.search(r'\b(?:PDF\d+|(?:chapitre|section|figure)\s+\d+)\b',text,re.I) or
        re.search(r'^(?:ce|cet|cette|le|la|notre)\s+(?:document|travail|article|thèse|section)\s+(?:présente|décrit|traite|explore|contient)',text,re.I))

def annotated(pipe, ideas, step=4, key='Roles'):
    """Le modèle classe les idées, sans pouvoir réécrire leurs faits."""
    result=[];warnings=[];known_topics=[]
    for index,start in enumerate(range(0,len(ideas),5),1):
        batch=ideas[start:start+5]
        local={'F'+source_hash(i)[:10]:i for i in batch}
        payload={'known_topics':known_topics[:12],'ideas':[{'ref':ref,'statement':i['statement'][:1000],'statement_is_excerpt':len(i['statement'])>1000,
                          'explanation':i.get('explanation','')[:1200],
                          'explanation_is_excerpt':len(i.get('explanation',''))>1200} for ref,i in local.items()]}
        def produce():
            issues=[]
            try:
                raw=pipe.client.ask('editorial_roles',payload,
                    '''Classe chaque idée sans la réécrire. role vaut concept, problem, method,
                    result, application ou limit. importance vaut essential, support ou detail.
                    Pour un débutant, privilégie définitions, problème, principe de méthode,
                    résultats AVEC conditions, applications et limites. Index, titres et tableaux
                    sans apport explicatif sont des détails. reason : motif bref en français.
                    topic : thème nominal de 2 à 7 mots ; réutilise les thèmes connus et reste
                    autour de 6 grands thèmes cohérents. level vaut foundation pour une notion
                    indispensable à expliquer avant les méthodes, core pour le raisonnement et
                    les résultats, detail pour les paramètres, cas numérotés, listes et réglages.
                    Un sigle, une API ou un paramètre n'est pas une notion de base par sa seule présence.
                    Structure : {"roles":{"REFERENCE":{"role":"concept","importance":"essential",
                    "reason":"motif","topic":"thème","level":"foundation"}}}.
                    Ne retourne aucun énoncé ni identifiant du PDF.''',
                    lambda v:quality.validate_reference_map(v,'roles'),budget=1100)
                mapping=raw['roles']
            except RECOVERABLE as error:
                mapping={};issues.append('Classement éditorial indicatif : '+str(error)[:250])
            decisions={}
            for ref,idea in local.items():
                row=mapping.get(ref)
                if (not isinstance(row,dict) or row.get('role') not in ROLES or
                    row.get('importance') not in ('essential','support','detail') or
                    not isinstance(row.get('reason'),str) or not row['reason'].strip()):
                    row=role_fallback(idea);issues.append(idea['id']+' : classement éditorial de secours.')
                decision={k:row[k] for k in ('role','importance','reason')}
                topic=row.get('topic')
                if isinstance(topic,str) and 1<=len(topic.split())<=7 and not re.search(r'[.!?;\n]|\bPDF\d+\b',topic):decision['topic']=topic.strip()
                decision['level']=row.get('level') if row.get('level') in ('foundation','core','detail') else ('foundation' if decision['role']=='concept' else 'core')
                if re.match(r'^Case[- ]?\d\b',idea['statement'],re.I):
                    decision.update(level='detail',importance='detail',reason='Scénario numéroté et paramètres conservés au dossier ; le podcast privilégie le principe de la méthode.')
                decisions[idea['id']]=decision
            return {'decisions':decisions,'warnings':issues}
        packet=pipe.unit(step,f'{key}{index}','Classement éditorial — lot '+str(index),
            {'protocol':VERSION,'payload':payload,'source_hashes':[source_hash(i) for i in batch]},
            produce,lambda v:'\n'.join('- '+i+' : '+r['role']+' / '+r['importance']+' — '+r['reason']
                                     for i,r in v['decisions'].items()))
        warnings.extend(packet['warnings'])
        for idea in batch:
            entry={**idea,**packet['decisions'][idea['id']],'source_hash':source_hash(idea)}
            if entry.get('topic') and entry['topic'] not in known_topics:known_topics.append(entry['topic'])
            result.append(entry)
    return result,warnings

def summary(ideas, maximum=12):
    """Résumé extractif : sélection de phrases sources, sans assertion nouvelle."""
    fields={r:[] for r in ROLES}
    for idea in ideas:
        fields[idea.get('role',role_fallback(idea)['role'])].append(idea)
    selected=[]
    for rank in range(2):
        for role in ROLES:
            choices=sorted(fields[role],key=lambda i:({'essential':0,'support':1,'detail':2}.get(i.get('importance'),1),len(passage(i))))
            if len(choices)>rank and len(selected)<maximum:selected.append(choices[rank])
    lines=[]
    for role in ROLES:
        entries=[i for i in selected if i.get('role',role_fallback(i)['role'])==role]
        if entries:
            title={'concept':'Notions essentielles','problem':'Problème posé','method':'Méthodes et raisonnement',
                   'result':'Résultats et apports','limit':'Limites et réserves','application':'Applications'}[role]
            lines+=['### '+title,'']
            lines.extend('- '+passage(i)+(' ['+i['id']+']' if i.get('id') else '') for i in entries)
            lines.append('')
    return '\n'.join(lines),[i['id'] for i in selected if i.get('id')]

def compile_documents(pipe):
    data=copy.deepcopy(pipe.saved(2));notes=[]
    if data.get('quality_version')!=quality.VERSION:
        raise ValueError('Anciennes sources : utiliser Améliorer les résumés existants avant de continuer.')
    for doc in data['documents']:
        sections=[];selected=[]
        for part in doc['parts']:
            for idea in part['ideas']:
                if idea.get('source_hash')!=source_hash(idea):raise ValueError('Source modifiée : réexaminer les résumés avant leur compilation. '+idea['id'])
            text,ids=summary(part['ideas'],6)
            sections.append('### Partie '+str(part['number'])+'\n\n'+text)
            selected.extend(ids)
        doc['synthesis']='\n\n'.join(sections)
        doc['synthesis_ids']=selected
        doc['synthesis_warnings']=[]
        doc['synthesis_provisional']=False
        notes.append('## '+doc['id']+' — '+doc['name']+'\n\n'+doc['synthesis'])
        notes.append('### Registre complet des idées\n\n'+registry_markdown([i for p in doc['parts'] for i in p['ideas']]))
    data['workflow_version']=VERSION
    return data,'\n\n'.join(notes)

def registry_markdown(ideas):
    return '\n\n'.join('- **['+i['id']+']** '+i['statement']+'\n  '+i.get('explanation','')+
        '\n  Source : '+i.get('document','PDF')+', pages '+', '.join(map(str,i.get('pages',[])))+
        ('\n  Appui source : '+' / '.join('« '+e['quote']+' » (page '+str(e['page'])+')' for e in i.get('evidence',[]))
         if i.get('evidence') else '') for i in ideas)

def common(pipe):
    data=pipe.saved(3);ideas=[copy.deepcopy(i) for d in data['documents'] for p in d['parts'] for i in p['ideas']]
    if data.get('workflow_version')!=VERSION:raise ValueError('Ancienne synthèse : reprendre à l’étape 3 après réexamen des sources.')
    if not ideas:raise ValueError('Aucune idée explicative retenue ; revoir le rapport des sources à l’étape 2.')
    if len({i['id'] for i in ideas})!=len(ideas):raise ValueError('Identifiants sources en doublon : reprendre les résumés.')
    if any(i.get('source_hash')!=source_hash(i) for i in ideas):raise ValueError('Source modifiée : réexaminer les résumés avant le texte commun.')
    warnings=[]
    if any(i.get('role') not in ROLES for i in ideas):
        ideas,warnings=annotated(pipe,ideas)
    for i in ideas:i['source_hash']=source_hash(i)
    groups=[];notes=[]
    for role in ROLES:
        entries=[i for i in ideas if i['role']==role]
        if not entries:continue
        text='\n\n'.join(passage(i)+' ['+i['id']+']' for i in entries)
        groups.append({'id':f'G{len(groups)+1}','title':LABELS[role],'role':role,
                       'idea_ids':[i['id'] for i in entries],'text':text})
        notes.append('## '+LABELS[role]+'\n\n'+text)
    result={'workflow_version':VERSION,'groups':groups,'ideas':ideas,
        'documents':[{k:d.get(k,{}) for k in ('id','name','glossary')} for d in data['documents']],
        'classification_warnings':warnings,'text_warnings':[],
        'synthesis_warnings':[],
        'source_uncertainties':[{'document':d['id'],'id':i['id'],'pages':i.get('pages',[]),'reason':i['reason']}
            for d in data['documents'] for p in d['parts'] for i in p.get('uncertain_ideas',[])]}
    return result,'\n\n'.join(notes)+'\n\n## Sources et idées\n\n'+registry_markdown(ideas)

def definitions(data):
    result={}
    for doc in data.get('documents',[]):
        for term,entries in doc.get('glossary',{}).items():
            if not entries:continue
            entry=entries[0]
            result[(doc['id'],term)]={'term':term,'definition':quality.preferred_definition(entry['definition']),
                                      'page':entry['page'],'document':doc['id']}
    return result

def fact_definitions(idea, terms):
    text=idea['statement']+' '+idea.get('explanation','')
    return [row for (document,term),row in terms.items() if document==idea.get('document') and
            re.search(r'\b'+re.escape(term)+r's?\b',text)]

def selection(data, minutes):
    ideas=data['ideas'];terms=definitions(data);total=minutes*145
    # Les introductions/raccords et la conclusion sont budgétés avant les idées.
    available=total
    queues={r:[] for r in ROLES};excluded={};duplicates={}
    for idea in ideas:
        if document_commentary(idea['statement']) or quality.unusable_fact_text(idea.get('explanation','')):
            excluded[idea['id']]='Commentaire sur le document ou texte de gabarit ; conservé au dossier pour réexamen, hors dialogue.'
            continue
        key=(quality.normalized(idea['statement']),quality.normalized(idea.get('explanation','')))
        if key in duplicates:
            excluded[idea['id']]='Redite exacte de '+duplicates[key]+' ; source conservée dans le dossier.'
        else:
            duplicates[key]=idea['id']
            choice={**idea}
            queues[idea.get('role',role_fallback(idea)['role'])].append(choice)
    priority={'essential':0,'support':1,'detail':2}
    position={i['id']:n for n,i in enumerate(ideas)}
    for role in ROLES:
        queues[role].sort(key=lambda i:({'foundation':0,'core':1,'detail':2}.get(i.get('level'),0 if role=='concept' else 1),
            priority.get(i.get('importance'),1),position[i['id']]))
    selected=[];cost=200;known=set();counts={}
    while any(queues.values()):
        tier=min({'foundation':0,'core':1,'detail':2}.get(q[0].get('level'),0 if r=='concept' else 1) for r,q in queues.items() if q)
        for role in ROLES:
            if not queues[role]:continue
            if {'foundation':0,'core':1,'detail':2}.get(queues[role][0].get('level'),0 if role=='concept' else 1)!=tier:continue
            idea=queues[role].pop(0)
            if idea.get('level')=='detail' or idea.get('importance')=='detail':
                excluded[idea['id']]='Détail spécialisé conservé au dossier pour privilégier les notions et le raisonnement dans le podcast.'
                continue
            defs=[d for d in fact_definitions(idea,terms) if (d['document'],d['term']) not in known]
            definition_cost=sum(words(definition_text(d)) for d in defs)
            increment=words(passage(idea))+EXPECTED_QUESTION_WORDS+definition_cost
            group=quality.definition_key(idea.get('topic') or LABELS[role])
            # Le coût vient du texte retenu, des définitions et d'une question brève.
            increment=increment+(CHAPTER_OVERHEAD_WORDS if counts.get(group,0)%5==0 else 0)
            if cost+increment<=available:
                selected.append(idea);cost+=increment
                counts[group]=counts.get(group,0)+1
                known.update((d['document'],d['term']) for d in defs)
            else:
                excluded[idea['id']]='Détail ou point complémentaire hors budget de durée ; conservé dans le dossier.'
    return selected,[{'idea_id':i['id'],'reason':excluded[i['id']]} for i in ideas if i['id'] in excluded],cost,terms

def plan(pipe):
    data=pipe.saved(4)
    if data.get('workflow_version')!=VERSION:
        raise ValueError('Ancien texte commun : réexaminer les sources puis reconstruire à partir de l’étape 3.')
    if len({i['id'] for i in data['ideas']})!=len(data['ideas']):raise ValueError('Identifiants sources en doublon.')
    if any(i.get('source_hash')!=source_hash(i) for i in data['ideas']):raise ValueError('Source modifiée : reconstruire le texte commun.')
    selected,excluded,cost,terms=selection(data,pipe.config['minutes'])
    if not selected:raise ValueError('Aucune idée ne tient dans la durée visée ; augmenter la durée ou choisir un extrait.')
    roles=[r for r in ROLES if any(i['role']==r for i in selected)]
    topic_groups={}
    for idea in selected:
        name=idea.get('topic') or LABELS[idea['role']]
        key=quality.definition_key(name)
        topic_groups.setdefault(key,{'title':name,'ideas':[]})['ideas'].append(idea)
    groups=sorted(topic_groups.values(),key=lambda g:(min({'foundation':0,'core':1}.get(i.get('level'),0 if i['role']=='concept' else 1) for i in g['ideas']),
        min(data['ideas'].index(i) for i in g['ideas'])))
    topic_rows=[{'ref':f'T{n}','title':g['title'],
        'level':'foundation' if any(i.get('level')=='foundation' or (not i.get('level') and i['role']=='concept') for i in g['ideas']) else 'core',
        'sample':g['ideas'][0]['statement'][:180]} for n,g in enumerate(groups,1)]
    by_topic={r['ref']:g for r,g in zip(topic_rows,groups)}
    samples=[]
    for role in roles:
        for idea in [i for i in selected if i['role']==role][:2]:
            samples.append({'role':role,'statement':idea['statement'][:220],
                'statement_is_excerpt':len(idea['statement'])>220})
    fallback={'central_question':'Comment comprendre les notions, les méthodes, leurs résultats et leurs limites dans ces documents ?',
              'titles':{r:LABELS[r] for r in roles}}
    vocabulary=' '.join(passage(i) for i in selected)+' '+' '.join(d['definition'] for d in terms.values())
    def propose_outline():
        issues=[]
        payload={'roles':roles,'samples':samples,'samples_are_incomplete':True,'audience':pipe.config['audience'],
                 'glossary':[d for d in terms.values() if d['term'] in quality.subject_symbols(vocabulary)][:10],
                 'topics':topic_rows if len(topic_rows)<=12 else []}
        try:
            value=pipe.client.ask('editorial_outline',payload,
                '''Propose une question centrale neutre et un titre bref par rôle pédagogique.
                L'ordre est imposé : notions, problème, méthode, résultats, applications, limites.
                Utilise les termes des points fournis et du lexique, sans ajouter de résultat.
                Titres distincts, 12 mots maximum ; question centrale de 30 mots maximum, finissant
                par ?. Pas de promesse de garantie, d'autonomie totale ou de supériorité générale.
                topic_order : toutes les références de topics, une fois chacune, dans un ordre
                pédagogique. Les notions fondatrices précèdent les méthodes qui les utilisent.
                Regroupe les notions proches ; les API, paramètres et cas numérotés viennent après
                les principes du domaine. N'invente aucun thème ni aucune référence.
                Structure : {"central_question":"question ?","titles":{"concept":"titre"}}.''',
                lambda v:(quality.validate_reference_map(v,'titles'),quality.validate_compilation({'text':v.get('central_question','')})),budget=900)
        except RECOVERABLE as error:
            value=fallback;issues.append('Question et titres indicatifs : '+str(error)[:200])
        banned=r'garanti|toujours|sans intervention|100\s*%|\bPDF\d+\b|\b(?:chapitre|section|figure)\s+\d+\b|présent(?:er|ation)\s+(?:du|le)\s+document'
        allowed={w for w in quality.definition_key(vocabulary+' '+' '.join(LABELS.values())).split() if len(w)>4}
        neutral={'comment','pourquoi','comprendre','expliquer','peuvent','apporter','principes','enjeux','limites','conditions','notions'}
        def relevant(text,limit):
            if not isinstance(text,str) or not text.strip() or words(text)>limit:return False
            try:quality.french_text(text)
            except ValueError:return False
            if re.search(banned,text,re.I):return False
            if any(t not in quality.subject_symbols(vocabulary) for t in quality.subject_symbols(text)):return False
            tokens={w for w in quality.definition_key(text).split() if len(w)>4}
            return len(tokens-(allowed|neutral))<=max(1,len(tokens)//3)
        # Une question libre peut présupposer un lien absent des sources, même
        # si chacun de ses mots apparaît quelque part dans le registre.
        question=fallback['central_question']
        titles={};seen=[]
        for role in roles:
            title=value['titles'].get(role)
            key=quality.definition_key(title) if isinstance(title,str) else ''
            token=set(key.split())
            declarative=isinstance(title,str) and re.search(r'\b(?:est|sont|utilise|utilisent|utilisé|utilisée|propose|proposent|proposé|proposée|nécessaire|introduit|se posent|implique|permet|garantit|améliore|améliorent|démontre|démontrent)\b',title,re.I)
            nominal=isinstance(title,str) and re.match(r'^(?:(?:les?|la|des?)\s+)?(?:notions|bases|principes|comprendre|problèmes?|défis|difficultés|méthodes?|démarches?|résultats|observations|mesures|applications|usages|limites|réserves|conditions|points? de vigilance)\b',title,re.I)
            if (not relevant(title,12) or declarative or not nominal or any(key==other or (len(token&set(other.split()))/max(1,len(token|set(other.split()))))>.8 for other in seen)):
                title=LABELS[role];key=quality.definition_key(title)
                issues.append('Titre '+role+' remplacé par un intitulé distinct et neutre.')
            titles[role]=title;seen.append(key)
        order=value.get('topic_order',[])
        if (not isinstance(order,list) or any(not isinstance(ref,str) for ref in order) or
            len(order)!=len(by_topic) or set(order)!=set(by_topic)):
            order=list(by_topic)
            if any(i.get('topic') for i in selected):issues.append('Ordre thématique indicatif : les notions fondatrices restent prioritaires.')
        # Même si le modèle propose l'inverse, les prérequis restent devant.
        levels={r['ref']:r['level'] for r in topic_rows}
        order=sorted(order,key=lambda ref:0 if levels[ref]=='foundation' else 1)
        return {'central_question':question,'titles':titles,'warnings':issues,'topic_order':order}
    outline=pipe.unit(5,'Fil','Fil conducteur et titres du podcast',
        {'protocol':VERSION,'samples':samples,'roles':roles,'topics':topic_rows,'sources':[source_hash(i) for i in selected],
         'glossary':list(terms.values())},propose_outline,
        lambda v:v['central_question']+'\n\n'+'\n'.join('- '+v['titles'][r] for r in roles))
    chapters=[]
    for ref in outline['topic_order']:
        group=by_topic[ref];entries=group['ideas']
        role=min(ROLES,key=lambda r:-sum(i['role']==r for i in entries))
        base_title=group['title'] if any(i.get('topic') for i in entries) else outline['titles'][role]
        entries.sort(key=lambda i:({'foundation':0,'core':1}.get(i.get('level'),0 if i['role']=='concept' else 1),ROLES.index(i['role'])))
        for start in range(0,len(entries),5):
            chunk=entries[start:start+5]
            title=base_title+(' — approfondissement '+str(start//5+1) if start else '')
            previous=chapters[-1]['title'] if chapters else None
            chapters.append({'id':f'C{len(chapters)+1}','title':title,'role':role,
                'question':QUESTIONS[role],'known':previous or 'Aucune connaissance préalable n’est supposée.',
                'new':'Comprendre les points sources de cette partie.',
                'why_next':'Relier ces points à la partie suivante.',
                'recap_id':chapters[-1]['idea_ids'][-1] if chapters else None,
                'idea_ids':[i['id'] for i in chunk],
                'target_words':sum(words(passage(i))+EXPECTED_QUESTION_WORDS+
                    sum(words(definition_text(d)) for d in fact_definitions(i,terms)) for i in chunk)+CHAPTER_OVERHEAD_WORDS})
    warnings=outline['warnings'][:]
    if len(chapters)>6:warnings.append('Certaines parties sont divisées pour limiter le nombre d’idées par échange.')
    if cost<pipe.config['minutes']*145*.6:warnings.append('Peu de matière vérifiée pour la durée demandée ; aucun remplissage inventé.')
    named_topics=[g['title'] for g in groups if any(i.get('topic') for i in g['ideas'])]
    central_question=('Comment comprendre '+', '.join(named_topics[:3])+' et leurs limites ?') if named_topics else outline['central_question']
    value={'workflow_version':VERSION,
        'central_question':central_question,
        'chapters':chapters,'exclusions':excluded,'warnings':warnings,'selected_count':len(selected),
        'registry_count':len(data['ideas']),'estimated_content_words':cost,
        'glossary_hash':fingerprint(sorted(terms.values(),key=lambda d:(d['document'],d['term']))),
        'registry_hash':fingerprint(data['ideas']),
        'target_words':pipe.config['minutes']*145,
        'source_hashes':{i['id']:source_hash(i) for i in selected}}
    weights=[c['target_words'] for c in chapters];available=pipe.config['minutes']*145
    budgets=[max(1,available*w//sum(weights)) for w in weights]
    for n in range(available-sum(budgets)):budgets[n%len(budgets)]+=1
    for c,budget in zip(chapters,budgets):c['target_words']=budget
    lines=['Question centrale : '+value['central_question'],'',
        f"{len(selected)} idées sélectionnées sur {len(data['ideas'])}. Les autres restent dans le dossier avec leur motif.",
        'La sélection respecte un budget de contenu ; la durée finale reste une estimation.']
    for c in chapters:
        lines+=['## '+c['id']+' — '+c['title'],'',
            'Question : '+c['question'],'','Déjà acquis : '+c['known'],'',
            'Budget : '+str(c['target_words'])+' mots','','Idées : '+', '.join(c['idea_ids'])]
    if excluded:
        lines+=['## Idées conservées dans le dossier mais hors podcast','']
        lines+=['- '+e['idea_id']+' : '+e['reason'] for e in excluded]
    return value,'\n\n'.join(lines)

def checked_registry(pipe):
    plan=pipe.saved(5);data=pipe.saved(4)
    if plan.get('workflow_version')!=VERSION:
        raise ValueError('Plan ancien : reprendre l’étape 5 avec la sélection éditoriale.')
    registry={i['id']:i for i in data['ideas']}
    if plan.get('registry_hash')!=fingerprint(data['ideas']):raise ValueError('Une idée source a changé : reconstruire le plan.')
    expected=[i for c in plan['chapters'] for i in c['idea_ids']]
    excluded=[e['idea_id'] for e in plan['exclusions']]
    if (len(expected)!=len(set(expected)) or set(expected)!=set(plan['source_hashes']) or
        set(expected)&set(excluded) or set(expected)|set(excluded)!=set(registry)):
        raise ValueError('Le plan ne couvre pas exactement le registre source : refaire l’étape 5.')
    current_terms=definitions(data)
    if plan.get('glossary_hash')!=fingerprint(sorted(current_terms.values(),key=lambda d:(d['document'],d['term']))):
        raise ValueError('Le lexique source a changé : reconstruire le plan.')
    for identity,expected in plan['source_hashes'].items():
        if identity not in registry or source_hash(registry[identity])!=expected:
            raise ValueError('Une idée source a changé : reconstruire le plan avant de poursuivre. '+identity)
    return plan,data,registry

def sentences(pipe):
    plan,data,registry=checked_registry(pipe);chapters=[];notes=[]
    for c in plan['chapters']:
        items=[{'idea_id':i,'sentence':registry[i]['statement'],'source_hash':source_hash(registry[i])} for i in c['idea_ids']]
        chapters.append({'id':c['id'],'items':items})
        notes+=['## '+c['title'],'','\n\n'.join('- '+i['sentence']+' ['+i['idea_id']+']' for i in items)]
    return {'workflow_version':VERSION,'chapters':chapters,'warnings':[]},'\n\n'.join(notes)

def explanations(pipe):
    plan,data,registry=checked_registry(pipe);keys=pipe.saved(6);chapters=[];notes=[]
    if keys.get('workflow_version')!=VERSION:raise ValueError('Phrases anciennes : refaire l’étape 6 avant les explications.')
    actual={i['idea_id']:i for c in keys['chapters'] for i in c['items']}
    for c in plan['chapters']:
        entries=[]
        for identity in c['idea_ids']:
            key=actual.get(identity)
            if not key or key.get('source_hash')!=source_hash(registry[identity]) or key['sentence']!=registry[identity]['statement']:
                raise ValueError('Phrase associée à une autre idée : refaire l’étape 6. '+identity)
            entries.append({'idea_id':identity,'source_hash':source_hash(registry[identity]),'text':passage(registry[identity])})
        transition=chapter_transition(c,chapters[-1]['title'] if chapters else None,registry)
        text='\n\n'.join(i['text']+' ['+i['idea_id']+']' for i in entries)
        chapters.append({'id':c['id'],'title':c['title'],'transition':transition,'text':text,'items':entries})
        notes+=['## '+c['title'],'',transition,'',text]
    return {'workflow_version':VERSION,'chapters':chapters,'warnings':[]},'\n\n'.join(notes)

def chapter_transition(chapter, previous=None, registry=None):
    if registry and chapter.get('recap_id'):
        previous_fact=registry[chapter['recap_id']]['statement'].rstrip('. ')
        return 'Nous avons retenu ce point : « '+previous_fact+' » ; voyons maintenant « '+chapter['title']+' ».'
    if previous:return 'Après « '+previous+' », abordons « '+chapter['title']+' ».'
    return 'Pour commencer, voici les notions nécessaires pour comprendre le sujet.'

def chapter_opening(chapter,plan,registry,first=False):
    opening=chapter_transition(chapter,None,registry)
    if first:return 'Bonjour et bienvenue. '+plan['central_question']+' Nous partirons des bases pour comprendre les méthodes, leurs résultats et leurs limites. '+opening
    return opening

def closing_text(plan,registry):
    chosen=[]
    for role in ('concept','method','limit'):
        found=next((registry[i] for c in plan['chapters'] for i in c['idea_ids'] if registry[i]['role']==role),None)
        if found and found['id'] not in chosen:chosen.append(found['id'])
    if not chosen:chosen=[plan['chapters'][0]['idea_ids'][0]]
    text='Pour conclure, voici les points à retenir. '+' '.join(registry[i]['statement'].rstrip('. ')+'.' for i in chosen)
    text+=' Ces résultats doivent être interprétés dans les conditions des études présentées. Merci pour votre écoute.'
    return text,chosen

def definition_text(row):
    return 'Dans ce document, '+row['term']+' désigne '+row['definition']+'.'

def valid_question(question, idea, others):
    if not isinstance(question,str) or not question.strip() or not question.strip().endswith('?'):
        return False
    if words(question)>MAX_QUESTION_WORDS:return False
    if document_commentary(question):return False
    if re.search(r'\b(?:toujours|infaillible|garantir|garantit|garantie)\b|100\s*%|sans intervention',question,re.I):return False
    try:quality.french_text(question)
    except ValueError:return False
    # Une question ne doit pas introduire de nombre ni de sigle absent du point.
    source=idea['statement']+' '+idea.get('explanation','')
    source_numbers={n.replace(',','.') for n in re.findall(r'\d+(?:[.,]\d+)?',source)}
    if any(n.replace(',','.') not in source_numbers for n in re.findall(r'\d+(?:[.,]\d+)?',question)):return False
    measurements=r'(?<!\w)\d+(?:[.,]\d+)?\s*(?:%|mW|MW|dB|GHz|MHz|THz|nm|GB|km|ms)(?!\w)'
    measured=lambda text:{re.sub(r'\s+','',m).replace(',','.') for m in re.findall(measurements,text)}
    if measured(question)-measured(source):return False
    terms=quality.subject_symbols(question)
    if any(not re.search(r'\b'+re.escape(t)+r'\b',source) for t in terms):return False
    tokens=lambda t:{w for w in quality.definition_key(t).split() if len(w)>4}
    q=tokens(question);own=len(q & tokens(source))
    generic=tokens(' '.join(QUESTIONS.values())+' '+' '.join(q for options in QUESTION_VARIANTS.values() for q in options)+
        ' peux expliquer pourquoi comment quelle quelles serait serait-il cela cette cette-ci exemple précis préciser important importance')
    content=q-generic
    source_tokens=tokens(source)
    # Ce contrôle lexical repère les hors-sujets manifestes ; il ne valide pas
    # scientifiquement une question. Les variantes de flexion restent permises.
    if content and not any(a==b or (min(len(a),len(b))>=6 and a[:5]==b[:5])
                           for a in content for b in source_tokens):return False
    for other in others:
        if other['id']!=idea['id'] and len(q & tokens(passage(other)))>own+1:return False
    return True

def dialogue(pipe):
    plan,data,registry=checked_registry(pipe);explain=pipe.saved(7)
    if explain.get('workflow_version')!=VERSION:raise ValueError('Explications anciennes : reconstruire à partir de l’étape 5.')
    examples={i['idea_id']:i for c in explain['chapters'] for i in c['items']}
    for identity in plan['source_hashes']:
        entry=examples.get(identity)
        if not entry or entry['source_hash']!=source_hash(registry[identity]) or entry['text']!=passage(registry[identity]):
            raise ValueError('Explication désolidarisée de sa source : refaire l’étape 7. '+identity)
    speakers=pipe.config['speakers'];terms=definitions(data)
    memory={'explained_ideas':{},'definitions':{},'examples':[],'open_questions':[],'last_turns':[],'asked_questions':[]}
    chapters=[];memories=[];warnings=[]
    for c in plan['chapters']:
        def produce_chapter():
            local_memory=copy.deepcopy(memory);turns=[];issues=[]
            for start in range(0,len(c['idea_ids']),2):
                batch=[registry[i] for i in c['idea_ids'][start:start+2]]
                local={'F'+source_hash(i)[:10]:i for i in batch}
                payload={'chapter':{k:c[k] for k in ('id','title','role')},
                    'ideas':[{'ref':ref,'statement':i['statement'][:1000],'statement_is_excerpt':len(i['statement'])>1000,
                              'explanation':i.get('explanation','')[:1600],
                              'explanation_is_excerpt':len(i.get('explanation',''))>1600} for ref,i in local.items()],
                    'memory':{'last_turns':[{'speaker':t['speaker'],'text':t['text'][:240]} for t in local_memory['last_turns'][-2:]],
                              'explained_ideas':{k:v[:160] for k,v in list(local_memory['explained_ideas'].items())[-8:]},
                              'definitions':dict(list(local_memory['definitions'].items())[-6:]),
                              'recent_questions':local_memory['asked_questions'][-3:]},
                    'audience':pipe.config['audience']}
                def produce_block():
                    block_issues=[]
                    block_defined=set(local_memory['definitions'])
                    recent=local_memory['asked_questions'][-3:]
                    try:
                        value=pipe.client.ask('dialogue',payload,
                            '''Propose UNE QUESTION courte et neutre par référence, en français.
                            Le logiciel fournit les réponses à partir des sources : n'en écris pas.
                            Maximum 20 mots par question, terminée par ?. N'introduis ni chiffre,
                            ni dispositif, ni résultat absent de l'idée. Tiens compte du dernier
                            échange pour éviter une nouvelle introduction ou une redéfinition.
                            Structure : {"questions":{"REFERENCE":"question ?"}}.''',
                            lambda v:quality.validate_reference_map(v,'questions'),budget=600)
                        questions=value['questions']
                    except RECOVERABLE as error:
                        questions={};block_issues.append('Questions de secours : '+str(error)[:200])
                    if set(questions)-set(local):block_issues.append('Références étrangères ignorées dans les propositions de questions.')
                    result=[]
                    for n,(ref,idea) in enumerate(local.items()):
                        question=questions.get(ref)
                        if not valid_question(question,idea,list(registry.values())):
                            # La réparation reçoit une seule idée : aucun décalage de voisinage.
                            try:
                                single={**payload,'ideas':[payload['ideas'][n]]}
                                value=pipe.client.ask('dialogue',single,
                                    'Écris seulement une question neutre en français sur cette idée, sans fait nouveau. '
                                    '20 mots maximum, finissant par ?. Structure : {"questions":{"'+ref+'":"question ?"}}.',
                                    lambda v:quality.validate_reference_map(v,'questions'),budget=300)
                                question=value['questions'].get(ref)
                            except RECOVERABLE:
                                question=None
                        if not valid_question(question,idea,list(registry.values())):
                            question=neutral_question(c['role'],recent)
                            block_issues.append(idea['id']+' : question neutre de secours.')
                        elif quality.definition_key(question) in {quality.definition_key(q) for q in recent[-3:]}:
                            question=neutral_question(c['role'],recent)
                            block_issues.append(idea['id']+' : question répétée remplacée par une relance neutre.')
                        recent.append(question)
                        qspeaker=speakers[2] if len(speakers)==3 and (start+n)%2 else speakers[0]
                        result.append({'speaker':qspeaker,'text':question.strip(),'idea_ids':[],'kind':'question'})
                        defs=[d for d in fact_definitions(idea,terms) if (d['document']+':'+d['term']) not in block_defined]
                        for d in defs:
                            block_defined.add(d['document']+':'+d['term'])
                            result.append({'speaker':speakers[1],'text':definition_text(d),'idea_ids':[],
                                           'kind':'definition','glossary_source':d})
                        result.append({'speaker':speakers[1],'text':passage(idea),'idea_ids':[idea['id']],
                                       'kind':'source','source_hash':source_hash(idea)})
                    return {'turns':result,'warnings':block_issues}
                packet=pipe.unit(8,f"{c['id']}-B{start//2+1}",c['title']+' — échange '+str(start//2+1),
                    {'protocol':VERSION,'payload':payload,'sources':[source_hash(i) for i in batch],
                     'definitions':local_memory['definitions'],'glossary':plan['glossary_hash'],'question_limit':MAX_QUESTION_WORDS},
                    produce_block,lambda v:script_markdown([{'title':c['title'],'opening_transition':'','turns':v['turns']}],speakers))
                turns.extend(packet['turns']);issues.extend(packet['warnings'])
                for turn in packet['turns']:
                    if turn.get('kind')=='definition':
                        d=turn['glossary_source'];local_memory['definitions'][d['document']+':'+d['term']]=d['definition']
                    elif turn.get('kind')=='question':
                        local_memory['asked_questions']=(local_memory['asked_questions']+[turn['text']])[-3:]
                for idea in batch:local_memory['explained_ideas'][idea['id']]=idea['statement']
                local_memory['last_turns']=turns[-2:]
            opening=chapter_opening(c,plan,registry,not chapters)
            return {'id':c['id'],'title':c['title'],'opening_transition':opening,
                    'turns':turns,'memory':local_memory,'warnings':issues}
        packet=pipe.unit(8,c['id'],c['title'],{'protocol':VERSION,'chapter':c,
            'sources':[source_hash(registry[i]) for i in c['idea_ids']],'memory':memory,'glossary':plan['glossary_hash'],'question_limit':MAX_QUESTION_WORDS},
            produce_chapter,lambda v:script_markdown([v],speakers))
        pipe.validate_dialogue(packet,speakers,c['idea_ids'])
        memory=copy.deepcopy(packet['memory']);warnings.extend(packet['warnings'])
        chapters.append({k:copy.deepcopy(packet[k]) for k in ('id','title','opening_transition','turns')})
        memories.append({'chapter':c['id'],'memory':copy.deepcopy(memory)})
        from storage import write
        write(pipe.project/'memoire'/f"{c['id']}.json",memory)
    return {'workflow_version':VERSION,'chapters':chapters,'memories':memories,'warnings':warnings},script_markdown(chapters,speakers)

def script_markdown(chapters,speakers):
    lines=[]
    for c in chapters:
        lines+=['## '+c['title'],'','**'+speakers[0]+' :** '+c['opening_transition'],'']
        lines+=['**'+t['speaker']+' :** '+t['text']+'\n' for t in c['turns']]
    return '\n'.join(lines)

def review(pipe):
    plan,data,registry=checked_registry(pipe);draft=pipe.saved(8)
    if draft.get('workflow_version')!=VERSION:raise ValueError('Dialogue ancien : refaire les étapes 6 à 8.')
    chapters=copy.deepcopy(draft['chapters']);seen=[];issues=[]
    chapter_map={c['id']:c for c in plan['chapters']};terms=definitions(data)
    for c in chapters:
        if c.get('id') not in chapter_map:raise ValueError('Chapitre de dialogue inconnu.')
        pipe.validate_dialogue(c,pipe.config['speakers'],chapter_map[c['id']]['idea_ids'])
        expected_opening=chapter_opening(chapter_map[c['id']],plan,registry,c['id']==plan['chapters'][0]['id'])
        if c['opening_transition']!=expected_opening:raise ValueError('Le rappel du chapitre ne correspond plus aux idées vérifiées : refaire le dialogue.')
        for turn in c['turns']:
            if turn.get('kind')=='source':
                ids=turn['idea_ids']
                if len(ids)!=1 or ids[0] not in registry:raise ValueError('Référence de dialogue inconnue.')
                idea=registry[ids[0]]
                if turn.get('source_hash')!=source_hash(idea) or turn['text']!=passage(idea):
                    raise ValueError('Le dialogue modifie une idée source : reconstruire le chapitre. '+ids[0])
                glossary={term:entries for doc in data.get('documents',[]) if doc['id']==idea.get('document') for term,entries in doc.get('glossary',{}).items()}
                quality.validate_acronyms(turn['text'],glossary)
                quality.validate_technical_wording(turn['text'],' '.join(e['quote'] for e in idea.get('evidence',[])))
                if quality.unusable_fact_text(turn['text']):raise ValueError('Commentaire de document encore présent : réexaminer cette idée source. '+ids[0])
                seen.extend(ids)
            elif turn.get('kind')=='definition':
                d=turn.get('glossary_source',{});source=terms.get((d.get('document'),d.get('term')))
                if source!=d or turn['text']!=definition_text(source):raise ValueError('Définition différente du lexique source.')
            elif turn.get('kind')!='question' or turn['idea_ids']:
                raise ValueError('Réplique non rattachée au contrat de contenu source.')
    expected=[i for c in plan['chapters'] for i in c['idea_ids']]
    if len(seen)!=len(set(seen)) or set(seen)!=set(expected):raise ValueError('Le dialogue doit traiter toutes les idées affectées à ce chapitre.')
    speakers=pipe.config['speakers']
    conclusion,recap_ids=closing_text(plan,registry)
    chapters[-1]['turns'].append({'speaker':speakers[0],'text':conclusion,'idea_ids':[],
                                 'kind':'closing','recap_ids':recap_ids})
    plain='\n\n'.join(speakers[0]+' : '+c['opening_transition']+'\n\n'+'\n\n'.join(t['speaker']+' : '+t['text'] for t in c['turns']) for c in chapters)
    count=sum(words(c['opening_transition'])+sum(words(t['text']) for t in c['turns']) for c in chapters)
    target=pipe.config['minutes']*145
    warnings=data.get('classification_warnings',[])+plan.get('warnings',[])+draft.get('warnings',[])
    duration_warning=not .75*target<=count<=1.15*target
    if duration_warning:issues.append({'chapter':'ensemble','note':'Durée à ajuster : matière source et durée cible ne coïncident pas encore.'})
    result={'workflow_version':VERSION,'chapters':chapters,'issues':issues,'covered_idea_ids':sorted(seen),
        'source_quality':quality.VERSION,'content_checks_passed':True,
        'source_registry':[copy.deepcopy(registry[i]) for i in expected],
        'source_glossaries':copy.deepcopy(data.get('documents',[])),
        'expected_idea_ids':sorted(expected),'all_planned_ids_present':True,'source_texts_preserved':True,
        'excluded_ideas':plan['exclusions'],'source_uncertainties':data.get('source_uncertainties',[]),
        'generation_warnings':warnings,'synthesis_warnings':[],'word_count':count,
        'estimated_minutes':round(count/145,1),'target_minutes':pipe.config['minutes'],
        'duration_warning':duration_warning,'markdown':script_markdown(chapters,speakers),'plain_text':plain,
        'note':'Les réponses conservent les formulations sources retenues. Leur fidélité scientifique et la qualité pédagogique nécessitent une relecture humaine.'}
    result['selected_count']=len(expected);result['registry_count']=len(registry)
    source1=pipe.project/'etapes/01.json'
    result['source_coverage']=[{'document':d['id'],'unreadable_pages':d.get('empty_pages',[])}
        for d in read(source1)['data']['documents']] if source1.exists() else []
    notes=result['markdown']+'\n\n## Rapport de révision\n\n'+str(count)+' mots — environ '+str(result['estimated_minutes'])+' minutes.\n\n'+result['note']
    if issues:notes+='\n\n'+'\n'.join('- '+i['note'] for i in issues)
    if warnings:notes+='\n\n### Points à relire\n\n'+'\n'.join('- '+w for w in warnings)
    if plan['exclusions']:notes+='\n\n### Idées hors dialogue, conservées au dossier\n\n'+'\n'.join('- '+e['idea_id']+' : '+e['reason'] for e in plan['exclusions'])
    for entry in result['source_coverage']:
        if entry['unreadable_pages']:notes+='\n\nPages sans texte extractible dans '+entry['document']+' : '+', '.join(map(str,entry['unreadable_pages']))+'. Leur contenu visuel reste à examiner.'
    return result,notes
