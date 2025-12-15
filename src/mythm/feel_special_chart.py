import json, random, sys
import numpy as np
import librosa

# ===== Tune สำหรับ Feel Special (K-pop) =====
VOCAB = [
    ["LEFT","UP","RIGHT"],
    ["LEFT","RIGHT","UP","DOWN"],
    ["UP","RIGHT","DOWN","LEFT"],
    ["LEFT","UP","DOWN","RIGHT","LEFT"],
    ["RIGHT","UP","LEFT","DOWN","RIGHT"],  # mirror
    ["LEFT","UP","RIGHT","DOWN","LEFT","UP"],
    ["RIGHT","UP","LEFT","DOWN","RIGHT","UP"],  # mirror long
]
STEPS = ["LEFT", "UP", "RIGHT", "DOWN"]

def smooth(x, w=9):
    if len(x) < w: return x
    k = np.ones(w) / w
    return np.convolve(x, k, mode="same")

def mutate_steps(steps, mirror_bias=0.0):
    out = steps[:]
    # กันซ้ำติด
    for i in range(1, len(out)):
        if out[i] == out[i-1]:
            out[i] = random.choice([s for s in STEPS if s != out[i-1]])

    # mirror บ่อยขึ้น (ให้ฟีล chorus)
    if mirror_bias > 0 and random.random() < mirror_bias and len(out) >= 3:
        # swap LEFT<->RIGHT บางตำแหน่ง
        for i in range(len(out)):
            if out[i] == "LEFT": out[i] = "RIGHT"
            elif out[i] == "RIGHT": out[i] = "LEFT"
    return out

def choose_len(energy01, section):  # section: "verse" / "chorus"
    if section == "chorus":
        return 6 if energy01 < 0.55 else 7
    # verse/pre
    return 3 if energy01 < 0.45 else 4

def section_from_rms(rms01):
    # rms01 ~ 0..1; chorus มักดัง/แน่นกว่า
    # threshold จะค่อนข้างเวิร์คกับ Feel Special
    return "chorus" if rms01 >= 0.62 else "verse"

def main(audio_path, out_chart="chart.json", offset_ms=-35):
    y, sr = librosa.load(audio_path, sr=44100, mono=True)

    # 1) แยก percussive สำหรับ K-pop
    y_h, y_p = librosa.effects.hpss(y)

    # 2) onset strength จาก percussive
    onset_env = librosa.onset.onset_strength(y=y_p, sr=sr)
    onset_env = smooth(onset_env, w=11)

    # 3) beat tracking
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    if len(beat_times) < 32:
        raise SystemExit("จับ beat ได้น้อยเกินไป (ไฟล์เสียงอาจมีปัญหา)")

    # 4) ค่า onset ที่ตำแหน่ง beat
    beat_onsets = onset_env[beat_frames]
    bo = beat_onsets - beat_onsets.min()
    bo = bo / (bo.max() + 1e-9)  # 0..1

    # 5) RMS เพื่อแยกท่อน (chorus มักพีค)
    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    rms = smooth(rms, w=21)
    rms01 = (rms - rms.min()) / (rms.max() + 1e-9)

    def rms_at_time(tsec):
        idx = int((tsec * sr) / hop)
        idx = max(0, min(len(rms01)-1, idx))
        return float(rms01[idx])

    patterns = []

    # 6) เลือก anchor แบบ “เน้น beat 2/4” + downbeat
    # และปรับ density ตาม section (verse: 1 bar, chorus: 1/2 bar)
    i = 0
    n = len(beat_times)

    # ตัด intro เงียบมาก ๆ ช่วงแรก: ข้ามจน rms เริ่มขึ้น
    # (ช่วย Feel Special ที่อินโทรบาง)
    while i < n and rms_at_time(beat_times[i]) < 0.18:
        i += 1

    while i < n:
        t = beat_times[i]
        sec_rms = rms_at_time(t)
        section = section_from_rms(sec_rms)

        every_beats = 4 if section == "chorus" else 4  # chorus แน่นกว่า

        # เลือกใน window +-1 beat หา hit หนัก
        win = range(max(0, i-1), min(n, i+2))
        best, best_score = None, -1.0
        for j in win:
            backbeat_bonus = 0.20 if (j % 4 in (1, 3)) else 0.0  # beat 2/4
            downbeat_bonus = 0.10 if (j % 4 == 0) else 0.0       # beat 1
            score = float(bo[j]) + backbeat_bonus + downbeat_bonus
            if score > best_score:
                best_score = score
                best = j

        # ถ้าจังหวะเบามาก ๆ ให้ข้าม (กันเงียบ/เบรก)
        if bo[best] < (0.10 if section == "verse" else 0.08):
            i += every_beats
            continue

        # สร้างคอมโบ
        energy = float(bo[best])
        L = choose_len(energy, section)

        base = random.choice(VOCAB)
        steps = (base * ((L + len(base) - 1)//len(base)))[:L]

        mirror_bias = 0.35 if section == "chorus" else 0.10
        steps = mutate_steps(steps, mirror_bias=mirror_bias)

        t_ms = int(round(beat_times[best] * 1000))
        patterns.append({"tMs": t_ms, "steps": steps})

        i += every_beats

    chart = {
        "title": "Feel Special",
        "artist": "TWICE",
        "bpm": float(tempo),
        "offsetMs": int(offset_ms),
        "patterns": patterns
    }

    with open(out_chart, "w", encoding="utf-8") as f:
        json.dump(chart, f, ensure_ascii=False, indent=2)

    print(f"Saved: {out_chart}")
    print(f"BPM: {float(tempo)}")
    print(f"Patterns: {len(patterns)} (จนจบเพลง)")
    print("Tip: ถ้าเร็ว/แน่นไป ลด chorus density โดยเปลี่ยน every_beats จาก 2 เป็น 4 ในโค้ด")

if __name__ == "__main__":
    audio = sys.argv[1] if len(sys.argv) > 1 else "song.wav"
    # ปรับ offset ได้จาก command line (ms)
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else -35
    out = sys.argv[3] if len(sys.argv) > 3 else "chart.json"
    main(audio, out_chart=out, offset_ms=offset)
