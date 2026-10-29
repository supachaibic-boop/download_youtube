import importlib.util
import json
import os
import shutil
import subprocess
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler
from unittest.mock import patch
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError

os.environ['API_TOKEN']='test-only-token-abcdefghijklmnopqrstuvwxyz'
TMP=tempfile.TemporaryDirectory()
os.environ['DATA_DIR']=TMP.name
spec=importlib.util.spec_from_file_location('vault',Path(__file__).parents[1]/'server/app.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class API(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a.init_db();cls.server=a.ThreadingHTTPServer(('127.0.0.1',0),a.Handler)
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown();cls.server.server_close();TMP.cleanup()
    def req(self,path,body=None,auth=True):
        headers={'Content-Type':'application/json'}
        if auth: headers['Authorization']='Bearer '+a.TOKEN
        r=Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urlopen(r) as res: return res.status,json.load(res)
        except HTTPError as e: return e.code,json.load(e)
    def create(self,fmt='mp4'):
        code,d=self.req('/api/jobs',{'url':'https://youtu.be/BaW_jenozKc','format':fmt,'quality':720,'mode':'download'})
        self.assertEqual(code,201);return d['id']
    def test_auth_and_health(self):
        self.assertEqual(self.req('/api/jobs',auth=False)[0],401)
        code,d=self.req('/api/health');self.assertEqual(code,200);self.assertTrue(d['ok'])
        self.assertTrue(a.DB.exists())
    def test_urls(self):
        for url in ['http://youtube.com/watch?v=BaW_jenozKc','https://youtube.com.evil.org/watch?v=BaW_jenozKc','https://localhost/a','https://youtube.com/playlist?list=abc','https://youtube.com:444/watch?v=BaW_jenozKc']:
            self.assertEqual(self.req('/api/jobs',{'url':url})[0],400)
        self.assertEqual(a.normalize_url('https://www.youtube.com/shorts/BaW_jenozKc'),'https://www.youtube.com/watch?v=BaW_jenozKc')
    def test_worker_completion_file_link_and_events(self):
        id=self.create()
        with a.connect() as c: job=dict(c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone())
        class FakeYDL:
            def __init__(self,opts): self.opts=opts
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def extract_info(self,url,download):
                self.opts['progress_hooks'][0]({'status':'downloading','downloaded_bytes':4,'total_bytes':4,'info_dict':{'title':'วิดีโอทดสอบ'}})
                self.opts['progress_hooks'][0]({'status':'finished','info_dict':{'title':'วิดีโอทดสอบ'}})
                (a.MEDIA/id/'ทดสอบ.mp4').write_bytes(b'test-media')
                return {'title':'วิดีโอทดสอบ'}
        old=sys.modules.get('yt_dlp');sys.modules['yt_dlp']=types.SimpleNamespace(YoutubeDL=FakeYDL)
        try: a.download_job(job)
        finally:
            if old: sys.modules['yt_dlp']=old
            else: sys.modules.pop('yt_dlp',None)
        rows=self.req('/api/jobs')[1]['jobs'];j=next(j for j in rows if j['id']==id)
        self.assertEqual(j['status'],'completed');self.assertEqual(j['size_bytes'],10)
        path=self.req('/api/jobs/'+id+'/file-link')[1]['path']
        with urlopen(self.url+path) as res: self.assertEqual(res.read(),b'test-media')
        self.assertEqual(self.req('/files/'+id+'?expires=9999999999&sig=fake')[0],403)
        self.assertGreaterEqual(len(self.req('/api/jobs/'+id+'/events')[1]['events']),3)
        self.assertEqual(self.req('/api/jobs/'+id+'/retry',{})[0],409)
    def test_failed_retry_and_restart(self):
        id=self.create('mp3');a.update(id,status='failed',error='test failure')
        self.assertEqual(self.req('/api/jobs/'+id+'/retry',{})[0],200)
        a.update(id,status='downloading');a.init_db()
        with a.connect() as c: self.assertEqual(c.execute('SELECT status FROM jobs WHERE id=?',(id,)).fetchone()[0],'queued')
        self.assertEqual(self.req('/api/jobs/'+id+'/file-link')[0],404)

    def test_record_mode_default_and_validation(self):
        code, result = self.req('/api/jobs', {'url':'https://youtu.be/BaW_jenozKc'})
        self.assertEqual(code, 201)
        jobs = self.req('/api/jobs')[1]['jobs']
        self.assertEqual(next(j for j in jobs if j['id']==result['id'])['mode'], 'record')
        self.assertEqual(self.req('/api/jobs', {'url':'https://youtu.be/BaW_jenozKc', 'mode':'bad'})[0],400)
        a.update(result['id'],status='recording')
        a.init_db()
        jobs=self.req('/api/jobs')[1]['jobs']
        self.assertEqual(next(j for j in jobs if j['id']==result['id'])['status'],'queued')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg is not installed')
    def test_real_background_recording_mp4_mp3_and_truncation(self):
        # Actual FFmpeg, HTTP delivery and ffprobe; only YouTube URL resolution is mocked.
        with tempfile.TemporaryDirectory() as root:
            fixture=Path(root)/'source.mp4'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                            '-f','lavfi','-i','color=c=blue:s=96x64:r=10',
                            '-f','lavfi','-i','sine=frequency=440:sample_rate=44100',
                            '-t','3','-c:v','mpeg4','-c:a','aac','-movflags','+faststart',str(fixture)],check=True)
            class Quiet(SimpleHTTPRequestHandler):
                def log_message(self,*args): pass
            server=a.ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=root))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                url='http://127.0.0.1:'+str(server.server_port)+'/source.mp4'
                for fmt in ('mp4','mp3'):
                    with self.subTest(format=fmt):
                        id=self.create(fmt)
                        a.update(id,mode='record')
                        with a.connect() as c:
                            job=dict(c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone())
                        info={'url':url,'duration':3,'title':'Background recording test',
                              'acodec':'aac','vcodec':'mpeg4','ext':'mp4'}
                        if fmt == 'mp4':
                            info['requested_formats'] = [{'url':url,'vcodec':'mpeg4','acodec':'none'},
                                                         {'url':url,'vcodec':'none','acodec':'aac'}]
                        class Resolver:
                            def __init__(self,opts): pass
                            def __enter__(self): return self
                            def __exit__(self,*args): pass
                            def prepare_filename(self,info): return str(a.MEDIA/id/'record.mp4')
                            def extract_info(self,url,download):
                                if download: raise AssertionError('Recording must not call direct download')
                                return info
                        started=time.monotonic()
                        with patch.dict(sys.modules,{'yt_dlp':types.SimpleNamespace(YoutubeDL=Resolver)}):
                            a.download_job(job)
                        self.assertGreaterEqual(time.monotonic()-started,2)
                        j=next(j for j in self.req('/api/jobs')[1]['jobs'] if j['id']==id)
                        self.assertEqual(j['status'],'completed')
                        self.assertEqual(j['progress'],100)
                        self.assertGreater(j['size_bytes'],500)
                        probe=subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',j['storage_path']],capture_output=True,text=True,check=True)
                        types_found={s['codec_type'] for s in json.loads(probe.stdout)['streams']}
                        self.assertIn('audio',types_found)
                        self.assertEqual('video' in types_found,fmt=='mp4')
                id=self.create()
                (a.MEDIA/id).mkdir(exist_ok=True)
                with self.assertRaisesRegex(RuntimeError,'สตรีมจบก่อนครบ'):
                    a.record_stream({'id':id,'format':'mp4','title':'test'},
                                    {'url':url,'duration':30,'vcodec':'mpeg4','acodec':'aac'},
                                    a.MEDIA/id/'truncated.mp4')
                self.assertFalse((a.MEDIA/id/'truncated.mp4').exists())
            finally:
                server.shutdown();server.server_close()

if __name__=='__main__': unittest.main(verbosity=2)
