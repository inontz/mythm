from pathlib import Path
import os, sys, json, random
import numpy as np
import librosa

SR = 44100
HOP = 512

def smooth(x, w=9):
    if len(x) < w: return x
    k = np.ones(w)/w
    return np.convolve(x, k, mode="same")

def norm(x):
    return (x-x.min())/(x.max()+1e-9)

def build_chart(y, sr, lanes, diff):
    if diff=="easy":
        min_gap, delta, wait, density = 130, 0.24, 7, 0.35
    elif diff=="normal":
        min_gap, delta, wait, density = 95, 0.21, 6, 0.55
    else:
        min_gap, delta, wait, density = 70, 0.18, 5, 0.75

    y_h, y_p = librosa.effects.hpss(y)
    onset = librosa.onset.onset_strength(y=y_p, sr=sr)
    onset = smooth(onset, 11)

    frames = librosa.onset.onset_detect(
        onset_envelope=onset, sr=sr, hop_length=HOP,
        backtrack=True, delta=delta, wait=wait
    )

    rms = norm(smooth(librosa.feature.rms(y=y, hop_length=HOP)[0], 21))

    notes=[]
    last_t=None

    for fr in frames:
        t = int(librosa.frames_to_time(fr, sr=sr, hop_length=HOP)*1000)
        if last_t and t-last_t < min_gap: continue
        if rms[min(fr,len(rms)-1)] < density: continue

        if random.random()<0.7:
            lane=random.randint(1,lanes-2)
        else:
            lane=random.randint(0,lanes-1)

        notes.append({"tMs":t,"lane":lane,"type":"tap"})
        last_t=t

    return notes

def main(artist_dir: Path):
    for song_dir in artist_dir.iterdir():
        audio = Path(song_dir,"song.wav")
        meta = json.load(open(Path(song_dir,"meta.json"),encoding="utf-8"))
        out = os.path.join(song_dir,"charts")
        os.makedirs(out, exist_ok=True)

        y,sr = librosa.load(audio, sr=SR, mono=True)

        for lanes in (5,6):
            for diff in ("easy","normal","hard"):
                notes = build_chart(y,sr,lanes,diff)
                chart = {
                    "title": meta["title"],
                    "artist": meta["artist"],
                    "lanes": lanes,
                    "difficulty": diff,
                    "offsetMs": meta.get("offsetMs",0),
                    "notes": notes
                }
                fn=f"{lanes}_{diff}.json"
                json.dump(chart, open(os.path.join(out,fn),"w",encoding="utf-8"),
                        ensure_ascii=False, indent=2)
                print("Saved", fn, "notes:", len(notes))

if __name__=="__main__":
    main(artist_dir=Path('songs'))
