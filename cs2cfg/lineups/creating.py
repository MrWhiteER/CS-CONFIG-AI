"""Two player-triggered pictures. No game configuration or game input."""
import base64
import math
import threading
import uuid
from pathlib import Path
from .radar import png


class PictureHotkey:
    """RegisterHotKey on an app-owned message thread, only during a wait."""
    def __init__(self, key, callback):
        self.key, self.callback = key, callback
        self.ready = threading.Event()
        self.error = None
        self.thread_id = None
        self.thread = threading.Thread(target=self.run, daemon=True, name='lineup-picture-key')

    def start(self):
        self.thread.start()
        self.ready.wait()
        if self.error:
            raise OSError(self.error)

    def run(self):
        try:
            self.message_loop()
        except (OSError, AttributeError, ValueError):
            self.error = 'The picture key is unavailable. Choose another key in Settings.'
        finally:
            self.ready.set()

    def message_loop(self):
        import ctypes
        from ctypes import wintypes as w
        user, kernel = ctypes.WinDLL('user32'), ctypes.WinDLL('kernel32')
        user.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
        user.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
        user.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
        user.PostThreadMessageW.argtypes = [w.DWORD, w.UINT, w.WPARAM, w.LPARAM]
        self.user = user
        self.thread_id = kernel.GetCurrentThreadId()
        message = w.MSG()
        user.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        registered = user.RegisterHotKey(None, 73, 0x4000, 0x70 + int(self.key[1:]) - 1)
        if not registered:
            self.error = 'The picture key is in use. Choose another Lineup picture key in Settings.'
        self.ready.set()
        if not registered:
            return
        try:
            while user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312 and message.wParam == 73:
                    self.callback()
        finally:
            user.UnregisterHotKey(None, 73)

    def close(self):
        if self.thread_id and self.thread.is_alive():
            self.user.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
            if threading.current_thread() is not self.thread:
                self.thread.join()


def crop_frame(frame, crop):
    width, height, rgba = frame
    if not (1 <= width <= 4096 and 1 <= height <= 4096 and len(rgba) == width*height*4):
        raise ValueError('Picture unavailable')
    x,y,w,h = crop
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in crop):
        raise ValueError('Choose a crop inside the picture.')
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > 1.000001 or y+h > 1.000001:
        raise ValueError('Choose a crop inside the picture.')
    left,top = int(x*width),int(y*height)
    right,bottom = min(width,round((x+w)*width)),min(height,round((y+h)*height))
    if right <= left or bottom <= top:
        raise ValueError('Choose a larger crop.')
    return right-left,bottom-top,b''.join(rgba[(row*width+left)*4:(row*width+right)*4] for row in range(top,bottom))


class CreatingSession:
    def __init__(self, capture, key='F9', hotkey=PictureHotkey, changed=lambda:None):
        self.capture, self.key, self.hotkey_factory, self.changed = capture,key,hotkey,changed
        self.frames = {}
        self.previews = {}
        self.waiting = None
        self.hotkey = None
        self.text = ''
        self.shot = 0
        self.lock = threading.RLock()

    @property
    def active(self):
        return self.waiting is not None

    def wait(self, kind='stand'):
        if kind not in ('stand','aim'):
            raise ValueError('Choose a picture.')
        self.waiting = None
        self.release()
        with self.lock:
            self.waiting = kind
            self.text = ('Go to where you stand and press ' if kind == 'stand' else 'Now aim where you throw and press ') + self.key
            self.hotkey = self.hotkey_factory(self.key, self.press)
            try:
                self.hotkey.start()
            except Exception:
                self.waiting = None
                self.release()
                raise
        self.changed()

    def release(self):
        # Message callbacks run on the hotkey thread; never join that thread here.
        if self.hotkey:
            self.hotkey.close()
            self.hotkey = None

    def press(self):
        with self.lock:
            if not self.waiting:
                return
            kind = self.waiting
            try:
                frame = self.capture()
                crop_frame(frame, [0,0,1,1])
            except (OSError, ValueError) as exc:
                self.text = (str(exc) if isinstance(exc, ValueError) else 'Picture unavailable.') + ' Keep CS2 visible and press ' + self.key + ' again.'
                self.changed()
                return
            if self.waiting != kind:
                return
            self.frames[kind] = frame
            self.previews.pop(kind, None)
            self.shot += 1
            if kind == 'stand' and 'aim' not in self.frames:
                self.waiting = 'aim'
                self.text = 'Now aim where you throw and press ' + self.key
            else:
                self.waiting = None
                self.release()
                self.text = 'Review both pictures. Crop removes the game HUD.'
        self.changed()

    def snapshot(self):
        with self.lock:
            if not self.active:
                for kind,frame in self.frames.items():
                    if kind not in self.previews:
                        self.previews[kind] = 'data:image/png;base64,'+base64.b64encode(png(*frame)).decode('ascii')
            return {'active':self.active, 'text':self.text,
                    'review':bool(not self.active and len(self.frames)==2), 'shot':self.shot,
                    'frames':dict(self.previews) if not self.active else {}}

    def cancel(self):
        # Release outside the lock so an in-flight key callback can finish.
        self.waiting = None
        self.release()
        with self.lock:
            self.frames.clear()
            self.previews.clear()
            self.text = ''
        self.changed()

    def save(self, edits, root):
        if self.active or len(self.frames) != 2:
            raise ValueError('Take both pictures first.')
        folder = Path(root)/'lineups'/'pictures'/uuid.uuid4().hex
        prepared = {}
        for kind in ('stand','aim'):
            edit = edits.get(kind,{})
            frame = crop_frame(self.frames[kind], edit.get('crop',[0,0,1,1]))
            marker = edit.get('marker',[.5,.5])
            if len(marker)!=2 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=1 for v in marker):
                raise ValueError('Place the picture marker.')
            prepared[kind] = (png(*frame), marker)
        folder.mkdir(parents=True)
        result = {}
        for kind,(raw,marker) in prepared.items():
            path = folder/(kind+'.png')
            path.write_bytes(raw)
            result[kind] = {'file':str(path.relative_to(Path(root)/'lineups')), 'marker':marker}
        return result


def pictures(row, root):
    """Only trusted, bounded app picture paths become data URLs."""
    result = {}
    folder = (Path(root)/'lineups'/'pictures').resolve()
    for kind, item in row.get('pictures',{}).items():
        if kind not in ('stand','aim') or not isinstance(item,dict):
            continue
        path = (Path(root)/'lineups'/item.get('file','')).resolve()
        if folder not in path.parents or not path.is_file():
            continue
        result[kind] = 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode('ascii')
    return result


def builtin_metadata(key, root):
    import json
    from . import MAPS
    if key not in MAPS:
        return {}
    path = Path(root)/'lineups'/('builtin-'+key+'.json')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_builtin(key, identity, metadata, root):
    import json
    from . import load
    if not any(r['id'] == identity for r in (load(key) or {}).get('lineups', [])):
        raise ValueError('Choose a lineup.')
    records = builtin_metadata(key, root)
    records[identity] = metadata
    path = Path(root)/'lineups'/('builtin-'+key+'.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(records), encoding='utf-8')
    temporary.replace(path)
