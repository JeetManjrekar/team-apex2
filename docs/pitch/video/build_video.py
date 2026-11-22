"""Assemble the BauBuddy demo video (<= 1:55) from:
  raw/slides_2-4.mp4   deck slides 2-4 rendered by PowerPoint (export_slides.ps1)
  raw/take_*/          a director take (frames.ffconcat + markers.json)
  raw/scene_arch.mp4, raw/scene_close.mp4   (scenes.js)
  vo/<id>.wav          voiceover per line of script.json (or --placeholder-vo: Windows TTS, for pacing only)
  dictation WAV        the German voice note used in the take (audible under the demo)

Every cut of waiting time inside the demo gets a visible "N s later" label. Output: out/BauBuddy_Demo.mp4 + out/subs.srt.
Usage: py build_video.py [--take raw/take_X] [--placeholder-vo] [--dictation raw/dictation.wav]
"""
import argparse, json, math, os, shutil, subprocess, sys, wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW, OUT, VO = HERE / "raw", HERE / "out", HERE / "vo"
FPS, W, H = 30, 1920, 1080
FONT_B = "C\\:/Windows/Fonts/segoeuib.ttf"
MAX_LEN = 115.0


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed:\n{' '.join(map(str, cmd))}\n{r.stderr[-2500:]}")
    return r.stdout


def duration(f):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]).strip())


def wav_len(f):
    with wave.open(str(f)) as w:
        return w.getnframes() / w.getframerate()


# ---------------------------------------------------------------- timeline
def timeline(take: Path):
    m = {x["beat"]: x for x in json.loads((take / "markers.json").read_text(encoding="utf-8"))["markers"]}
    t = lambda b: m[b]["t"]
    typed = json.loads((take / "markers.json").read_text(encoding="utf-8"))["typed"]
    segs = []
    # 0:00-0:25 · slides (story 0-12.3, gap, solution sped up to fit)
    segs += [dict(src="slides", a=0.0, b=12.3, vo="01_hook"),
             dict(src="slides", a=12.3, b=18.0, vo="02_solution", vo_at=0.2),
             dict(src="slides", a=18.0, b=29.2, speed=1.8)]
    # 0:25 · live demo
    dict_end = t("dictation_stop") + 1.0 if "dictation_stop" in m else t("dictation_start") + 2.0
    segs += [dict(src="take", a=max(0.0, t("assist") - 1.0), b=dict_end, vo="03_live", dictation=not typed,
                  dictation_at=t("dictation_start") - max(0.0, t("assist") - 1.0))]
    wait = t("draft_ready") - dict_end
    proof_end = t("source_second") + 3.0 if "source_second" in m else t("source_document") + 3.2
    segs += [dict(src="take", a=t("draft_ready") - 0.5, b=t("source_document") - 0.2, label=f"{wait:.0f} s later", vo="04_draft"),
             dict(src="take", a=t("source_document") - 0.2, b=proof_end, vo="05_proof",
                  zoom=dict(box=m["source_document"].get("box"), z=1.55))]
    if "question" in m:
        wait2 = t("answer_filled") - t("answer_sent") - 1.0
        segs += [dict(src="take", a=t("question") - 0.3, b=t("answer_sent") + 1.0, vo="06_gap",
                      zoom=dict(box={"x": 30, "y": 330, "width": 360, "height": 260}, z=1.6)),   # AI Manager chat column (1440 layout)
                 dict(src="take", a=t("answer_filled") - 1.2, b=t("answer_filled") + 1.6, label=f"{wait2:.0f} s later")]
    click_from = t("doc_reopen") - 0.3 if "doc_reopen" in m else t("checked") - 1.6   # completed draft reopens, then the click
    segs += [dict(src="take", a=click_from, b=t("checked") + 3.6, vo="07_click"),
             dict(src="take", a=t("agent") + 0.2, b=t("agent") + 3.7, vo="08_site")]
    # 3D twin: the best beats of the app's own tour, found by its captions (the pile-row "Structure" caption is skipped:
    # it divides metres drilled by the pile count, an app bug)
    tour = [x for x in json.loads((take / "markers.json").read_text(encoding="utf-8"))["markers"] if x["beat"] == "tour"]
    def cap(kicker, title=None):
        return next(x["t"] for x in tour if x["kicker"].startswith(kicker) and (title is None or title in x["title"]))
    ov = tour[0]["t"]                                  # the tour opens with the site overview (caption text depends on language)
    segs += [dict(src="take", a=ov + 0.4, b=ov + 2.9),
             dict(src="take", a=cap("Zone", "Bohrpfähle") + 0.2, b=cap("Zone", "Bohrpfähle") + 2.7),
             dict(src="take", a=cap("Zone", "Erdbau") + 0.2, b=cap("Zone", "Erdbau") + 2.7),
             dict(src="take", a=cap("AI detection") + 0.2, b=cap("AI detection") + 2.9)]
    # 1:20 · technical approach, 1:45 · close
    segs += [dict(src="arch", a=0.0, b=25.0, vo="09_tech", vo_at=0.4, speed=1.2),
             dict(src="close", a=0.0, b=10.0, vo="10_close", vo_at=0.2)]
    return segs


