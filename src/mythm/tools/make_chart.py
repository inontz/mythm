import os, sys, json, random
import numpy as np
import librosa

SR = 44100
HOP = 512

def smooth(x, w=7):
    if len(x) < w: return x
    return np.convolve(x, np.ones(w)/w, mode="same")

def norm01(x):
    x = np.asarray(x)
    return (x - x.min()) / (x.max() + 1e-9)

def clamp_density(notes, duration_s, target_npm):
    max_notes = int(target_npm * (duration_s/60.0))
    max_notes = max(90, max_notes)
    if len(notes) <= max_notes:
        return notes
    step = int(np.ceil(len(notes) / max_notes))
    return notes[::step]

def pick_lane(prev, lanes):
    if lanes >= 4 and random.random() < 0.75:
        lane = random.randint(1, lanes-2)
    else:
        lane = random.randint(0, lanes-1)
    if prev is not None and lane == prev and random.random() < 0.7:
        lane = max(0, min(lanes-1, lane + random.choice([-1, 1])))
    return lane

def build_vocal_first(y, sr, lanes, diff):
    # balanced density (แก้แน่นไป)
    if diff == "easy":
        min_gap_ms = 165; wait = 6; target_npm = 150; thr = 0.16; delta = 0.12; chorus_p = 0.12
    elif diff == "normal":
        min_gap_ms = 130; wait = 6; target_npm = 210; thr = 0.15; delta = 0.12; chorus_p = 0.16
    else:
        min_gap_ms = 105; wait = 5; target_npm = 280; thr = 0.14; delta = 0.11; chorus_p = 0.20

    duration_s = len(y)/sr

    y_h, _ = librosa.effects.hpss(y)
    onset = librosa.onset.onset_strength(y=y_h, sr=sr, aggregate=np.median)
    onset = norm01(smooth(onset, 7))

    rms = norm01(smooth(librosa.feature.rms(y=y, hop_length=HOP)[0], 21))
    chorus_thr = float(np.percentile(rms, 65))

    min_gap_frames = int((min_gap_ms/1000) * sr / HOP)

    def detect(delta_use, thr_use):
        frames = librosa.onset.onset_detect(
            onset_envelope=onset, sr=sr, hop_length=HOP,
            backtrack=True, delta=delta_use, wait=wait, units="frames"
        )
        notes = []
        last_fr = None
        prev_lane = None

        for fr in frames:
            if last_fr is not None and (fr - last_fr) < min_gap_frames:
                continue
            s = float(onset[min(fr, len(onset)-1)])
            is_chorus = rms[min(fr, len(rms)-1)] >= chorus_thr
            if (not is_chorus) and (s < thr_use):
                continue

            t_ms = int(round(librosa.frames_to_time(fr, sr=sr, hop_length=HOP) * 1000))
            lane = pick_lane(prev_lane, lanes)
            prev_lane = lane
            notes.append({"tMs": t_ms, "lane": lane, "type": "tap"})
            last_fr = fr

            if is_chorus and random.random() < chorus_p:
                fr2 = fr + int(0.12 * sr / HOP)
                t2 = int(round(librosa.frames_to_time(fr2, sr=sr, hop_length=HOP) * 1000))
                lane2 = pick_lane(prev_lane, lanes)
                prev_lane = lane2
                notes.append({"tMs": t2, "lane": lane2, "type": "tap"})

        notes.sort(key=lambda n: n["tMs"])
        notes = clamp_density(notes, duration_s, target_npm)
        return notes

    trials = [
        (delta, thr),
        (max(0.10, delta*0.90), max(0.12, thr*0.90)),
        (max(0.09, delta*0.80), max(0.11, thr*0.80)),
        (max(0.08, delta*0.70), max(0.10, thr*0.70)),
    ]
    best = []
    for dlt, th in trials:
        cand = detect(dlt, th)
        if len(cand) > len(best):
            best = cand
    return best

def main(song_dir: str | os.PathLike):
    meta_path = os.path.join(song_dir, "meta.json")
    wav_path = os.path.join(song_dir, "song.wav")
    out_dir = os.path.join(song_dir, "charts")
    os.makedirs(out_dir, exist_ok=True)

    meta = json.load(open(meta_path, encoding="utf-8"))
    y, sr = librosa.load(wav_path, sr=SR, mono=True)

    random.seed(7)
    for lanes in (5, 6):
        for diff in ("easy", "normal", "hard"):
            notes = build_vocal_first(y, sr, lanes, diff)
            chart = {
                "title": meta.get("title", os.path.basename(song_dir)),
                "artist": meta.get("artist", os.path.basename(os.path.dirname(song_dir))),
                "lanes": lanes,
                "difficulty": diff,
                "offsetMs": int(meta.get("offsetMs", 0)),
                "bpm": int(meta.get("bpm", 0)),
                "style": "vocal_first_balanced",
                "notes": notes
            }
            fn = f"{lanes}_{diff}.json"
            with open(os.path.join(out_dir, fn), "w", encoding="utf-8") as f:
                json.dump(chart, f, ensure_ascii=False, indent=2)
            print("Saved", os.path.join(out_dir, fn), "notes:", len(notes))

if __name__ == "__main__":
    main(sys.argv[1])
