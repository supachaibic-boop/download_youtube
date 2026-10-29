"""Single-process, single-worker YouTube download manager. Python 3.11+."""
import collections
import subprocess
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, urlencode

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('DATA_DIR', ROOT / 'data')).resolve()
MEDIA = DATA / 'downloads'
DB = DATA / 'vault.sqlite3'
TOKEN = os.environ.get('API_TOKEN', '')
ORIGINS = set(filter(None, os.environ.get('ALLOWED_ORIGINS', '').split(',')))
STOP = threading.Event()

def now(): return datetime.now(timezone.utc).isoformat()

def connect():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    MEDIA.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL,
          format TEXT NOT NULL, quality INTEGER NOT NULL, status TEXT NOT NULL,
          progress REAL NOT NULL DEFAULT 0, downloaded_bytes INTEGER DEFAULT 0,
          total_bytes INTEGER DEFAULT 0, speed REAL DEFAULT 0, eta INTEGER,
          filename TEXT, storage_path TEXT, size_bytes INTEGER DEFAULT 0,
          error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
          status TEXT NOT NULL, message TEXT, created_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at);
          CREATE INDEX IF NOT EXISTS events_job ON events(job_id);''')
        columns = {r[1] for r in c.execute('PRAGMA table_info(jobs)')}
        for name, definition in [('mode', "TEXT NOT NULL DEFAULT 'download'"),
                                 ('duration_seconds', 'REAL NOT NULL DEFAULT 0'),
                                 ('recorded_seconds', 'REAL NOT NULL DEFAULT 0')]:
            if name not in columns:
                c.execute(f'ALTER TABLE jobs ADD COLUMN {name} {definition}')
        c.execute("UPDATE jobs SET status='queued', error=NULL WHERE status IN ('extracting','downloading','recording','processing')")

def update(job_id, **fields):
    fields['updated_at'] = now()
    with connect() as c:
        c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?', [*fields.values(), job_id])
        if 'status' in fields:
            c.execute('INSERT INTO events(job_id,status,message,created_at) VALUES(?,?,?,?)',
                      (job_id, fields['status'], fields.get('error'), now()))

def normalize_url(raw):
    try:
        p = urlsplit(raw.strip())
        if p.scheme != 'https' or p.username or p.password or p.port not in (None,443): raise ValueError()
        host = (p.hostname or '').lower()
        if host == 'youtu.be': vid = p.path.strip('/')
        elif host in {'youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'}:
            if p.path == '/watch': vid = parse_qs(p.query).get('v',[''])[0]
            elif p.path.startswith(('/shorts/','/live/','/embed/')): vid = p.path.split('/')[2]
            else: raise ValueError()
        else: raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid): raise ValueError()
        return 'https://www.youtube.com/watch?'+urlencode({'v':vid})
    except (ValueError, IndexError):
        raise ValueError('กรุณาใส่ลิงก์วิดีโอ YouTube แบบ HTTPS ที่ถูกต้อง (ไม่รองรับ playlist)')

def record_stream(job, info, output):
    """Read selected media at native rate until EOF; publish only complete files."""
    duration = float(info.get('duration') or 0)
    if info.get('is_live') or not 0 < duration <= 10800:
        raise RuntimeError('โหมดบันทึกรองรับวิดีโอที่จบแล้ว ความยาวไม่เกิน 3 ชั่วโมงและมีข้อมูลระยะเวลา')
    streams = info.get('requested_formats') or [info]
    if any(s.get('has_drm') for s in streams):
        raise RuntimeError('ไม่รองรับสตรีม DRM')
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
           '-nostats', '-stats_period', '1', '-progress', 'pipe:1', '-y']
    for stream in streams:
        url = stream.get('url', '')
        if urlsplit(url).scheme not in ('https', 'http'):
            raise RuntimeError('ไม่รองรับรูปแบบสตรีมนี้')
        headers = {**info.get('http_headers', {}), **stream.get('http_headers', {})}
        header_text = ''.join(f'{k}: {v}\r\n' for k, v in headers.items()
                              if re.fullmatch(r'[A-Za-z0-9-]+', k)
                              and '\r' not in str(v) and '\n' not in str(v))
        cmd += ['-re', '-rw_timeout', '30000000']
        if header_text:
            cmd += ['-headers', header_text]
        cmd += ['-i', url]
    audio = next((i for i,s in enumerate(streams) if s.get('acodec') not in (None, 'none')), None)
    video = next((i for i,s in enumerate(streams) if s.get('vcodec') not in (None, 'none')), None)
    if job['format'] == 'mp3':
        if audio is None: raise RuntimeError('ไม่พบสตรีมเสียง')
        cmd += ['-map', f'{audio}:a:0', '-vn', '-c:a', 'libmp3lame', '-b:a', '192k']
    else:
        if video is None: raise RuntimeError('ไม่พบสตรีมวิดีโอ')
        cmd += ['-map', f'{video}:v:0']
        if audio is not None: cmd += ['-map', f'{audio}:a:0']
        cmd += ['-c', 'copy', '-movflags', '+faststart']
    partial = output.with_name(output.stem + '.recording' + output.suffix)
    cmd += [str(partial)]
    update(job['id'], status='recording', title=info.get('title', job['title']),
           duration_seconds=duration, recorded_seconds=0, progress=0)
    done = threading.Event()
    timed_out = threading.Event()
    errors = collections.deque(maxlen=12)
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8', errors='replace') as proc:
        def drain_errors():
            for line in proc.stderr: errors.append(line[:1000])
        def watchdog():
            deadline = time.monotonic() + duration + 300
            while not done.wait(0.25):
                if STOP.is_set() or time.monotonic() > deadline:
                    timed_out.set()
                    if proc.poll() is None: proc.kill()
                    return
        reader = threading.Thread(target=drain_errors, daemon=True)
        guard = threading.Thread(target=watchdog, daemon=True)
        reader.start(); guard.start()
        try:
            for line in proc.stdout:
                key, _, value = line.strip().partition('=')
                if key == 'out_time_us':
                    try: seconds = max(0, float(value) / 1_000_000)
                    except ValueError: continue
                    update(job['id'], recorded_seconds=seconds,
                           progress=min(99, round(100*seconds/duration, 1)),
                           eta=max(0, int(duration-seconds)),
                           downloaded_bytes=partial.stat().st_size if partial.exists() else 0)
                elif key == 'progress' and value == 'end':
                    update(job['id'], status='processing', eta=0)
            code = proc.wait(timeout=10)
        finally:
            done.set()
            if proc.poll() is None: proc.kill(); proc.wait()
            reader.join(timeout=2); guard.join(timeout=2)
    if timed_out.is_set():
        raise RuntimeError('การบันทึกหยุดลงหรือเกินเวลาที่กำหนด กรุณาลองใหม่')
    if code != 0:
        detail = re.sub(r'https?://\S+', '[stream URL]', ''.join(errors))[-1500:]
        raise RuntimeError('FFmpeg บันทึกไม่สำเร็จ: ' + detail)
    # A clean EOF can also mean an interrupted HTTP response; verify duration.
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'json', str(partial)], capture_output=True, text=True, timeout=30)
    try: actual = float(json.loads(probe.stdout)['format']['duration'])
    except (ValueError, KeyError, TypeError): raise RuntimeError('ตรวจสอบไฟล์ที่บันทึกไม่ได้')
    if probe.returncode or actual <= 0 or actual < duration - max(2, duration*0.01):
        raise RuntimeError('สตรีมจบก่อนครบความยาววิดีโอ ไฟล์ยังไม่ถูกระบุว่าสำเร็จ กรุณาลองใหม่')
    partial.replace(output)
    return output


def download_job(job):
    import yt_dlp
    folder = MEDIA / job['id']
    folder.mkdir(exist_ok=True)
    last = [0.0]
    def hook(d):
        if STOP.is_set(): raise RuntimeError('Server stopping; job will resume after restart')
        info = d.get('info_dict', {})
        if d['status'] == 'finished':
            update(job['id'],status='processing',title=info.get('title',job['title']),speed=0,eta=None)
        elif d['status']=='downloading' and time.monotonic()-last[0] > 0.75:
            last[0]=time.monotonic()
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            got = d.get('downloaded_bytes',0)
            update(job['id'],status='downloading',title=info.get('title',job['title']),
                   progress=min(99,round(100*got/total,1)) if total else 0,
                   downloaded_bytes=got,total_bytes=total,speed=d.get('speed') or 0,eta=d.get('eta'))
    def reject(info, *, incomplete=False):
        if info.get('is_live'): return 'ไม่รองรับ Live ที่กำลังถ่ายทอดสด'
        if (info.get('duration') or 0) > 10800: return 'รองรับวิดีโอไม่เกิน 3 ชั่วโมง'
    opts = dict(noplaylist=True,quiet=True,no_warnings=True,restrictfilenames=False,
                outtmpl=str(folder/'%(title).120B [%(id)s].%(ext)s'),
                progress_hooks=[hook],match_filter=reject, socket_timeout=25,
                retries=3,fragment_retries=3,max_filesize=2*1024**3,
                js_runtimes={'deno':{}},windowsfilenames=True)
    if job['format']=='mp3':
        opts.update(format='bestaudio/best',postprocessors=[{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'192'}])
    else:
        h=job['quality']
        opts.update(format=f'bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/best[height<={h}][ext=mp4]', merge_output_format='mp4')
    update(job['id'],status='extracting',error=None)
    with yt_dlp.YoutubeDL(opts) as ydl:
        recording = job.get('mode', 'download') == 'record'
        info=ydl.extract_info(job['url'], download=not recording)
        if recording:
            if not info: raise RuntimeError('ไม่พบข้อมูลวิดีโอ')
            output = Path(ydl.prepare_filename(info)).with_suffix('.' + job['format'])
            file = record_stream(job, info, output)
            update(job['id'], status='completed', title=info.get('title',job['title']),
                   progress=100, recorded_seconds=info.get('duration') or 0,
                   filename=file.name, storage_path=str(file), size_bytes=file.stat().st_size,
                   speed=0, eta=None)
            return
    if not info: raise RuntimeError('ไม่พบข้อมูลวิดีโอ')
    files=list(folder.glob('*.'+job['format']))
    if not files: raise RuntimeError('ไม่พบไฟล์ผลลัพธ์หลังประมวลผล')
    file=max(files,key=lambda f:f.stat().st_mtime)
    update(job['id'],status='completed',title=info.get('title',job['title']),progress=100,
           filename=file.name,storage_path=str(file),size_bytes=file.stat().st_size,speed=0,eta=None)

def worker():
    while not STOP.is_set():
        with connect() as c:
            job=c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        if not job:
            STOP.wait(0.8); continue
        try: download_job(dict(job))
        except Exception as e:
            update(job['id'],status='failed',error=re.sub(r'\x1b\[[0-9;]*m','',str(e))[:1800],speed=0,eta=None)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass # Do not log auth headers / signed URLs.
    def cors(self):
        origin=self.headers.get('Origin','')
        if origin in ORIGINS:
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
    def send_json(self, code, payload):
        b=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(code); self.cors()
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def auth(self):
        return bool(TOKEN) and hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+TOKEN)
    def do_OPTIONS(self):
        self.send_response(204); self.cors()
        self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type')
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.end_headers()
    def body(self):
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<=8192: raise ValueError('ขนาดข้อมูลไม่ถูกต้อง')
        return json.loads(self.rfile.read(size))
    def do_GET(self):
        p=urlsplit(self.path)
        if p.path.startswith('/files/'):
            return self.serve_media(p)
        if p.path.startswith('/api/'):
            if not self.auth(): return self.send_json(401,{'error':'API token ไม่ถูกต้อง'})
            if p.path=='/api/health':
                return self.send_json(200,{'ok':True,'database':str(DB),'storage':str(MEDIA),'free_bytes':shutil.disk_usage(DATA).free})
            if p.path=='/api/jobs':
                with connect() as c: rows=[dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1000')]
                return self.send_json(200,{'jobs':rows})
            m=re.fullmatch(r'/api/jobs/([a-f0-9]{32})/(events|file-link)',p.path)
            if m:
                id,kind=m.groups()
                with connect() as c:
                    job=c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
                    if not job: return self.send_json(404,{'error':'ไม่พบรายการ'})
                    if kind=='events':
                        return self.send_json(200,{'events':[dict(r) for r in c.execute('SELECT * FROM events WHERE job_id=? ORDER BY id DESC LIMIT 100',(id,))]})
                if job['status']!='completed' or not Path(job['storage_path']).is_file():
                    return self.send_json(404,{'error':'ไฟล์ยังไม่พร้อม หรือถูกย้ายออกจากเซิร์ฟเวอร์'})
                expires=str(int(time.time())+120)
                sig=hmac.new(TOKEN.encode(),(id+':'+expires).encode(),hashlib.sha256).hexdigest()
                return self.send_json(200,{'path':f'/files/{id}?expires={expires}&sig={sig}'})
            return self.send_json(404,{'error':'ไม่พบ API'})
        if p.path in ('/','/index.html'):
            b=(ROOT/'dist/index.html').read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        else: self.send_json(404,{'error':'ไม่พบหน้า'})
    def serve_media(self,p):
        id=p.path.removeprefix('/files/')
        q=parse_qs(p.query);expires=q.get('expires',[''])[0];sig=q.get('sig',[''])[0]
        expected=hmac.new(TOKEN.encode(),(id+':'+expires).encode(),hashlib.sha256).hexdigest()
        if not expires.isdigit() or int(expires)<time.time() or not hmac.compare_digest(sig,expected):
            return self.send_json(403,{'error':'ลิงก์หมดอายุ กรุณากดดาวน์โหลดอีกครั้ง'})
        with connect() as c: job=c.execute("SELECT * FROM jobs WHERE id=? AND status='completed'",(id,)).fetchone()
        if not job or not job['storage_path']: return self.send_json(404,{'error':'ไม่พบไฟล์'})
        f=Path(job['storage_path']).resolve()
        if not f.is_relative_to(MEDIA) or not f.is_file(): return self.send_json(404,{'error':'ไม่พบไฟล์'})
        from urllib.parse import quote
        self.send_response(200); self.cors()
        self.send_header('Content-Type','audio/mpeg' if job['format']=='mp3' else 'video/mp4')
        self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(f.name))
        self.send_header('Content-Length',str(f.stat().st_size));self.end_headers()
        try:
            with f.open('rb') as src: shutil.copyfileobj(src,self.wfile,1024*1024)
        except (BrokenPipeError,ConnectionResetError): pass
    def do_POST(self):
        if not self.auth(): return self.send_json(401,{'error':'API token ไม่ถูกต้อง'})
        try:
            if self.path=='/api/jobs':
                data=self.body();url=normalize_url(data.get('url',''))
                fmt=data.get('format','mp4');quality=int(data.get('quality',1080))
                mode=data.get('mode','record')
                if mode not in ('record','download'): raise ValueError('โหมดไม่ถูกต้อง')
                if fmt not in ('mp4','mp3') or quality not in (360,480,720,1080): raise ValueError('รูปแบบหรือความละเอียดไม่ถูกต้อง')
                with connect() as c:
                    if c.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','extracting','downloading','recording','processing')").fetchone()[0]>=50:
                        return self.send_json(429,{'error':'คิวเต็ม (50 รายการ)'})
                    id=secrets.token_hex(16);t=now()
                    c.execute('INSERT INTO jobs(id,url,title,format,quality,status,created_at,updated_at,mode) VALUES(?,?,?,?,?,?,?,?,?)',
                              (id,url,'กำลังรออ่านชื่อวิดีโอ',fmt,quality,'queued',t,t,mode))
                    c.execute('INSERT INTO events(job_id,status,created_at) VALUES(?,?,?)',(id,'queued',t))
                return self.send_json(201,{'id':id})
            m=re.fullmatch(r'/api/jobs/([a-f0-9]{32})/retry',self.path)
            if m:
                with connect() as c:
                    count=c.execute("UPDATE jobs SET status='queued',progress=0,recorded_seconds=0,downloaded_bytes=0,error=NULL,updated_at=? WHERE id=? AND status='failed'",(now(),m[1])).rowcount
                    if count: c.execute('INSERT INTO events(job_id,status,created_at) VALUES(?,?,?)',(m[1],'queued',now()))
                return self.send_json(200 if count else 409,{'ok':bool(count),'error':None if count else 'ลองใหม่ได้เฉพาะรายการที่ไม่สำเร็จ'})
            self.send_json(404,{'error':'ไม่พบ API'})
        except (ValueError,TypeError,AttributeError) as e: self.send_json(400,{'error':str(e)})

if __name__=='__main__':
    if len(TOKEN)<24: raise SystemExit('Set API_TOKEN to at least 24 characters before starting.')
    init_db();threading.Thread(target=worker,daemon=True).start()
    server=ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler)
    print('Video Vault ready on port '+str(server.server_port),flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: STOP.set();server.server_close()
