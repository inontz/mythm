import os
import json
import pygame

from mythm.config import (
    W, H, JUDGE_Y, SPAWN_TIME,
    COUNTDOWN_MS, GO_MS,
    GREAT, MISS_AT, KEY_HOLD_MS
)
from mythm.judge import judge
from mythm.fx import FX
from mythm.input_modes import LR6_KEYS, keymaps_lane_mode
from mythm.renderers import lane_layout_default, lane_center_x, render_multilane, render_lr6_beatup_ui, HitFlash, lr6_hit_xy_for_lane

# ---------- song fs ----------
def list_songs():
    out = []
    base = "songs"
    if not os.path.isdir(base):
        return out
    for artist in sorted(os.listdir(base)):
        ap = os.path.join(base, artist)
        if not os.path.isdir(ap):
            continue
        for song in sorted(os.listdir(ap)):
            sp = os.path.join(ap, song)
            if os.path.isdir(sp):
                out.append((artist, song))
    return out

def song_base(a, s): return os.path.join("songs", a, s)
def meta_path(a, s): return os.path.join(song_base(a, s), "meta.json")
def audio_path(a, s): return os.path.join(song_base(a, s), "song.wav")

def chart_path(a, s, lanes, diff):
    return os.path.join(song_base(a, s), "charts", f"{lanes}_{diff}.json")

def load_meta(a, s):
    return json.load(open(meta_path(a, s), encoding="utf-8"))

