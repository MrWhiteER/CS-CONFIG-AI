"""Runtime radar extraction and SVG annotations; never ships Valve art."""
import base64
import html
import json
import struct
import threading
import zlib
from pathlib import Path
from .. import mapart, vpk, vdf
from . import MAPS, canonical, pixel

_lock = threading.Lock()
_memory = {}


def lz4(raw, expected):
    """Decode a bounded raw LZ4 block (Source 2 compressed mip data)."""
    at, out = 0, bytearray()
    def size(n):
        nonlocal at
        if n == 15:
            while True:
                if at >= len(raw): raise ValueError('Truncated texture')
                extra=raw[at]; at+=1; n+=extra
                if extra != 255: break
        return n
    while at < len(raw):
        token=raw[at]; at+=1
        length=size(token>>4)
        if at+length > len(raw) or len(out)+length > expected: raise ValueError('Invalid texture size')
        out.extend(raw[at:at+length]); at+=length
        if at == len(raw): break
        if at+2 > len(raw): raise ValueError('Truncated texture')
        offset=int.from_bytes(raw[at:at+2],'little'); at+=2
        count=size(token&15)+4
        if not offset or offset>len(out) or len(out)+count>expected: raise ValueError('Invalid texture match')
        for _ in range(count): out.append(out[-offset])
    if len(out)!=expected: raise ValueError('Invalid texture size')
    return bytes(out)


def png(width, height, rgba):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    scan = b''.join(b'\0' + rgba[y*width*4:(y+1)*width*4] for y in range(height))
    return (mapart.PNG_START + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(scan)) + chunk(b'IEND', b''))


