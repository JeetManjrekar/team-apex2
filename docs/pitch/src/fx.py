"""Inject Morph transitions and entrance animations into the pptxgenjs output.
usage: python3 fx.py raw.pptx anim.json out.pptx
"""
import json, re, sys, zipfile
from collections import OrderedDict

raw, animf, out = sys.argv[1:4]
anim = json.load(open(animf))

MORPH = ('<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
         '<mc:Choice xmlns:p159="http://schemas.microsoft.com/office/powerpoint/2015/09/main" Requires="p159">'
         '<p:transition xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" spd="slow" p14:dur="1200">'
         '<p159:morph option="byObject"/></p:transition></mc:Choice>'
         '<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback></mc:AlternateContent>')
FADE = '<p:transition spd="med"><p:fade/></p:transition>'


class Ids:
    def __init__(self): self.n = 2
    def next(self):
        self.n += 1
        return self.n


def tgt(spid):
    return f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'


def effect(ids, spid, fx, node, delay):
    dur = 650
    vis = (f'<p:set><p:cBhvr><p:cTn id="{ids.next()}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
           f'{tgt(spid)}<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>')

    def anim(attr, frm, to, d=dur):
        return (f'<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn id="{ids.next()}" dur="{d}" decel="100000" fill="hold"/>'
                f'{tgt(spid)}<p:attrNameLst><p:attrName>{attr}</p:attrName></p:attrNameLst></p:cBhvr>'
                f'<p:tavLst><p:tav tm="0"><p:val><p:strVal val="{frm}"/></p:val></p:tav><p:tav tm="100000"><p:val><p:strVal val="{to}"/></p:val></p:tav></p:tavLst></p:anim>')

    def filt(f, d=dur):
        return f'<p:animEffect transition="in" filter="{f}"><p:cBhvr><p:cTn id="{ids.next()}" dur="{d}"/>{tgt(spid)}</p:cBhvr></p:animEffect>'

    if fx == 'fade':
        preset, sub, body = 10, 0, vis + filt('fade')
    elif fx == 'up':
        preset, sub, body = 42, 0, vis + filt('fade') + anim('ppt_x', '#ppt_x', '#ppt_x') + anim('ppt_y', '#ppt_y+.06', '#ppt_y')
    elif fx == 'zoom':
        preset, sub, body = 53, 16, vis + filt('fade', 500) + anim('ppt_w', '#ppt_w*0.6', '#ppt_w', 700) + anim('ppt_h', '#ppt_h*0.6', '#ppt_h', 700)
    elif fx == 'wipeUp':
        preset, sub, body = 22, 4, vis + filt('wipe(up)', 900)
    elif fx == 'wipeDown':
        preset, sub, body = 22, 1, vis + filt('wipe(down)', 1400)
    else:
        raise ValueError(fx)
    cid = ids.next()
    return (f'<p:par><p:cTn id="{cid}" presetID="{preset}" presetClass="entr" presetSubtype="{sub}" fill="hold" nodeType="{node}">'
            f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>{body}</p:childTnLst></p:cTn></p:par>')


def timing(effects, name2id):
    ids = Ids()
    groups = OrderedDict()
    for e in effects:
        groups.setdefault(e['group'], []).append(e)
    # auto group first
    order = (['auto'] if 'auto' in groups else []) + [g for g in groups if g != 'auto']
    pars = []
    for g in order:
        items = [e for e in groups[g] if e['name'] in name2id]
        if not items:
            continue
        outer = ids.next(); inner = ids.next()
        cond = ('<p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond>' if g == 'auto'
                else '<p:cond delay="indefinite"/>')
        effs = []
        for i, e in enumerate(items):
            node = ('clickEffect' if g != 'auto' and i == 0 else ('afterEffect' if g == 'auto' and i == 0 else 'withEffect'))
            effs.append(effect(ids, name2id[e['name']], e['fx'], node, e['delay']))
        pars.append(f'<p:par><p:cTn id="{outer}" fill="hold"><p:stCondLst>{cond}</p:stCondLst><p:childTnLst>'
                    f'<p:par><p:cTn id="{inner}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
                    f'{"".join(effs)}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>')
    if not pars:
        return ''
    return ('<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
            '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
            + ''.join(pars) +
            '</p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
            '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>'
            '</p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>')


zin = zipfile.ZipFile(raw)
zout = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED)
for item in zin.infolist():
    data = zin.read(item.filename)
    m = re.fullmatch(r'ppt/slides/slide(\d+)\.xml', item.filename)
    if m:
        no = m.group(1)
        xml = data.decode('utf8')
        name2id = {}
        for sid, name in re.findall(r'<p:cNvPr id="(\d+)" name="([^"]*)"', xml):
            name2id.setdefault(name, sid)
        effs = anim.get(no, [])
        missing = [e['name'] for e in effs if e['name'] not in name2id]
        if missing:
            print(f'slide {no}: missing names {missing[:5]}')
        trans = FADE if no == '1' else MORPH
        tm = timing(effs, name2id)
        xml = re.sub(r'<p:transition.*?</p:transition>|<p:transition[^>]*/>', '', xml)
        xml = xml.replace('</p:clrMapOvr>', '</p:clrMapOvr>' + trans + tm, 1)
        data = xml.encode('utf8')
    zout.writestr(item, data)
zout.close()
print('fx ok ->', out)
