import json, random, sys
import numpy as np
import librosa

VOCAB = [
    ["LEFT","UP","RIGHT"],
    ["LEFT","RIGHT","UP","DOWN"],
    ["UP","DOWN","RIGHT","LEFT"],
    ["LEFT","UP","DOWN","RIGHT"],
    ["UP","RIGHT","DOWN","LEFT"],
    ["LEFT","UP","RIGHT","DOWN","LEFT"],
]

def smooth(x, w=8):
    if len(x) < w: return x
    k = np.ones(w)/w
    return np.convolve(x, k, mode="same")

def pick_len(energy, diff):
    # energy ~ 0..1
    if diff == "easy":
        base = 3 if energy < 0.5 else 4
        return base
    if diff == "hard":
        base = 5 if energy < 0.5 else 7
        return base
    # normal
    base = 4 if energy < 0.5 else 5
    return base

def mutate_steps(steps, diff):
    out = steps[:]
    # กันซ้ำติด
    for i in range(1, len(out)):
        if out[i] == out[i-1]:
            out[i] = random.choice([s for s in ["LEFT","UP","RIGHT","DOWN"] if s != out[i-1]])
    # hard เพิ่มโอกาสสลับบางจุด
    if diff == "hard" and len(out) >= 5 and random.random() < 0.35:
        j = random.randint(1, len(out)-2)
        out[j], out[j+1] = out[j+1], out[j]
    return out

def main(audio_path, out_chart="chart.json", diff="normal"):
    y, sr = librosa.load(audio_path, sr=None, mono=True)

    # onset strength (พลังจังหวะ)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_env = smooth(onset_env, w=10)

    # beat tracking
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    if len(beat_times) < 16:
        raise SystemExit("เพลงสั้น/จับ beat ไม่ได้พอ")

    # offset ให้ beat แรกเป็น anchor (แล้วค่อยมีตัวปรับ offset ภายหลังได้)
    offset_ms = int(round(-beat_times[0] * 1000))

    # เอา onset strength เฉพาะตำแหน่ง beat
    beat_onsets = onset_env[beat_frames]
    # normalize 0..1
    bo = beat_onsets - beat_onsets.min()
    bo = bo / (bo.max() + 1e-9)

    # ตั้งความถี่การวางคอมโบ
    if diff == "easy":
        every_beats = 8   # ทุก 2 ห้อง (4/4)
    elif diff == "hard":
        every_beats = 2   # ทุกครึ่งห้อง
    else:
        every_beats = 4   # ทุก 1 ห้อง

    patterns = []

    # หา "downbeat-ish": ทุก 4 beat เลือกตัวที่ onset สูงสุดเป็นจังหวะหนัก
    # แล้วใช้มันเป็น candidate confirm
    heavy_candidates = set()
    for i in range(0, len(beat_times) - 4, 4):
        j = i + int(np.argmax(bo[i:i+4]))
        heavy_candidates.add(j)

    # เลือก anchor ตาม every_beats + ต้องเป็นจังหวะหนักพอ
    for i in range(0, len(beat_times), every_beats):
        # เลือกภายในหน้าต่างเล็ก ๆ รอบ i เพื่อเกาะจังหวะหนัก
        window = range(max(0, i-1), min(len(beat_times), i+2))
        # ให้คะแนน: เป็น heavy candidate + onset สูง
        best = None
        best_score = -1
        for j in window:
            score = bo[j] + (0.25 if j in heavy_candidates else 0.0)
            if score > best_score:
                best_score = score
                best = j

        # ตัดช่วงพลังต่ำมาก (กันอินโทรเงียบ)
        if bo[best] < (0.12 if diff != "hard" else 0.08):
            continue

        energy = float(bo[best])
        target_len = pick_len(energy, diff)

        base = random.choice(VOCAB)
        # ปรับความยาวให้ตรงเป้าหมาย
        steps = (base * ((target_len + len(base)-1)//len(base)))[:target_len]
        steps = mutate_steps(steps, diff)

        t_ms = int(round(beat_times[best] * 1000))
        patterns.append({"tMs": t_ms, "steps": steps})

    chart = {
        "title": "Auto BeatUp",
        "artist": "Unknown",
        "bpm": float(tempo),
        "offsetMs": offset_ms,
        "patterns": patterns
    }

    with open(out_chart, "w", encoding="utf-8") as f:
        json.dump(chart, f, ensure_ascii=False, indent=2)

    print(f"Saved {out_chart}")
    print(f"BPM={float(tempo)} offsetMs={offset_ms} patterns={len(patterns)}")

if __name__ == "__main__":
    audio = "song\\TWICE - Feel Special.wav"
    diff = sys.argv[2] if len(sys.argv) > 2 else "normal"
    main(audio, out_chart="chart.json", diff=diff)
