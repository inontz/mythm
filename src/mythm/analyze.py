# analyze.py
import librosa, json, sys

audio = sys.argv[1]

y, sr = librosa.load(audio, mono=True)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
times = librosa.frames_to_time(beats, sr=sr)

data = {
    "bpm": float(tempo),
    "offsetMs": int(-times[0] * 1000),
    "beatsMs": [int(t * 1000) for t in times]
}

json.dump(data, open("analysis.json","w"), indent=2)
print("BPM:", tempo)
