import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_html import SCHEMA
from projet_local import Projet
from application import Application


def document():
    interval={'id':'e1','start':.1,'end':.8,'character':'voice:0','reviewed':False}
    return {'schema':SCHEMA,'analysis_id':'test-project','source_sha256':'a'*64,'duration':1.,
            'characters':[{'id':'voice:0','label':'Personnage','color':'#ff6500','photo':None}],
            'initial':[interval],'initialCuts':[],'automatic':[copy.deepcopy(interval)],'automaticCuts':[],
            'audioMix':{'removedCharacters':[],'keepAmbience':True,'keepUnknown':True},'peaks':[0,1],
            'media':'data:video/mp4;base64,AAAA','improMedia':'data:video/mp4;base64,AAAA','title':'Essai'}


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.project=Projet.create(self.folder/'scene',document())

    def tearDown(self):
        self.temp.cleanup()

    def test_reopen_preserves_manual_edits_mix_and_automatic_baseline(self):
        edits=copy.deepcopy(self.project.edits)
        edits['intervals'][0].update(start=.2,reviewed=True)
        edits['audioMix']['removedCharacters']=['voice:0']
        self.project.save(edits)
        reopened=Projet(self.project.path)
        data=reopened.document()
        self.assertEqual(data['initial'][0]['start'],.2)
        self.assertTrue(data['initial'][0]['reviewed'])
        self.assertEqual(data['automatic'][0]['start'],.1)
        self.assertEqual(data['audioMix']['removedCharacters'],['voice:0'])
        self.assertEqual(json.loads((self.project.folder/'corrections-precedentes.json').read_text())['intervals'][0]['start'],.1)
        self.assertEqual(self.project._document['initial'][0]['start'],.1)

    def test_invalid_or_failed_save_does_not_overwrite_previous_work(self):
        path=self.project.folder/'corrections.json'
        previous=path.read_bytes()
        edits=copy.deepcopy(self.project.edits)
        edits['source_sha256']='wrong'
        with self.assertRaises(ValueError):self.project.save(edits)
        self.assertEqual(path.read_bytes(),previous)
        edits=copy.deepcopy(self.project.edits)
        edits['intervals'][0]['start']=.25
        with patch('projet_local.ecrire_json',side_effect=OSError('Disque plein')):
            with self.assertRaises(OSError):self.project.save(edits)
        self.assertEqual(path.read_bytes(),previous)
        self.assertEqual(self.project.document()['initial'][0]['start'],.1)

    def test_existing_project_not_replaced(self):
        with self.assertRaises(ValueError):Projet.create(self.project.folder,document())

    def test_two_windows_cannot_overwrite_the_same_project(self):
        other=Projet(self.project.path)
        self.project.acquire()
        try:
            with self.assertRaisesRegex(ValueError,'déjà ouvert'):other.acquire()
        finally:
            self.project.release()
        other.acquire()
        other.release()

    def test_corrupted_corrections_are_reported(self):
        (self.project.folder/'corrections.json').write_text('{}')
        with self.assertRaises(ValueError):Projet(self.project.path)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.app=Application()
        self.app._destination=self.folder/'projets'
        class Window:
            def __init__(self):self.urls=[]
            def load_url(self,url):self.urls.append(url)
        self.app._window=Window()

    def tearDown(self):
        self.app.cleanup()
        self.temp.cleanup()

    def test_old_html_import_reads_data_without_running_its_scripts_or_analysis(self):
        source=self.folder/'ancien.html'
        source.write_text('<script>throw Error("ne jamais exécuter")</script><script id="editor-data" type="application/json">'+json.dumps(document())+'</script>')
        with patch.object(self.app,'_choose',side_effect=[str(source),str(self.folder)]),patch('lancer_studio.traiter',side_effect=AssertionError('Analyse interdite')):
            self.app.import_editor()
        project=self.app._project
        self.assertTrue(project.path.exists())
        self.assertTrue(self.app._window.urls[-1].startswith('file:///'))
        html=Path(self.app._ui/'editeur.html').read_text()
        self.assertIn('DOUBALGE_DESKTOP',html)
        self.assertNotIn('ne jamais exécuter',html)
        edits=copy.deepcopy(project.edits)
        edits['intervals'][0]['start']=.3
        session=self.app._session
        self.app.save_project(session,edits)
        self.assertEqual(Projet(project.path).edits['intervals'][0]['start'],.3)
        with self.assertRaises(ValueError):self.app.save_project('ancienne-session',edits)

    def test_cancelled_mp4_does_not_replace_destination(self):
        project=Projet.create(self.folder/'scene',document())
        self.app._editor(project)
        destination=self.folder/'entrainement.mp4'
        destination.write_bytes(b'previous-video')
        edits=copy.deepcopy(project.edits)
        edits['audioMix']['removedCharacters']=['voice:0']
        def render(*args):
            self.app._cancel.wait(5)
            from export_mp4 import Cancelled
            raise Cancelled()
        with patch.object(self.app,'_choose',return_value=str(destination)),patch('application.render',side_effect=render):
            self.app.start_export(self.app._session,{'edits':edits,'profile':'mail'})
            self.app.cancel_job()
            self.app._worker.join(5)
        self.assertEqual(self.app.job_status()['status'],'cancelled')
        self.assertEqual(destination.read_bytes(),b'previous-video')

    def test_destination_changes_only_through_explicit_folder_button(self):
        initial=self.app.preparation_settings()['destination']
        with patch.object(self.app,'_choose',return_value=None):
            self.assertEqual(self.app.choose_destination()['destination'],initial)
        parent=self.folder/'destination-personnalisee'
        with patch.object(self.app,'_choose',return_value=str(parent)) as choose:
            self.assertEqual(self.app.choose_destination()['destination'],str(parent.resolve()))
            self.assertEqual(choose.call_args.args[0],'folder')
        self.assertFalse(parent.exists())

    def test_running_window_reports_version_and_installation_path(self):
        info=self.app.release_info()
        self.assertEqual(info['version'],'2026.11.02.2')
        self.assertTrue((Path(info['folder'])/'studio'/'application.py').exists())

    def test_changed_files_require_restart_before_preparation(self):
        with patch('application._LOADED_CODE','ancienne-version'),patch.object(self.app,'_choose',side_effect=AssertionError('Pas de dialogue')):
            with self.assertRaisesRegex(ValueError,'Fermez cette fenêtre'):
                self.app.prepare({'source':'https://www.youtube.com/watch?v=test'})
        self.assertEqual(self.app.job_status()['status'],'idle')
        self.assertFalse(self.app._destination.exists())

    def test_automatic_worker_without_source_never_opens_legacy_dialog(self):
        import subprocess
        worker=Path(__file__).resolve().parents[1]/'lancer_studio.py'
        result=subprocess.run([sys.executable,str(worker),'--sans-ouvrir'],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Aucun sélecteur ne sera ouvert',result.stderr)

    def test_default_destination_is_project_folder_without_dialog(self):
        with patch('application.ROOT',self.folder):
            other=Application()
        try:
            self.assertEqual(other.preparation_settings()['destination'],str(self.folder/'projets'))
            self.assertFalse((self.folder/'projets').exists())
        finally:
            other.cleanup()

    def test_preparation_keeps_supplied_json_and_opens_new_project(self):
        corrected=self.folder/'corrige.json'
        corrected.write_text(json.dumps(document()))
        self.app._approved['corrections']=str(corrected)
        calls=[]
        class Process:
            def __init__(self,command,**kwargs):
                calls.append(command)
                output=Path(command[command.index('--sortie')+1]);output.mkdir()
                (output/'OSS-editeur.html').write_text('<script id="editor-data" type="application/json">'+json.dumps(document())+'</script>')
                self.stdout=iter(['[analyse] Corrections manuelles réutilisées\n'])
            def wait(self):return 0
        with patch.object(self.app,'_choose',side_effect=AssertionError('Aucun dialogue pour une URL')),patch('application.subprocess.Popen',Process):
            self.app.prepare({'source':'https://www.youtube.com/watch?v=test','corrections':str(corrected)})
            self.app._worker.join(5)
        self.assertEqual(self.app.job_status()['status'],'done')
        self.assertIn('--sans-ouvrir',calls[0])
        self.assertEqual(calls[0][calls[0].index('--video')+1],'https://www.youtube.com/watch?v=test')
        self.assertTrue(Path(calls[0][calls[0].index('--sortie')+1]).is_relative_to(self.app._destination))
        self.assertEqual(calls[0][calls[0].index('--corrections')+1],str(corrected))
        self.app.open_prepared()
        self.assertEqual(self.app._project.document()['analysis_id'],'test-project')
        self.assertTrue(self.app._window.urls[-1].startswith('file:///'))


if __name__=='__main__':unittest.main()
