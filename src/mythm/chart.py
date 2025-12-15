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

def build_vocal_first(y, sr, lanes, diff):
    # ✅ เพิ่มความหนาแน่น (สำคัญ)
    if diff == "easy":
        min_gap_ms = 120
        wait = 5
        target_npm = 260
        strength_thr = 0.14
        base_delta = 0.10
        chorus_extra_prob = 0.25
    elif diff == "normal":
        min_gap_ms = 95
        wait = 4
        target_npm = 360
        strength_thr = 0.12
        base_delta = 0.09
        chorus_extra_prob = 0.33
    else:  # hard
        min_gap_ms = 75
        wait = 3
        target_npm = 480
        strength_thr = 0.10
        base_delta = 0.08
        chorus_extra_prob = 0.40

    y_h, y_p = librosa.effects.hpss(y)

    # vocal-ish onset envelope (median aggregate helps syllables)
    onset_v = librosa.onset.onset_strength(y=y_h, sr=sr, aggregate=np.median)
    onset_v = norm01(smooth(onset_v, 7))

    # energy for chorus detection
    rms = norm01(smooth(librosa.feature.rms(y=y, hop_length=HOP)[0], 21))
    chorus_thr = float(np.percentile(rms, 60))  # top ~40% energy = chorus-ish

    duration_s = len(y) / sr
    target = max(160, int(target_npm * (duration_s / 60.0)))  # ✅ เป้าขั้นต่ำต่อเพลง

    min_gap_frames = int((min_gap_ms/1000) * sr / HOP)

    def pick_lane(prev):
        # center bias
        if random.random() < 0.75 and lanes >= 4:
            lane = random.randint(1, lanes-2)
        else:
            lane = random.randint(0, lanes-1)
        if prev is not None and lane == prev and random.random() < 0.7:
            lane = max(0, min(lanes-1, lane + random.choice([-1, 1])))
        return lane

    def detect(delta, thr):
        frames = librosa.onset.onset_detect(
            onset_envelope=onset_v, sr=sr, hop_length=HOP,
            backtrack=True, delta=delta, wait=wait, units="frames"
        )

        notes = []
        last_fr = None
        prev_lane = None

        for fr in frames:
            if last_fr is not None and (fr - last_fr) < min_gap_frames:
                continue

            s = float(onset_v[min(fr, len(onset_v)-1)])
            is_chorus = rms[min(fr, len(rms)-1)] >= chorus_thr

            # ✅ verse ก็ต้องเก็บ syllable มากขึ้น (แก้น้อย)
            if (not is_chorus) and (s < thr):
                continue

            t_ms = int(round(librosa.frames_to_time(fr, sr=sr, hop_length=HOP) * 1000))
            lane = pick_lane(prev_lane)
            prev_lane = lane
            notes.append({"tMs": t_ms, "lane": lane, "type": "tap"})
            last_fr = fr

            # ✅ chorus เพิ่มโน้ตแทรก (เหมือนตามคำร้องถี่ขึ้น)
            if is_chorus and random.random() < chorus_extra_prob:
                fr2 = fr + int(0.12 * sr / HOP)  # ~120ms
                t2 = int(round(librosa.frames_to_time(fr2, sr=sr, hop_length=HOP) * 1000))
                lane2 = pick_lane(prev_lane)
                notes.append({"tMs": t2, "lane": lane2, "type": "tap"})
                prev_lane = lane2

        notes.sort(key=lambda n: n["tMs"])
        return notes

    # ✅ “ไล่ลด” delta + thr จนกว่าจะถึง target
    trials = [
        (base_delta, strength_thr),
        (max(0.06, base_delta*0.85), max(0.07, strength_thr*0.85)),
        (max(0.05, base_delta*0.75), max(0.06, strength_thr*0.75)),
        (max(0.04, base_delta*0.65), max(0.05, strength_thr*0.65)),
        (0.035, 0.045),
        (0.030, 0.040),
    ]

    best = []
    for dlt, thr in trials:
        cand = detect(dlt, thr)
        if len(cand) > len(best):
            best = cand
        if len(cand) >= target:
            return cand

    # ถ้ายังไม่ถึง target: densify pass (ลด min_gap ลงอีกเล็กน้อย)
    densified = []
    last_t = None
    relaxed_gap = max(45, int(min_gap_ms * 0.70))
    for n in best:
        if last_t is None or (n["tMs"] - last_t) >= relaxed_gap:
            densified.append(n)
            last_t = n["tMs"]
    return densified

def main(song_dir: str):
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
                "style": "vocal_first_density_lock",
                "notes": notes
            }
            fn = f"{lanes}_{diff}.json"
            with open(os.path.join(out_dir, fn), "w", encoding="utf-8") as f:
                json.dump(chart, f, ensure_ascii=False, indent=2)
            print("Saved", os.path.join(song_dir, "charts", fn), "notes:", len(notes))