def decode_blocks(data, width, height, alpha=False):
    """Bounded BC1 / BC3 decoder, including BC1 transparency and BC3 alpha."""
    if not 1 <= width <= 2048 or not 1 <= height <= 2048:
        raise ValueError('Texture too large')
    stride = 16 if alpha else 8
    if len(data) != ((width+3)//4)*((height+3)//4)*stride:
        raise ValueError('Truncated texture')
    out = bytearray(width*height*4)
    offset = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            block = data[offset:offset+stride]
            offset += stride
            alphas, bits = [255]*8, 0
            if alpha:
                a, b = block[:2]
                alphas = [a, b] + ([( (7-i)*a+i*b)//7 for i in range(1,7)] if a > b
                                  else [((5-i)*a+i*b)//5 for i in range(1,5)] + [0,255])
                bits = int.from_bytes(block[2:8], 'little')
                block = block[8:]
            a, b, indices = struct.unpack('<HHI', block)
            def rgb(n):
                return ((n >> 11)*255//31, ((n >> 5)&63)*255//63, (n&31)*255//31, 255)
            colors = [rgb(a), rgb(b)]
            if a > b or alpha:
                colors += [tuple((2*colors[0][k]+colors[1][k])//3 for k in range(4)),
                           tuple((colors[0][k]+2*colors[1][k])//3 for k in range(4))]
            else:
                colors += [tuple((colors[0][k]+colors[1][k])//2 for k in range(4)), (0,0,0,0)]
            for i in range(16):
                x, y = bx+i%4, by+i//4
                if x < width and y < height:
                    color = colors[(indices >> (i*2))&3]
                    out[(y*width+x)*4:(y*width+x+1)*4] = bytes((*color[:3], alphas[(bits>>(i*3))&7] if alpha else color[3]))
    return bytes(out)


def cut_texture(raw):
    embedded = mapart.cut_png(raw)
    if embedded:
        return embedded
    # Source 2 resource directory: offsets are relative to their own field.
    if len(raw) < 16:
        return None
    try:
        start, count = struct.unpack_from('<II', raw, 8)
        if count > 64:
            return None
        for i in range(count):
            at = 8 + start + i*12
            tag, off, size = struct.unpack_from('<4sII', raw, at)
            if tag != b'DATA':
                continue
            pos = at+4+off
            version = struct.unpack_from('<H', raw, pos)[0]
            width, height, depth, fmt, mips = struct.unpack_from('<HHHBB', raw, pos+20)
            extras = struct.unpack_from('<I', raw, pos+36)[0]
            if version != 1 or depth != 1 or extras>32 or fmt not in (1,2,4,28) or not 1 <= mips <= 12:
                return None
            if not 1 <= width <= 2048 or not 1 <= height <= 2048:
                return None
            def length(w,h):
                return w*h*4 if fmt in (4,28) else ((w+3)//4)*((h+3)//4)*(8 if fmt == 1 else 16)
            mip_sizes = [length(max(1,width>>m),max(1,height>>m)) for m in range(mips)]
            compression = 0
            extra_offset = struct.unpack_from('<I',raw,pos+32)[0]
            for n in range(extras):
                at = pos+32+extra_offset+n*12
                kind,offset,extra_size = struct.unpack_from('<III',raw,at)
                if kind == 4:
                    extra = at+4+offset
                    compression,mip_offset,mip_count=struct.unpack_from('<III',raw,extra)
                    if compression not in (0,1,2) or mip_count != mips: return None
                    mip_sizes=list(struct.unpack_from('<'+'I'*mips,raw,extra+4+mip_offset))
                    if any(s>32*1024*1024 for s in mip_sizes): return None
            offset = pos+size + sum(mip_sizes[1:])
            data = raw[offset:offset+mip_sizes[0]]
            if len(data)!=mip_sizes[0]: return None
            if len(data)!=length(width,height):
                if compression == 1: data=lz4(data,length(width,height))
                elif compression == 2:
                    import zstandard
                    try:
                        data=zstandard.ZstdDecompressor().decompress(data,max_output_size=length(width,height))
                    except zstandard.ZstdError:
                        return None
                else: return None
            rgba = data if fmt in (4,28) else decode_blocks(data,width,height,fmt==2)
            if fmt == 28:
                rgba = bytes(channel for i in range(0,len(data),4) for channel in (data[i+2],data[i+1],data[i],data[i+3]))
            return png(width,height,rgba) if len(rgba)==width*height*4 else None
    except (ValueError, struct.error, IndexError, ImportError):
        pass
    return None


def read_overview(text):
    root = next(iter(vdf.parse(text).values()))
    out = {k: float(root[k]) for k in ('pos_x','pos_y','scale')}
    import math
    if not all(math.isfinite(n) for n in out.values()) or out['scale'] <= 0:
        raise ValueError('Invalid overview')
    return {**out, 'width':1024, 'height':1024}


def picture(dir_vpk, cache_dir, key):
    key = canonical(key)
    if key not in MAPS or dir_vpk is None:
        return None
    try:
        stamp = Path(dir_vpk).stat().st_mtime_ns
        cache = Path(cache_dir)/'lineup-radar'
        target = cache/f'{key}-{stamp}.json'
        with _lock:
            identity = (str(dir_vpk), str(cache_dir), key, stamp)
            if identity in _memory:
                return _memory[identity]
            if len(_memory)>8:
                _memory.clear()
            if target.is_file():
                result = json.loads(target.read_text(encoding='utf-8'))
                _memory[identity] = result
                return result
            index = vpk.read_index(dir_vpk)
            overview_entry = index.get(f'resource/overviews/de_{key}.txt')
            entry = next((index[p] for p in (
                f'panorama/images/overheadmaps/de_{key}_radar_psd.vtex_c',
                f'panorama/images/overheadmaps/de_{key}_radar_tga.vtex_c',
                f'panorama/images/overheadmaps/de_{key}_radar.vtex_c',
                f'materials/overviews/de_{key}_radar.vtex_c') if p in index), None)
            if entry is None:
                _memory[identity] = None
                return None
            image = cut_texture(vpk.read_file(dir_vpk, entry))
            if image is None:
                _memory[identity] = None
                return None
            overview_text = (vpk.read_file(dir_vpk,overview_entry).decode('utf-8-sig') if overview_entry is not None
                             else (Path(dir_vpk).parent/'resource/overviews'/f'de_{key}.txt').read_text(encoding='utf-8-sig'))
            overview = read_overview(overview_text)
            result = {'overview':overview,'image':'data:image/png;base64,'+base64.b64encode(image).decode('ascii')}
            cache.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix('.tmp')
            temp.write_text(json.dumps(result),encoding='utf-8')
            temp.replace(target)
            _memory[identity] = result
            return result
    except (OSError, ValueError, KeyError, StopIteration, TypeError, vpk.VpkError):
        return None


def draw(art, rows):
    if not art:
        return ''
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="Stand points and landing areas">',
             '<image width="1024" height="1024" href="'+html.escape(art['image'],quote=True)+'"/>']
    for i,row in enumerate(rows,1):
        x,y = pixel(row['stand'],art['overview'])
        if row['land'] is None:
            parts.append(f'<g><title>{html.escape(row["name"])}</title><circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="white" stroke="#14101c" stroke-width="4"/></g>')
            continue
        u,v = pixel(row['land'] or row['stand'],art['overview'])
        color = {'smoke':'#dce1eb','fire':'#ff873e','flash':'#ffffff','grenade':'#ff5252'}[row['type']]
        parts.append(f'<g><title>{html.escape(row["name"])}</title><path d="M{x:.1f} {y:.1f} Q{(x+u)/2:.1f} {min(y,v)-90:.1f} {u:.1f} {v:.1f}" fill="none" stroke="{color}" stroke-width="5" stroke-dasharray="12 10"/><circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="white" stroke="#14101c" stroke-width="4"/><circle cx="{u:.1f}" cy="{v:.1f}" r="30" fill="{color}" fill-opacity=".35" stroke="{color}" stroke-width="5"/><text x="{u:.1f}" y="{v+9:.1f}" text-anchor="middle" font-family="Segoe UI" font-size="28" fill="white" stroke="#111" paint-order="stroke" stroke-width="3">{i}</text></g>')
    return ''.join(parts)+'</svg>'
