from mythm.config import S_PERFECT, PERFECT, GREAT, MISS_AT

def judge(now, t_ms):
    d = now - t_ms
    if abs(d) <= S_PERFECT:
        return "S.PERFECT", d
    if abs(d) <= PERFECT:
        return "PERFECT", d
    if abs(d) <= GREAT:
        return "GREAT", d
    if d > MISS_AT:
        return "MISS", d
    return "EARLY", d
