import pygame, os, json

W, H = 980, 620
JUDGE_Y = 520
SPAWN_TIME = 2600  # ms

S_PERFECT = 18
PERFECT = 35
GREAT = 80
MISS_AT = 120

KEY_HOLD_MS = 120

def list_songs():
    out = []
    base = "songs"
    for artist in sorted(os.listdir(base)):
        ad = os.path.join(base, artist)
        if not os.path.isdir(ad):
            continue
        for song in sorted(os.listdir(ad)):
            sd = os.path.join(ad, song)
            if os.path.isdir(sd):
                out.append((artist, song))
    return out

def song_base(artist, song):
    return os.path.join("songs", artist, song)

def load_meta(artist, song):
    p = os.path.join(song_base(artist, song), "meta.json")
    return json.load(open(p, encoding="utf-8"))

def save_meta(artist, song, meta):
    p = os.path.join(song_base(artist, song), "meta.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def load_chart(artist, song, lanes, diff):
    base = song_base(artist, song)
    chart_path = os.path.join(base, "charts", f"{lanes}_{diff}.json")
    if not os.path.exists(chart_path):
        return None, f"Missing chart: {chart_path}"
    chart = json.load(open(chart_path, encoding="utf-8"))
    notes = sorted(chart.get("notes", []), key=lambda n: n["tMs"])
    if len(notes) == 0:
        return notes, "Chart has 0 notes (regen needed)."
    return notes, None

def audio_path(artist, song):
    return os.path.join(song_base(artist, song), "song.wav")

def now_ms(offset_ms):
    p = pygame.mixer.music.get_pos()
    if p < 0: p = 0
    return p + offset_ms

def lane_layout(lanes):
    lane_w = 90 if lanes == 6 else 110
    x0 = (W - lanes * lane_w) // 2
    return lane_w, x0

def lane_center_x(x0, lane_w, lane):
    return x0 + lane * lane_w + lane_w // 2

def keymaps(lanes):
    # default
    key_6 = {pygame.K_a:0, pygame.K_s:1, pygame.K_d:2, pygame.K_j:3, pygame.K_k:4, pygame.K_l:5}
    key_5 = {pygame.K_a:0, pygame.K_s:1, pygame.K_d:2, pygame.K_k:3, pygame.K_l:4}
    # num
    num_6 = {
        pygame.K_1:0, pygame.K_KP1:0,
        pygame.K_2:1, pygame.K_KP2:1,
        pygame.K_3:2, pygame.K_KP3:2,
        pygame.K_4:3, pygame.K_KP4:3,
        pygame.K_5:4, pygame.K_KP5:4,
        pygame.K_6:5, pygame.K_KP6:5,
    }
    num_5 = {
        pygame.K_1:0, pygame.K_KP1:0,
        pygame.K_2:1, pygame.K_KP2:1,
        pygame.K_3:2, pygame.K_KP3:2,
        pygame.K_4:3, pygame.K_KP4:3,
        pygame.K_5:4, pygame.K_KP5:4,
    }
    return (key_6 if lanes==6 else key_5), (num_6 if lanes==6 else num_5)

def labels(lanes, mode):
    if lanes == 6:
        return ["A","S","D","J","K","L"] if mode=="KEY" else ["1","2","3","4","5","6"]
    return ["A","S","D","K","L"] if mode=="KEY" else ["1","2","3","4","5"]

def judge(now, tMs):
    d = now - tMs
    if abs(d) <= S_PERFECT:
        return "S.PERFECT", d
    if abs(d) <= PERFECT:
        return "PERFECT", d
    if -GREAT <= d <= GREAT:
        return "GREAT", d
    if d > MISS_AT:
        return "MISS", d
    return "TOO EARLY", d

# ---------- FX ----------
class FX:
    def __init__(self):
        self.center_text = None  # (text, col, start_ms, dur_ms)
        self.bursts = []         # (x,y, col, start, dur)
        self.shake_until = 0
        self.shake_amp = 0

    def show_center(self, text, col, now, dur=420):
        self.center_text = (text, col, now, dur)

    def burst(self, x, y, col, now, dur=260):
        self.bursts.append((x,y,col,now,dur))

    def shake_miss(self, now, dur=210, amp=6):
        t = pygame.time.get_ticks()
        self.shake_until = max(self.shake_until, t + dur)
        self.shake_amp = max(self.shake_amp, amp)

    def cam(self, now_unused=None):
        t = pygame.time.get_ticks()
        if t >= self.shake_until or self.shake_amp <= 0:
            return 0, 0
        span = self.shake_amp * 2
        ox = (t % span) - self.shake_amp
        oy = ((t // 2) % span) - self.shake_amp
        return ox, oy
def main():
    pygame.init()
    pygame.mixer.pre_init(44100, -16, 2, 2048)
    pygame.mixer.init()

    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("SuperStar Rhythm (multi-song)")
    font = pygame.font.SysFont("Arial", 22)
    big = pygame.font.SysFont("Arial", 30)
    center_font = pygame.font.SysFont("Arial", 64)
    clock = pygame.time.Clock()

    song_list = list_songs()
    if not song_list:
        raise SystemExit("No songs found under songs/<artist>/<song_name>/")

    song_idx = 0
    lanes = 6
    diff = "normal"

    key_mode = "KEY"  # KEY / NUM
    KEYMAP, NUMMAP = keymaps(lanes)

    key_down_until = [0]*lanes

    fx = FX()

    # ------- Auto calibration state -------
    # เราจะเก็บ error ของ hit ที่โดน (S/P/G) แล้วค่อยๆ ปรับ offsetMs ให้เข้าใกล้ 0
    cal_errors = []           # list of d(ms)
    cal_apply_every = 12      # ปรับทุก 12 hit
    cal_gain = 0.35           # แรงปรับ (0.2-0.5 กำลังดี)
    cal_limit_step = 12       # จำกัดการปรับต่อครั้ง (ms)
    cal_min_hits_to_save = 24 # ก่อนเซฟกลับ meta.json
    cal_last_saved_offset = None

    meta = None
    notes = None
    offset_ms = 0
    status = ""
    active = []
    ni = 0
    combo = 0

    def reload_keymaps():
        nonlocal KEYMAP, NUMMAP
        KEYMAP, NUMMAP = keymaps(lanes)

    def restart_song(save_meta_first=True):
        nonlocal meta, notes, offset_ms, status, active, ni, combo, key_down_until
        nonlocal cal_errors, cal_last_saved_offset

        artist, song = song_list[song_idx]

        # save meta offset (if changed)
        if save_meta_first and meta is not None and cal_last_saved_offset is not None:
            try:
                save_meta(artist, song, meta)
            except Exception:
                pass

        meta = load_meta(artist, song)
        offset_ms = int(meta.get("offsetMs", 0))
        cal_last_saved_offset = offset_ms
        cal_errors = []

        notes, err = load_chart(artist, song, lanes, diff)
        status = err or f"Loaded {len(notes)} notes."

        fx.center_text = None
        fx.bursts.clear()
        pygame.mixer.music.stop()
        pygame.mixer.music.load(audio_path(artist, song))
        pygame.mixer.music.play()

        active = []
        ni = 0
        combo = 0
        key_down_until = [0]*lanes

    def apply_auto_calibration():
        nonlocal offset_ms, cal_errors, cal_last_saved_offset
        if len(cal_errors) < cal_apply_every:
            return

        recent = cal_errors[-cal_apply_every:]
        avg = sum(recent) / len(recent)  # + = เร็วไป (กดหลังโน้ต), - = ช้าไป (กดก่อนโน้ต)

        # เราต้องการให้ avg เข้าใกล้ 0
        step = int(round(-avg * cal_gain))
        step = max(-cal_limit_step, min(cal_limit_step, step))
        if step == 0:
            return

        offset_ms += step
        meta["offsetMs"] = int(offset_ms)
        cal_last_saved_offset = offset_ms

        fx.show_center("CAL", (200, 220, 255), now_ms(offset_ms), dur=260)

        # เซฟกลับ meta.json เมื่อเริ่มนิ่งพอ
        if len(cal_errors) >= cal_min_hits_to_save:
            try:
                artist, song = song_list[song_idx]
                save_meta(artist, song, meta)
                status_msg = f"AutoCal saved offsetMs={offset_ms} (avg err {avg:+.1f}ms)"
                return status_msg
            except Exception:
                return None
        return None

    restart_song(save_meta_first=False)
    lane_w, x0 = lane_layout(lanes)

    running = True
    while running:
        now = now_ms(offset_ms)
        ox, oy = fx.cam(now)

        # spawn
        if notes:
            while ni < len(notes) and now >= notes[ni]["tMs"] - SPAWN_TIME:
                n = dict(notes[ni])
                n["hit"] = False
                active.append(n)
                ni += 1

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False

            if e.type == pygame.KEYDOWN:
                # song navigation
                if e.key == pygame.K_LEFT:
                    song_idx = (song_idx - 1) % len(song_list)
                    restart_song()
                elif e.key == pygame.K_RIGHT:
                    song_idx = (song_idx + 1) % len(song_list)
                    restart_song()

                # difficulty (SHIFT+1/2/3)
                elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3) and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    diff = ["easy","normal","hard"][e.key - pygame.K_1]
                    restart_song()

                # lanes toggle
                elif e.key == pygame.K_F3:
                    lanes = 5 if lanes == 6 else 6
                    lane_w, x0 = lane_layout(lanes)
                    reload_keymaps()
                    restart_song()

                # key mode
                elif e.key == pygame.K_TAB:
                    key_mode = "NUM" if key_mode == "KEY" else "KEY"

                # hit input
                if notes:
                    keys = KEYMAP if key_mode=="KEY" else NUMMAP
                    if e.key in keys:
                        lane = keys[e.key]
                        if lane >= lanes:
                            continue

                        # key highlight always
                        key_down_until[lane] = now + KEY_HOLD_MS

                        # find candidate note in this lane (tap only in classic charts)
                        cand = [n for n in active if (not n["hit"]) and n["lane"] == lane and now >= n["tMs"] - GREAT]
                        if not cand:
                            fx.show_center("MISS", (255, 90, 90), now)
                            fx.shake_miss(now)
                            combo = 0
                            continue

                        n = min(cand, key=lambda x: abs(now - x["tMs"]))
                        res, err = judge(now, n["tMs"])

                        if res in ("S.PERFECT", "PERFECT", "GREAT"):
                            n["hit"] = True
                            combo += 1
                            cal_errors.append(err)

                            col = (120,255,160) if res=="S.PERFECT" else ((160,220,255) if res=="PERFECT" else (255,220,160))
                            fx.show_center(res, col, now)
                            fx.burst(lane_center_x(x0,lane_w,lane), JUDGE_Y, col, now)

                            maybe = apply_auto_calibration()
                            if maybe:
                                status = maybe

                        elif res == "MISS":
                            n["hit"] = True
                            combo = 0
                            fx.show_center("MISS", (255,90,90), now)
                            fx.shake_miss(now)
                        else:
                            # too early: ไม่ตัดคอมโบ และไม่โชว์ MISS
                            pass

        # auto miss
        if notes:
            for n in active:
                if not n["hit"] and (now - n["tMs"] > MISS_AT):
                    n["hit"] = True
                    combo = 0
                    fx.show_center("MISS", (255,90,90), now)
                    fx.shake_miss(now)

        # cleanup
        active = [n for n in active if now - n["tMs"] <= 1500]

        # draw
        screen.fill((20,20,30))

        # lanes + key highlight overlay
        labs = labels(lanes, key_mode)
        for i in range(lanes):
            x = x0 + i*lane_w
            pygame.draw.rect(screen, (60,60,85), (x+ox, 0+oy, lane_w-6, H), border_radius=8)
            pygame.draw.line(screen, (255,255,255), (x+ox, JUDGE_Y+oy), (x+lane_w-6+ox, JUDGE_Y+oy), 2)

            if key_down_until[i] > now:
                remain = key_down_until[i] - now
                alpha = int(160 * (remain / KEY_HOLD_MS))
                overlay = pygame.Surface((lane_w-6, H), pygame.SRCALPHA)
                overlay.fill((180,220,255, max(0,min(255,alpha))))
                screen.blit(overlay, (x+ox, 0+oy))

            # bottom pad
            pad = pygame.Rect(x+ox, H-42+oy, lane_w-6, 36)
            pygame.draw.rect(screen, (35,35,50), pad, border_radius=8)
            screen.blit(font.render(labs[i], True, (220,220,220)), (x+10+ox, H-36+oy))

        # notes
        if notes:
            st = max(1, SPAWN_TIME)
            for n in active:
                if n["hit"]:
                    continue
                p = (now - (n["tMs"] - st)) / st
                if p < 0:
                    continue
                y = p * JUDGE_Y
                if 0 < y < H:
                    cx = lane_center_x(x0, lane_w, n["lane"])
                    pygame.draw.circle(screen, (255,210,210), (cx+ox, int(y)+oy), 14)

        # bursts (hit effect)
        for b in fx.bursts[:]:
            x,y,col,stt,dur = b
            t = (now - stt) / dur
            if t >= 1:
                fx.bursts.remove(b)
                continue
            r = int(16 + 44*t)
            a = int(190*(1-t))
            surf = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*col, a), (r, r), r, width=4)
            screen.blit(surf, (x-r+ox, y-r+oy))

        # center text (GREAT/PERFECT/S.PERFECT/MISS)
        if fx.center_text:
            text, col, stt, dur = fx.center_text
            t = (now - stt) / dur
            if t >= 1:
                fx.center_text = None
            else:
                alpha = int(255*(1-t))
                s = center_font.render(text, True, col)
                s.set_alpha(alpha)
                screen.blit(s, (W//2 - s.get_width()//2 + ox, H//2 - s.get_height()//2 + oy))

        # HUD
        artist, song = song_list[song_idx]
        screen.blit(big.render(f"{meta.get('title',song)} - {meta.get('artist',artist)}", True, (255,255,255)), (20+ox, 12+oy))
        screen.blit(font.render(f"{lanes} lanes | diff={diff.upper()} (SHIFT+1/2/3) | key={key_mode} (TAB) | song (←/→) | F3 5↔6", True, (200,200,210)), (20+ox, 46+oy))
        screen.blit(font.render(f"Combo: {combo} | offsetMs={offset_ms} | hits(cal)={len(cal_errors)}", True, (255,200,120)), (20+ox, 76+oy))
        if status:
            screen.blit(font.render(status, True, (180,180,255)), (20+ox, 104+oy))

        pygame.display.flip()
        clock.tick(60)

    # เซฟ meta ตอนปิดเกม (กันลืม)
    try:
        artist, song = song_list[song_idx]
        save_meta(artist, song, meta)
    except Exception:
        pass

    pygame.quit()

if __name__ == "__main__":
    main()
