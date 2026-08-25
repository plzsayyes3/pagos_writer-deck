#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import curses, fcntl, mmap, os, struct, unicodedata
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
FB='/dev/fb1'; FBIOGET_VSCREENINFO=0x4600; FBIOGET_FSCREENINFO=0x4602
FONT_CANDIDATES=[os.path.expanduser('~/e-Paper/E-paper_Separate_Program/3in7_e-Paper_G/RaspberryPi_JetsonNano/python/pic/Font.ttc'),'/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
def screen_info(fd):
    var=bytearray(160); fix=bytearray(80); fcntl.ioctl(fd,FBIOGET_VSCREENINFO,var,True); fcntl.ioctl(fd,FBIOGET_FSCREENINFO,fix,True)
    x,y,xv,yv,xo,yo,bpp,_=struct.unpack_from('8I',var,0)
    ro,rl,_=struct.unpack_from('3I',var,32); go,gl,_=struct.unpack_from('3I',var,44); bo,bl,_=struct.unpack_from('3I',var,56)
    stride=struct.unpack_from('I',fix,44)[0]
    return {'w':x,'h':y,'yv':yv,'bpp':bpp,'stride':stride,'ro':ro,'rl':rl,'go':go,'gl':gl,'bo':bo,'bl':bl}
def px(r,g,b,i):
    return ((r*((1<<i['rl'])-1)//255)<<i['ro'])|((g*((1<<i['gl'])-1)//255)<<i['go'])|((b*((1<<i['bl'])-1)//255)<<i['bo'])
def main(stdscr):
    curses.raw(); curses.noecho(); stdscr.nodelay(False)
    fd=os.open(FB,os.O_RDWR); info=screen_info(fd)
    if info['bpp']!=16: raise RuntimeError(f"expected 16bpp, got {info['bpp']}bpp")
    mm=mmap.mmap(fd,info['stride']*info['yv'],mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE)
    fontp=next((p for p in FONT_CANDIDATES if os.path.exists(p)),None)
    if not fontp: raise RuntimeError('font not found')
    font=ImageFont.truetype(fontp,24); small=ImageFont.truetype(fontp,15); lines=['']
    def draw():
        img=Image.new('RGB',(info['w'],info['h']),'white'); d=ImageDraw.Draw(img)
        y=6
        for logical in '\n'.join(lines).split('\n'):
            cur=''
            for ch in logical:
                test=cur+ch
                if d.textlength(test,font=font)>info['w']-20 and cur: d.text((10,y),cur,font=font,fill='black'); y+=30; cur=ch
                else: cur=test
            d.text((10,y),cur,font=font,fill='black'); y+=30
            if y>info['h']-42: break
        sy=info['h']-31; d.line((0,sy,info['w'],sy),fill=(230,190,0),width=2); d.text((10,info['h']-24),f"{sum(map(len,lines))}字",font=small,fill='black'); d.text((info['w']//2-25,info['h']-24),'未保存',font=small,fill='black')
        clock=datetime.now().strftime('%H:%M'); bb=d.textbbox((0,0),clock,font=small); d.text((info['w']-10-(bb[2]-bb[0]),info['h']-24),clock,font=small,fill='black')
        img=img.rotate(180); out=bytearray(info['stride']*info['yv'])
        for yy in range(info['h']):
            base=yy*info['stride']
            for xx in range(info['w']): struct.pack_into('<H',out,base+xx*2,px(*img.getpixel((xx,yy)),info))
        mm.seek(0); mm.write(out); mm.flush()
    try:
        draw()
        while True:
            ch=stdscr.get_wch()
            if isinstance(ch,str):
                if ch=='\x11': break
                if ch in ('\n','\r'): lines.append('')
                elif ch in ('\x7f','\b'):
                    if lines[-1]: lines[-1]=lines[-1][:-1]
                    elif len(lines)>1: lines.pop()
                elif ch and unicodedata.category(ch[0])!='Cc': lines[-1]+=ch
                draw()
    finally:
        mm.close(); os.close(fd)
if __name__=='__main__': curses.wrapper(main)
