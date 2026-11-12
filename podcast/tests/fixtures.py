"""PDF réel et fournisseur simulé, réservés aux tests (jamais au produit)."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading


def make_pdf(path, label='Optique', page_count=3):
    objects=[]
    def add(value):
        objects.append(value);return len(objects)
    add(b'<< /Type /Catalog /Pages 2 0 R >>')
    add(b'')
    add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    pages=[]
    for n in range(1,page_count+1):
        sentence=f'{label} page {n}. Le signal perd de la puissance dans la fibre. Un amplificateur peut compenser les pertes. Il faut aussi comprendre les limites du dispositif.'
        stream=('BT /F1 12 Tf 50 750 Td ('+sentence+') Tj ET').encode('ascii')
        content=add(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
        page=add(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content} 0 R >>'.encode())
        pages.append(page)
    objects[1]=(f'<< /Type /Pages /Count {page_count} /Kids ['+' '.join(f'{p} 0 R' for p in pages)+'] >>').encode()
    data=bytearray(b'%PDF-1.4\n');offsets=[0]
    for n,obj in enumerate(objects,1):
        offsets.append(len(data));data.extend(f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(data);data.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:data.extend(f'{offset:010} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
    path.write_bytes(data)
    return path


def answer(task,p):
    if task=='part_summary':
        pages=sorted({b['page'] for b in p['blocks']})
        return {'summary':'Le signal s’atténue ; une amplification compense une partie des pertes.',
                'ideas':[{'statement':'Le signal s’atténue dans la fibre.','explanation':'Les pertes réduisent la puissance disponible.','pages':pages},
                         {'statement':'Une amplification compense les pertes.','explanation':'Le dispositif possède des limites à étudier.','pages':pages}]}
    if task=='pdf_synthesis':return {'text':'Les trois parties relient les pertes, leur compensation et les limites.'}
    if task=='review_facts':
        return {'decisions':{i['id']:{'statement':i['statement'],'explanation':i['explanation'],
                        'evidence':[p['source_text'][:100]],'status':'kept','reason':'Appui simulé pour le test.'}
                       for i in p['candidates']}}
    if task=='fact_support':return {'verdicts':{i['ref']:{'status':'supported','reason':'Appui sémantique simulé pour ce test.'} for i in p['facts']}}
    if task=='common_paragraphs':return {'paragraphs':{i['ref']:i['statement']+' '+i.get('explanation','') for i in p['ideas']}}
    if task=='explanation_paragraphs':return {'transition':'Nous avons vu les pertes ; étudions maintenant leur compensation.',
        'paragraphs':{i['ref']:i['statement']+' '+i.get('explanation','') for i in p['ideas']}}
    if task=='part_structure':
        items=p['elements']
        return {'problem':'Comprendre les pertes de signal.',
                'concepts':' '.join(i.get('statement',i.get('concepts','')) for i in items),
                'methods':'Étudier les moyens de compensation.',
                'results':'Les sources précisent les effets observés.','limits':'Les dispositifs ont des limites à examiner.'}
    if task=='global_groups':
        cut=max(1,len(p['ideas'])//2)
        return {'assignments':{i['ref']:'Comprendre les pertes' if n<cut else 'Compenser les pertes' for n,i in enumerate(p['ideas'])}}
    if task=='global_text':return {'text':' '.join(i['statement']+' ['+i['id']+']' for i in p['ideas'])}
    if task in ('plan','plan_groups'):
        import math
        groups=p['groups']
        if task=='plan_groups':
            size=max(1,math.ceil(len(groups)/20))
            groups=[{'title':groups[n]['title'],'group_ids':[g['id'] for g in groups[n:n+size]]} for n in range(0,len(groups),size)]
        return {'central_question':'Comment transmettre un signal plus loin ?', 'chapters':[{'id':f'C{n}','title':g['title'],'question':'Pourquoi ces phénomènes ?',
                'known':'Les points précédents.','new':'Les relations de cause à effet.','why_next':'Étudier la suite du raisonnement.',
                **({'group_ids':g['group_ids']} if task=='plan_groups' else {'idea_ids':g['idea_ids']}),
                'target_words':400} for n,g in enumerate(groups,1)],'exclusions':[]}
    if task=='key_sentences':return {'sentences':{i['ref']:i['statement'] for i in p['ideas']}}
    if task=='explanation':return {'transition':'Nous avons posé le problème ; voyons comment le résoudre.','text':' '.join(i['statement']+' ['+i['id']+']' for i in p['ideas'])}
    if task=='dialogue':
        return {'opening_transition':'Nous avons vu les pertes ; étudions maintenant leur compensation.',
                'turns':[{'speaker':p['speakers'][n%len(p['speakers'])],'text':i['statement'],'idea_ids':[i['id']]} for n,i in enumerate(p['ideas'])],
                'memory_update':{'definitions':{p['chapter']['id']:'Définition déjà expliquée.'},'examples':['Exemple '+p['chapter']['id']],'open_questions':['Quelle est la suite ?']}}
    if task=='review':return {'opening_transition':p['draft']['opening_transition'],'turns':p['draft']['turns'],'issues':['Contrôle technique simulé pour le test.']}
    raise ValueError(task)


class FakeClient:
    def __init__(self,config=None,cache=None,cancelled=None,progress=None):
        self.cancelled=cancelled or threading.Event();self.calls=[]
    def cancel(self):self.cancelled.set()
    def ask(self,task,payload,instructions,validate,budget=4000):
        self.calls.append((task,json.loads(json.dumps(payload))))
        value=answer(task,payload);validate(value);return value


class StubHandler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*_):pass
    def do_GET(self):
        data=json.dumps({'models':[{'name':'mistral:test'}]}).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        prompt=request['messages'][1]['content']
        task=prompt.splitlines()[0].split(':',1)[1].strip()
        payload=json.loads(prompt.split('DONNÉES :\n',1)[1])
        self.server.calls.append((task,payload))
        self.server.requests.append(request)
        result=json.dumps(answer(task,payload),ensure_ascii=False)
        status=200
        events=[{'message':{'content':result},'done':False},{'message':{'content':''},'done':True,'done_reason':'stop'}]
        if self.server.responses:
            status,events=self.server.responses.pop(0)
        if self.server.fail_on and task==self.server.fail_on[0] and payload.get('chapter',{}).get('id')==self.server.fail_on[1]:
            self.server.fail_on=None;status=500;events=[{'error':'Echec de chapitre simulé'}]
        data=('\n'.join(json.dumps(e) for e in events)+'\n').encode()
        self.send_response(status);self.send_header('Content-Type','application/x-ndjson')
        self.send_header('Content-Length',str(len(data)+(1000000 if self.server.stall else 0)));self.end_headers()
        if self.server.stall:
            self.wfile.write(b'{"message":{"content":""},"done":false}\n');self.wfile.flush()
            self.server.started.set();self.server.release.wait(10)
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass


class StubServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self):
        self.calls=[];self.requests=[];self.responses=[];self.fail_on=None
        self.stall=False;self.started=threading.Event();self.release=threading.Event()
        super().__init__(('127.0.0.1',0),StubHandler)
        self.thread=threading.Thread(target=self.serve_forever,daemon=True);self.thread.start()
        self.endpoint=f'http://127.0.0.1:{self.server_port}'
    def close(self):
        self.release.set();self.shutdown();self.server_close();self.thread.join()