# ---------------------------------------------------------------- video
def render_segment(i, s, take, tmp):
    src = {"slides": RAW / "slides_2-4.mp4", "arch": RAW / "scene_arch.mp4", "close": RAW / "scene_close.mp4"}.get(s["src"])
    out = tmp / f"seg{i:02d}.mp4"
    speed = s.get("speed", 1.0)
    vf = [f"setpts=(PTS-STARTPTS)/{speed}", f"fps={FPS}", f"scale={W}:{H}:flags=lanczos", "setsar=1"]
    z = s.get("zoom")
    if z and z.get("box"):   # ease into the evidence quote: box is in CSS px of the 1440x810 layout -> x4/3
        bx, by = (z["box"]["x"] + z["box"]["width"] / 2) * 4 / 3, (z["box"]["y"] + z["box"]["height"] / 2) * 4 / 3
        zz = f"(1+({z['z']}-1)*(1-pow(1-min(1,t/0.8),3)))"          # eased zoom factor over 0.8 s
        # scale the frame up per frame, then cut a fixed 1920x1080 window centred on the quote (clamped to the frame)
        vf += [f"scale=w='trunc({W}*{zz}/2)*2':h='trunc({H}*{zz}/2)*2':eval=frame:flags=lanczos",
               f"crop={W}:{H}:x='min(max({bx}*iw/{W}-{W}/2,0),iw-{W})':y='min(max({by}*ih/{H}-{H}/2,0),ih-{H})'", "setsar=1"]
    if s.get("pad"):         # hold the last frame (still image) until the voice line has finished
        vf.append(f"tpad=stop_mode=clone:stop_duration={s['pad']:.3f}")
    if s.get("label"):
        vf.append(f"drawtext=fontfile='{FONT_B}':text='{s['label']}':fontsize=40:fontcolor=white:"
                  f"box=1:boxcolor=0xFF7A00@0.92:boxborderw=18:x=w-tw-70:y=70:enable='lt(t,1.6)'")
    if s["src"] == "take":
        inp = ["-f", "concat", "-safe", "0", "-ss", f"{s['a']:.3f}", "-to", f"{s['b']:.3f}", "-i", str(take / "frames.ffconcat")]
    else:
        inp = ["-ss", f"{s['a']:.3f}", "-to", f"{s['b']:.3f}", "-i", str(src)]
    run(["ffmpeg", "-v", "error", "-y", *inp, "-vf", ",".join(vf), "-an", "-c:v", "libx264", "-preset", "medium",
         "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])
    return out


# ---------------------------------------------------------------- audio + subtitles
def placeholder_vo(lines, dest):
    """Windows SAPI voice reading the script: pacing check only, never the final audio."""
    dest.mkdir(parents=True, exist_ok=True)
    for ln in lines:
        f = dest / f"{ln['id']}.wav"
        if f.exists():
            continue
        txt = ln["text"].replace("'", "''")
        ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Rate=1;"
              f"$s.SetOutputToWaveFile('{f}'); $s.Speak('{txt}'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def srt_time(x):
    h, r = divmod(x, 3600); mnt, s = divmod(r, 60)
    return f"{int(h):02d}:{int(mnt):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def chunks(text, n_words=9):
    w = text.split()
    k = max(1, math.ceil(len(w) / n_words))
    size = math.ceil(len(w) / k)
    return [" ".join(w[i:i + size]) for i in range(0, len(w), size)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--take", default=None)
    ap.add_argument("--placeholder-vo", action="store_true")
    ap.add_argument("--dictation", default=None, help="WAV of the German dictation used in the take")
    ap.add_argument("--no-subs", action="store_true", help="no burned-in subtitles (for a live pitch narrated over the muted video)")
    a = ap.parse_args()
    take = Path(a.take) if a.take else sorted(RAW.glob("take_*"))[-1]
    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    lines = {l["id"]: l for l in script["vo"]}
    vo_dir = VO
    for mp3 in sorted((VO / "src").glob("*.mp3")):   # the repo keeps the ElevenLabs MP3s; WAVs are derived
        wav = VO / f"{mp3.stem}.wav"
        if mp3.stem != "dictation_de" and not wav.exists():
            run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(wav)])
    if a.placeholder_vo:
        vo_dir = RAW / "vo_placeholder"
        placeholder_vo(script["vo"], vo_dir)

    OUT.mkdir(exist_ok=True)
    tmp = RAW / "build"; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
    segs = timeline(take)
    # a voice line spans its segment and the following ones without a line; if it is longer, pad the group's last segment
    vi = [i for i, s in enumerate(segs) if "vo" in s] + [len(segs)]
    for g0, g1 in zip(vi, vi[1:]):
        f = vo_dir / f"{segs[g0]['vo']}.wav"
        if not f.exists():
            continue
        need = segs[g0].get("vo_at", 0.3) + wav_len(f) + 0.45
        have = sum((segs[j]["b"] - segs[j]["a"]) / segs[j].get("speed", 1.0) for j in range(g0, g1))
        if need > have and segs[g1 - 1]["src"] in ("take", "close"):
            segs[g1 - 1]["pad"] = need - have
    files, starts, t = [], [], 0.0
    for i, s in enumerate(segs):
        f = render_segment(i, s, take, tmp)
        d = duration(f)
        files.append(f); starts.append(t); s["dur"] = d; t += d
    total = t
    (tmp / "list.txt").write_text("".join(f"file '{f.name}'\n" for f in files))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "video.mp4"], cwd=tmp)

    # voice: each line starts at its segment (+vo_at); warn if it runs into the next line
    audio_in, filt, subs, prev_end = [], [], [], 0.0
    for i, s in enumerate(segs):
        if "vo" not in s:
            continue
        f = vo_dir / f"{s['vo']}.wav"
        if not f.exists():
            print(f"  ! missing {f.name} (silent)")
            continue
        at = max(starts[i] + s.get("vo_at", 0.3), prev_end + 0.15)
        L = wav_len(f); prev_end = at + L
        nxt = next((starts[j] for j in range(i + 1, len(segs)) if "vo" in segs[j]), total)
        flag = "  <-- runs into the next line, shorten it" if prev_end > nxt + 0.05 else ""
        print(f"  {s['vo']:<12} {at:6.1f}–{prev_end:6.1f} s  ({L:4.1f} s){flag}")
        audio_in += ["-i", str(f)]
        k = len(audio_in) // 2
        filt.append(f"[{k}:a]aresample=48000,pan=stereo|c0=c0|c1=c0,adelay={int(at * 1000)}|{int(at * 1000)}[v{k}]")
        parts = chunks(lines[s["vo"]]["text"]); per = L / len(parts)
        subs += [(at + j * per, at + (j + 1) * per - 0.05, p) for j, p in enumerate(parts)]
    dic = next((i for i, s in enumerate(segs) if s.get("dictation")), None)
    if dic is not None and a.dictation:
        at = starts[dic] + segs[dic]["dictation_at"]
        audio_in += ["-i", str(Path(a.dictation).resolve())]
        k = len(audio_in) // 2
        filt.append(f"[{k}:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume=0.8,adelay={int(at * 1000)}|{int(at * 1000)}[v{k}]")
        subs.append((at, at + wav_len(a.dictation), script["dictation"]["sub"]))
    subs.sort()
    (tmp / "subs.srt").write_text("\n".join(f"{n + 1}\n{srt_time(s)} --> {srt_time(e)}\n{txt}\n" for n, (s, e, txt) in enumerate(subs)), encoding="utf-8")

    n = len(audio_in) // 2
    mix = (";".join(filt) + ";" + "".join(f"[v{k}]" for k in range(1, n + 1)) +
           f"amix=inputs={n}:normalize=0,apad,atrim=0:{total:.3f},loudnorm=I=-14:TP=-1.5:LRA=11[a]") if n else None
    style = "FontName=Segoe UI,FontSize=17,PrimaryColour=&H00F8F4F2,BackColour=&H99000000,BorderStyle=4,Outline=0,Shadow=0,MarginV=18"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", "video.mp4", *audio_in,
           *([] if a.no_subs else ["-vf", f"subtitles=subs.srt:force_style='{style}'"])]
    cmd += (["-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"] if mix else ["-an"])
    final = OUT / ("BauBuddy_Demo_nosubs.mp4" if a.no_subs else "BauBuddy_Demo.mp4")
    part = tmp / "final.mp4"            # encode next to the parts, swap in only when complete (a player may hold the old file)
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "final.mp4"]
    run(cmd, cwd=tmp)
    duration(part)                      # fails loudly if the file is incomplete
    try:
        os.replace(part, final)
    except PermissionError:
        final = OUT / "BauBuddy_Demo_new.mp4"
        os.replace(part, final)
        print("  ! BauBuddy_Demo.mp4 is open in another program; wrote", final.name)
    shutil.copy(tmp / "subs.srt", OUT / "subs.srt")
    d = duration(final)
    print(f"\n{final}  {d:.1f} s  {'OK' if d <= MAX_LEN else 'TOO LONG (cap 115 s)'}  · take {take.name} · vo {'PLACEHOLDER' if a.placeholder_vo else vo_dir}")
    for i, s in enumerate(segs):
        print(f"  {starts[i]:6.1f} s  {s['src']:<6} {s.get('vo', ''):<12} {s.get('label', '')}")


if __name__ == "__main__":
    main()
