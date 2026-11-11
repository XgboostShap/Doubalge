"""Régression des accès refusés WinError 5/32 et lectures concurrentes."""
import errno
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import storage


def locked(code=5):
    error=PermissionError(errno.EACCES,'Accès refusé pendant une lecture')
    error.winerror=code
    return error


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'tache.json'
        storage.write(self.path,{'state':'running'})
    def tearDown(self):self.temp.cleanup()

    def test_windows_transient_replace_retries_without_deleting_previous_file(self):
        original_replace=os.replace
        for code in (5,32,33):
            attempts=[]
            before=self.path.read_bytes()
            def operation(source,target):
                attempts.append(1)
                if len(attempts)<=2:
                    self.assertEqual(self.path.read_bytes(),before)
                    # Il existe déjà une nouvelle sauvegarde complète et fermée.
                    self.assertEqual(json.loads(Path(source).read_text()),{'state':'done','code':code})
                    raise locked(code)
                return original_replace(source,target)
            with self.subTest(winerror=code),patch('storage.os.replace',side_effect=operation),patch('storage.time.sleep'):
                storage.write(self.path,{'state':'done','code':code})
            self.assertEqual(storage.read(self.path),{'state':'done','code':code})
            self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_permanent_failure_preserves_original_and_cleans_temporary_file(self):
        before=self.path.read_bytes()
        with patch('storage.os.replace',side_effect=locked()),patch('storage.time.sleep'):
            with self.assertRaises(PermissionError):storage.write(self.path,{'state':'done'})
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_unrelated_io_failure_is_not_retried(self):
        with patch('storage.os.replace',side_effect=OSError(errno.ENOSPC,'Disque plein')) as operation,patch('storage.time.sleep') as sleep:
            with self.assertRaises(OSError):storage.write(self.path,{'state':'done'})
        self.assertEqual(operation.call_count,1);sleep.assert_not_called()
        self.assertEqual(storage.read(self.path),{'state':'running'})

    def test_invalid_json_value_leaves_existing_file_intact(self):
        with self.assertRaises(ValueError):storage.write(self.path,{'number':float('nan')})
        self.assertEqual(storage.read(self.path),{'state':'running'})
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_read_sharing_error_retries(self):
        original=Path.read_text;attempts=[]
        def operation(path,*args,**kwargs):
            if path==self.path:
                attempts.append(1)
                if len(attempts)==1:raise locked(32)
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',operation),patch('storage.time.sleep'):
            self.assertEqual(storage.read(self.path),{'state':'running'})
        self.assertEqual(len(attempts),2)

    def test_writer_waits_until_reader_has_closed_the_file(self):
        original_read=Path.read_text;original_replace=os.replace
        reading=threading.Event();release=threading.Event();writing=threading.Event();replaced=threading.Event();errors=[]
        def read_text(path,*args,**kwargs):
            if path==self.path:
                reading.set()
                if not release.wait(3):raise RuntimeError('Lecteur bloqué')
                result=original_read(path,*args,**kwargs);reading.clear();return result
            return original_read(path,*args,**kwargs)
        def replace(source,target):
            if reading.is_set():raise locked()
            result=original_replace(source,target);replaced.set();return result
        def reader():
            try:storage.read(self.path)
            except Exception as error:errors.append(error)
        def writer():
            writing.set()
            try:storage.write(self.path,{'state':'done'})
            except Exception as error:errors.append(error)
        with patch.object(Path,'read_text',read_text),patch('storage.os.replace',side_effect=replace):
            a=threading.Thread(target=reader);b=threading.Thread(target=writer)
            try:
                a.start();self.assertTrue(reading.wait(2));b.start();self.assertTrue(writing.wait(2))
                self.assertFalse(replaced.wait(.05))
            finally:
                release.set();a.join(3);b.join(3)
        self.assertFalse(a.is_alive());self.assertFalse(b.is_alive());self.assertFalse(errors,errors)
        self.assertEqual(storage.read(self.path),{'state':'done'})

    def test_archiving_retries_a_windows_sharing_violation(self):
        original=os.replace;attempts=[];destination=self.path.parent/'archive.json'
        def replace(source,target):
            attempts.append(1)
            if len(attempts)==1:raise locked(32)
            return original(source,target)
        with patch('storage.os.replace',side_effect=replace),patch('storage.time.sleep'):
            storage.replace(self.path,destination)
        self.assertFalse(self.path.exists());self.assertEqual(storage.read(destination),{'state':'running'})


if __name__=='__main__':unittest.main()
