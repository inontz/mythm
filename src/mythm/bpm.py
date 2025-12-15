from pathlib import Path
import sys, json, os
import numpy as np
import librosa

def estimate_bpm(y, sr):
    # onset envelope
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    # tempo candidates (multi-tempo)
    tempos = librosa.beat.tempo(
        onset_envelope=onset_env,
        sr=sr,
        aggregate=None
    )

    if len(tempos) == 0:
        return None

    # เลือก tempo ที่ใกล้ median มากสุด (กัน spike)
    median = np.median(tempos)
    bpm = tempos[np.argmin(np.abs(tempos - median))]
    return int(round(float(bpm)))

def main(artist_dir: Path):
    for song_dir in artist_dir.iterdir():
        audio = Path(song_dir, "song.wav")
        meta_path = Path(song_dir, "meta.json")

        if not os.path.exists(audio):
            raise FileNotFoundError(audio)
        if not os.path.exists(meta_path):
            raise FileNotFoundError(meta_path)

        print("Loading audio...")
        y, sr = librosa.load(audio, sr=44100, mono=True)

        print("Estimating BPM...")
        bpm = estimate_bpm(y, sr)
        if bpm is None:
            print("❌ Cannot detect BPM")
            sys.exit(1)

        print(f"Detected BPM: {bpm}")

        meta = json.load(open(meta_path, encoding="utf-8"))
        old_bpm = meta.get("bpm")

        meta["bpm"] = bpm

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"✅ meta.json updated: bpm {old_bpm} → {bpm}")

if __name__ == "__main__":
    main(artist_dir=Path('songs'))
