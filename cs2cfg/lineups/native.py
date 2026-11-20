"""Small runtime radar bitmap for the existing native click-through HUD."""
import base64
import json
import struct
import zlib
from functools import lru_cache
from . import pixel


def decode_png(raw):
    """8-bit RGB/RGBA PNG filters, with bounded output and no image dependency."""
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid image')
    at, compressed, width, height, channels = 8, bytearray(), 0, 0, 0
    while at+12 <= len(raw):
        size = struct.unpack_from('>I',raw,at)[0]
        tag, data = raw[at+4:at+8],raw[at+8:at+8+size]
        if len(data) != size:
            raise ValueError('Truncated image')
        if tag == b'IHDR':
            if len(data) != 13:
                raise ValueError('Invalid image header')
            width,height,bits,kind,compression,filtering,interlace=struct.unpack('>IIBBBBB',data)
            if (not 1 <= width <= 2048 or not 1 <= height <= 2048 or bits != 8
                    or kind not in (2,6) or compression or filtering or interlace):
                raise ValueError('Unsupported image')
            channels=3 if kind==2 else 4
        elif tag == b'IDAT': compressed.extend(data)
        elif tag == b'IEND': break
        at+=size+12
    if not channels:
        raise ValueError('Missing image size')
    stride=width*channels
    limit=(stride+1)*height
    decoder=zlib.decompressobj()
    scan=decoder.decompress(compressed,limit+1)
    if len(scan)!=limit or not decoder.eof:
        raise ValueError('Invalid image pixels')
    out,previous=bytearray(),bytes(stride)
    for y in range(height):
        kind=scan[y*(stride+1)]; row=bytearray(scan[y*(stride+1)+1:(y+1)*(stride+1)])
        if kind>4: raise ValueError('Invalid filter')
        for x in range(stride):
            a=row[x-channels] if x>=channels else 0
            b=previous[x]; c=previous[x-channels] if x>=channels else 0
            value=0
            if kind==1: value=a
            elif kind==2: value=b
            elif kind==3: value=(a+b)//2
            elif kind==4:
                p=a+b-c; distances=(abs(p-a),abs(p-b),abs(p-c))
                value=(a,b,c)[distances.index(min(distances))]
            row[x]=(row[x]+value)&255
        if channels==4: out.extend(row)
        else:
            for x in range(0,stride,3): out.extend((*row[x:x+3],255))
        previous=row
    return width,height,bytes(out)


@lru_cache(maxsize=4)
def bitmap(art_json, rows_json):
    art, rows=json.loads(art_json),json.loads(rows_json)
    width,height,rgba=decode_png(base64.b64decode(art['image'].split(',',1)[1]))
    side=336; out=bytearray(side*side*4)
    for y in range(side):
        for x in range(side):
            at=((y*height//side)*width+x*width//side)*4
            r,g,b,a=rgba[at:at+4]
            out[(y*side+x)*4:(y*side+x+1)*4]=bytes((b*a//255,g*a//255,r*a//255,a))
    def dot(x,y,r,color,ring=False):
        for yy in range(max(0,int(y-r)),min(side,int(y+r)+1)):
            for xx in range(max(0,int(x-r)),min(side,int(x+r)+1)):
                distance=(xx-x)**2+(yy-y)**2
                if distance<=r*r and (not ring or distance>=(r-2)**2):
                    out[(yy*side+xx)*4:(yy*side+xx+1)*4]=bytes((*reversed(color),255))
    digits = {'0':['111','101','101','101','111'],'1':['010','110','010','010','111'],
              '2':['111','001','111','100','111'],'3':['111','001','111','001','111'],
              '4':['101','101','111','001','001'],'5':['111','100','111','001','111'],
              '6':['111','100','111','101','111'],'7':['111','001','010','010','010'],
              '8':['111','101','111','101','111'],'9':['111','101','111','001','111']}
    for number,row in enumerate(rows,1):
        x,y=pixel(row['stand'],art['overview']); u,v=pixel(row['land'],art['overview'])
        x,y,u,v=[n*side/1024 for n in (x,y,u,v)]
        for i in range(81):
            if i%6>=3: continue
            t=i/80; s=1-t
            dot(s*s*x+2*s*t*(x+u)/2+t*t*u,s*s*y+2*s*t*(min(y,v)-30)+t*t*v,1,(220,225,235))
        dot(x,y,4,(255,255,255));dot(u,v,10,(220,225,235),True)
        for j,char in enumerate(str(number)):
            for yy,line in enumerate(digits[char]):
                for xx,value in enumerate(line):
                    if value=='1': dot(u-3+j*7+xx*2,v-4+yy*2,1,(255,255,255))
    return bytes(out)
