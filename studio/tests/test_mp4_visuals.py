"""Allumage des cartes, portrait intégré et aperçu du prochain plan."""
import base64
from io import BytesIO
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mp4_visuals import Visuals, plan_state, portrait_state


class VisualTests(unittest.TestCase):
    def test_flash_sustained_light_and_pause(self):
        intervals = [{'character':'voice:0','start':2.,'end':2.6,'reviewed':True},
                     {'character':'voice:0','start':2.7,'end':3.,'reviewed':False}]
        for t, opacity, caption in [(.4,.35,None),(.625,1.,'À vous · Bientôt'),
                                    (.875,.35,'À vous · Bientôt'),(2.1,1.,'À vous'),
                                    (2.625,1.,'À vous · Bientôt'),(2.8,1.,'À vous ?'),(3.,.35,None)]:
            self.assertEqual(portrait_state(intervals,'voice:0',t,{'voice:0'}),(opacity,caption))
        self.assertEqual(portrait_state(intervals,'voice:0',2.1,set()),(1.,'Film'))

    def test_corrected_plan_times_and_flash(self):
        cuts = [{'time':1.}]
        self.assertEqual(plan_state(cuts,.4),(cuts[0],.35,'Prochain plan'))
        self.assertEqual(plan_state(cuts,.625),(cuts[0],1.,'Plan imminent'))
        self.assertEqual(plan_state(cuts,.875),(cuts[0],.35,'Plan imminent'))
        self.assertEqual(plan_state(cuts,1.1),(cuts[0],1.,'Changement de plan'))
        self.assertEqual(plan_state(cuts,1.25),(None,0,''))

    def test_photo_and_opacity_in_pixels(self):
        import numpy as np
        from PIL import Image
        photo = BytesIO()
        Image.new('RGB',(100,100),'red').save(photo,format='JPEG')
        person = {'id':'voice:0','label':'Élodie','color':'#ff6500','photo':base64.b64encode(photo.getvalue()).decode()}
        edits = {'characters':[person], 'cuts':[], 'intervals':[{'character':'voice:0','start':2.,'end':3.,'reviewed':True}],
                 'audioMix':{'removedCharacters':['voice:0']}}
        visuals = Visuals({'characters':[person]},edits,640,360)
        class NoPreview:
            def set(self,*args):
                raise AssertionError('Pas de plan dans cette scène')
        frame = np.zeros((360,640,3),dtype=np.uint8)
        def pixels(t):
            return np.frombuffer(visuals.draw(frame,t,NoPreview()),dtype=np.uint8).reshape(360,640,3)
        bright, dim = pixels(.625), pixels(.875)
        x, y = 640-round(640*.015)-visuals.size+10,360-48-visuals.size+10
        self.assertGreater(bright[y,x,0],240)  # photo rouge, pas un symbole de voix
        self.assertLess(bright[y,x,1],10)
        self.assertGreater(dim[y,x,0],70)
        self.assertLess(dim[y,x,0],100)
        self.assertTrue(np.array_equal(bright[y,x],pixels(2.1)[y,x]))


if __name__ == '__main__':
    unittest.main()