def save_meta(a, s, meta):
    with open(meta_path(a, s), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def load_chart(a, s, lanes, diff):
    p = chart_path(a, s, lanes, diff)
    if not os.path.exists(p):
        return None, f"Missing chart: {p}"
    j = json.load(open(p, encoding="utf-8"))
    notes = sorted(j.get("notes", []), key=lambda n: n["tMs"])
    if len(notes) == 0:
        return notes, "Chart has 0 notes (regen needed)."
    return notes, None

# ---------- timing ----------
def song_now_ms(offset_ms: int):
    p = pygame.mixer.music.get_pos()  # ms since music play()
    if p < 0:
        p = 0
    return p + int(offset_ms)

def main():
    pygame.init()
    pygame.mixer.pre_init(44100, -16, 2, 2048)
    pygame.mixer.init()

    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("mythm")
    font = pygame.font.SysFont("Arial", 22)
    big = pygame.font.SysFont("Arial", 30)
    center_font = pygame.font.SysFont("Arial", 64)
    clock = pygame.time.Clock()

    song_list = list_songs()
    if not song_list:
        raise SystemExit("No songs found under songs/<artist>/<song>/")

    song_idx = 0
    cur_artist, cur_song = song_list[song_idx]

    # modes
    input_mode = "LANE"  # LANE / LR6
    key_mode = "KEY"     # KEY / NUM (LANE only)

    lanes = 6
    diff = "normal"

    KEYMAP, NUMMAP = keymaps_lane_mode(lanes)
    lane_w, x0 = lane_layout_default(lanes)

    fx = FX()
    flash = HitFlash()


    # auto calibration
    cal_errors = []
    cal_apply_every = 12
    cal_gain = 0.35
    cal_limit_step = 12
    cal_min_hits_to_save = 24

    meta = None
    notes = []
    active = []
    ni = 0
    combo = 0
    offset_ms = 0
    status = ""

    # timing
    countdown_until_tick = 0
    song_start_tick = 0
    go_until_tick = 0
    music_started = False

    # highlight
    key_down_until = [0]*6  # always keep 6 slots (LR6 uses 0..5, LANE uses 0..lanes-1)

    # def apply_auto_calibration(now):
    #     nonlocal offset_ms, cal_errors, status, meta
    #     if len(cal_errors) < cal_apply_every:
    #         return
    #     recent = cal_errors[-cal_apply_every:]
    #     avg = sum(recent) / len(recent)
    #     step = int(round(-avg * cal_gain))
    #     step = max(-cal_limit_step, min(cal_limit_step, step))
    #     if step == 0:
    #         return
    #     offset_ms += step
    #     meta["offsetMs"] = int(offset_ms)
    #     fx.show("CAL", (200,220,255), now, dur=260)

    #     if len(cal_errors) >= cal_min_hits_to_save:
    #         try:
    #             save_meta(cur_artist, cur_song, meta)
    #             status = f"AutoCal saved offsetMs={offset_ms} (avg err {avg:+.1f}ms)"
    #         except Exception:
    #             pass

    def restart_song(save_prev=True):
        nonlocal cur_artist, cur_song, meta, notes, offset_ms, status
        nonlocal active, ni, combo, cal_errors
        nonlocal countdown_until_tick, song_start_tick, go_until_tick, music_started
        nonlocal key_down_until

        cur_artist, cur_song = song_list[song_idx]

        if save_prev and meta is not None:
            try:
                save_meta(cur_artist, cur_song, meta)
            except Exception:
                pass

        meta = load_meta(cur_artist, cur_song)
        offset_ms = int(meta.get("offsetMs", 0))

        # LR6 always uses 6 lanes charts
        use_lanes = 6 if input_mode == "LR6" else lanes
        n2, err = load_chart(cur_artist, cur_song, use_lanes, diff)
        notes = n2 if n2 is not None else []
        status = err or f"Loaded {len(notes)} notes."

        fx.reset()
        key_down_until = [0]*6

        pygame.mixer.music.stop()
        pygame.mixer.music.load(audio_path(cur_artist, cur_song))

        t = pygame.time.get_ticks()
        countdown_until_tick = t + COUNTDOWN_MS
        song_start_tick = countdown_until_tick
        go_until_tick = 0
        music_started = False

        active = []
        ni = 0
        combo = 0
        cal_errors = []

    restart_song(save_prev=False)

    running = True
    while running:
        t = pygame.time.get_ticks()

        # start music after countdown

        if (not music_started) and pygame.time.get_ticks() >= song_start_tick:
            pygame.mixer.music.play()
            music_started = True
            go_until_tick = pygame.time.get_ticks() + GO_MS

        now = song_now_ms(offset_ms) if music_started else 0

        ox, oy = fx.cam()

        # spawn
        if music_started and notes:
            while ni < len(notes) and now >= notes[ni]["tMs"] - SPAWN_TIME:
                n = dict(notes[ni])
                n["hit"] = False
                active.append(n)
                ni += 1

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False

            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False

                # song navigation
                if e.key == pygame.K_LEFT:
                    song_idx = (song_idx - 1) % len(song_list)
                    restart_song()
                    continue
                if e.key == pygame.K_RIGHT:
                    song_idx = (song_idx + 1) % len(song_list)
                    restart_song()
                    continue

                # toggle mode
                if e.key == pygame.K_F4:
                    input_mode = "LR6" if input_mode == "LANE" else "LANE"
                    fx.show(f"MODE {input_mode}", (220,220,255), now, dur=450)
                    # when entering/exiting LR6, reload chart with correct lanes
                    restart_song(save_prev=False)
                    continue

                # difficulty
                if e.key in (pygame.K_1, pygame.K_2, pygame.K_3) and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    diff = ["easy","normal","hard"][e.key - pygame.K_1]
                    restart_song()
                    continue

                # LANE-only toggles
                if input_mode == "LANE":
                    if e.key == pygame.K_TAB:
                        key_mode = "NUM" if key_mode == "KEY" else "KEY"
                        fx.show(f"KEY {key_mode}", (220,220,255), now, dur=350)
                        continue
                    if e.key == pygame.K_F3:
                        lanes = 5 if lanes == 6 else 6
                        KEYMAP, NUMMAP = keymaps_lane_mode(lanes)
                        lane_w, x0 = lane_layout_default(lanes)
                        restart_song()
                        continue

                # HIT (only when started)
                if not (music_started and notes):
                    continue

                # ----- LR6 MODE -----
                if input_mode == "LR6":
                    if e.key not in LR6_KEYS:
                        continue
                    lane = LR6_KEYS[e.key]  # 0..5
                    key_down_until[lane] = now + KEY_HOLD_MS

                    cand = [n for n in active if (not n["hit"]) and int(n.get("lane",0)) == lane and now >= n["tMs"] - GREAT]
                    if not cand:
                        fx.show("MISS", (255,90,90), now)
                        fx.shake()
                        combo = 0
                        continue

                    n = min(cand, key=lambda x: abs(now - x["tMs"]))
                    res, err = judge(now, n["tMs"])

                    if res in ("S.PERFECT","PERFECT","GREAT"):
                        n["hit"] = True
                        combo += 1
                        cal_errors.append(err)

                        col = (120,255,160) if res=="S.PERFECT" else ((160,220,255) if res=="PERFECT" else (255,220,160))
                        fx.show(res, col, now)
                        hx, hy = lr6_hit_xy_for_lane(lane)
                        col = (120,255,160) if res=="S.PERFECT" else ((160,220,255) if res=="PERFECT" else (255,220,160))
                        flash.add(hx, hy, now, col)
                        # fx.burst(bx + ox, by + oy, col, now)

                        # apply_auto_calibration(now)
                    elif res == "MISS":
                        n["hit"] = True
                        combo = 0
                        fx.show("MISS", (255,90,90), now)
                        fx.shake()
                    continue

                # ----- LANE MODE -----
                keys = KEYMAP if key_mode == "KEY" else NUMMAP
                if e.key not in keys:
                    continue
                lane = keys[e.key]
                if lane >= lanes:
                    continue

                key_down_until[lane] = now + KEY_HOLD_MS

                cand = [n for n in active if (not n["hit"]) and int(n.get("lane",0)) == lane and now >= n["tMs"] - GREAT]
                if not cand:
                    fx.show("MISS", (255,90,90), now)
                    fx.shake()
                    combo = 0
                    continue

                n = min(cand, key=lambda x: abs(now - x["tMs"]))
                res, err = judge(now, n["tMs"])

                if res in ("S.PERFECT","PERFECT","GREAT"):
                    n["hit"] = True
                    combo += 1
                    cal_errors.append(err)

                    col = (120,255,160) if res=="S.PERFECT" else ((160,220,255) if res=="PERFECT" else (255,220,160))
                    fx.show(res, col, now)
                    fx.burst(lane_center_x(x0, lane_w, lane)+ox, JUDGE_Y+oy, col, now)

                    # apply_auto_calibration(now)
                elif res == "MISS":
                    n["hit"] = True
                    combo = 0
                    fx.show("MISS", (255,90,90), now)
                    fx.shake()

        # auto miss
        if music_started and notes:
            for n in active:
                if (not n["hit"]) and (now - n["tMs"] > MISS_AT):
                    n["hit"] = True
                    combo = 0
                    fx.show("MISS", (255,90,90), now)
                    fx.shake()

        # cleanup
        active = [n for n in active if (now - n["tMs"] <= 1500)]

        # draw
        screen.fill((20,20,30))

        if input_mode == "LR6":
            render_lr6_beatup_ui(screen, active, now, key_down_until, font, flash)

        else:
            render_multilane(screen, active, now, lanes, lane_w, x0, key_mode, key_down_until[:lanes], font)

        # burst effects
        for b in fx.bursts[:]:
            x, y, col, st, dur = b
            tt = (now - st) / dur
            if tt >= 1:
                fx.bursts.remove(b)
                continue
            r = int(16 + 44*tt)
            a = int(190*(1-tt))
            surf = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*col, a), (r, r), r, width=4)
            screen.blit(surf, (x - r, y - r))

        # center text
        if fx.center:
            txt, col, st, dur = fx.center
            tt = (now - st) / dur
            if tt >= 1:
                fx.center = None
            else:
                alpha = int(255 * (1-tt))
                s = center_font.render(txt, True, col)
                s.set_alpha(alpha)
                screen.blit(s, (W//2 - s.get_width()//2 + ox, H//2 - s.get_height()//2 + oy))

        # countdown / GO
        if not music_started:
            remain = max(0, countdown_until_tick - t)
            num = 1 + (remain // 1000)
            s = center_font.render(str(int(num)), True, (255,255,255))
            screen.blit(s, (W//2 - s.get_width()//2, H//2 - s.get_height()//2))
        elif go_until_tick and t < go_until_tick:
            s = center_font.render("GO", True, (200,255,200))
            screen.blit(s, (W//2 - s.get_width()//2, H//2 - s.get_height()//2))

        # HUD
        # title = meta.get("title", cur_song) if meta else cur_song
        # artist = meta.get("artist", cur_artist) if meta else cur_artist
        screen.blit(big.render(f"[{song_idx+1}/{len(song_list)}] {cur_song} - {cur_artist}", True, (255,255,255)), (20+ox, 12+oy))

        if input_mode == "LR6":
            screen.blit(font.render("MODE=LR6 (F4)  |  LR6 keys: 1 4 7 | 3 6 9", True, (200,200,210)), (20+ox, 46+oy))
        else:
            screen.blit(font.render(f"MODE=LANE (F4) | lanes={lanes}(F3) | key={key_mode}(TAB)", True, (200,200,210)), (20+ox, 46+oy))

        screen.blit(font.render(f"diff={diff.upper()} (SHIFT+1/2/3) | song(←/→) | Combo={combo} | offsetMs={offset_ms}", True, (255,200,120)), (20+ox, 76+oy))
        if status:
            screen.blit(font.render(status, True, (180,180,255)), (20+ox, 104+oy))

        pygame.display.flip()
        clock.tick(60)

    try:
        if meta is not None:
            save_meta(cur_artist, cur_song, meta)
    except Exception:
        pass

    pygame.quit()

if __name__ == "__main__":
    main()
