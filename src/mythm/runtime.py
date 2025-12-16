import os
import json
from pathlib import Path
import pygame

from mythm.config import (
    W, H, JUDGE_Y, SPAWN_TIME,
    COUNTDOWN_MS, GO_MS,
    GREAT, MISS_AT, KEY_HOLD_MS,
)
from mythm.judge import judge
from mythm.fx import FX
from mythm.input_modes import LR6_KEYS, keymaps_lane_mode
from mythm.renderers import (
    lane_layout_default,
    lane_center_x,
    render_multilane,
    render_lr6_beatup_ui,
    HitFlash,
    lr6_hit_xy_for_lane,
)

# ---------------- Song FS ----------------
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

def load_chart(a, s, lanes, diff):
    p = chart_path(a, s, lanes, diff)
    if not os.path.exists(p):
        return None, f"Missing chart: {p}"
    j = json.load(open(p, encoding="utf-8"))
    notes = sorted(j.get("notes", []), key=lambda n: n["tMs"])
    if len(notes) == 0:
        return notes, "Chart has 0 notes (regen needed)."
    return notes, None

# ---------------- Timing ----------------
def song_now_ms(offset_ms: int) -> int:
    """Lock game time to audio playback position."""
    p = pygame.mixer.music.get_pos()  # ms since play/unpause, pauses stop advancing
    if p < 0:
        p = 0
    return int(p) + int(offset_ms)

# ---------------- UI helpers ----------------
def draw_button(screen, rect, text, font, big=False, enabled=True):
    col = (55, 70, 110) if enabled else (40, 40, 55)
    pygame.draw.rect(screen, col, rect, border_radius=14)
    pygame.draw.rect(screen, (235, 235, 245), rect, width=2, border_radius=14)
    f = font
    s = f.render(text, True, (255, 255, 255) if enabled else (180, 180, 190))
    screen.blit(s, (rect.x + rect.w//2 - s.get_width()//2, rect.y + rect.h//2 - s.get_height()//2))

def main():
    pygame.mixer.pre_init(44100, -16, 2, 2048)
    pygame.init()
    
    pygame.mixer.init()

    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("mythm")
    font = pygame.font.SysFont("Arial", 22)
    big = pygame.font.SysFont("Arial", 30)
    center_font = pygame.font.SysFont("Arial", 64)
    clock = pygame.time.Clock()

    # SFX
    tap_sfx_on = True
    tap_sfx = None
    try:
        tap_sfx = pygame.mixer.Sound(Path("assets", "sfx", "tap.wav"))
        tap_sfx.set_volume(0.6)
        print("Loaded tap sfx:", tap_sfx)
    except Exception as e:
        tap_sfx = None
        print("Tap SFX load failed:", tap_sfx, "|", repr(e))

    song_list = list_songs()
    if not song_list:
        raise SystemExit("No songs found under songs/<artist>/<song>/")

    song_idx = 0
    cur_artist, cur_song = song_list[song_idx]

    # modes
    input_mode = "LR6"  # LANE / LR6
    key_mode = "KEY"    # KEY / NUM (LANE only)
    lanes = 6
    diff = "normal"

    KEYMAP, NUMMAP = keymaps_lane_mode(lanes)
    lane_w, x0 = lane_layout_default(lanes)

    # gameplay
    meta = None
    notes = []
    active = []
    ni = 0
    combo = 0
    offset_ms = 0
    status = ""

    fx = FX()
    flash = HitFlash()

    # hold support
    keys_pressed = [False]*6
    holding = [None]*6  # lane -> note dict or None

    # state machine
    STATE_SELECT = "SELECT"
    STATE_COUNTDOWN = "COUNTDOWN"
    STATE_PLAYING = "PLAYING"
    STATE_PAUSE_CD = "PAUSE_CD"
    state = STATE_SELECT

    # timers
    countdown_until_tick = 0
    go_until_tick = 0
    resume_until_tick = 0
    music_started = False

    # buttons (select screen)
    play_btn = pygame.Rect(W//2 - 120, H - 92, 240, 56)
    sfx_btn = pygame.Rect(20, H - 78, 150, 46)

    def stop_music():
        pygame.mixer.music.stop()

    def start_preview():
        """Loop preview while selecting songs."""
        nonlocal music_started
        stop_music()
        pygame.mixer.music.load(audio_path(cur_artist, cur_song))
        pygame.mixer.music.play(loops=-1)
        music_started = True

    def start_countdown():
        nonlocal state, countdown_until_tick, go_until_tick, music_started
        stop_music()
        music_started = False
        state = STATE_COUNTDOWN
        t = pygame.time.get_ticks()
        countdown_until_tick = t + COUNTDOWN_MS
        go_until_tick = 0

    def start_song_playback():
        nonlocal state, music_started, go_until_tick
        stop_music()
        pygame.mixer.music.load(audio_path(cur_artist, cur_song))
        pygame.mixer.music.play()
        music_started = True
        go_until_tick = pygame.time.get_ticks() + GO_MS
        state = STATE_PLAYING

    def pause_with_resume_countdown():
        nonlocal state, resume_until_tick
        pygame.mixer.music.pause()
        state = STATE_PAUSE_CD
        resume_until_tick = pygame.time.get_ticks() + COUNTDOWN_MS

    def resume_after_countdown_if_ready():
        nonlocal state, go_until_tick
        pygame.mixer.music.unpause()
        go_until_tick = pygame.time.get_ticks() + GO_MS
        state = STATE_PLAYING

    def reload_song_assets():
        """Load meta/chart and reset gameplay trackers."""
        nonlocal meta, notes, active, ni, combo, offset_ms, status, holding
        meta = load_meta(cur_artist, cur_song)
        offset_ms = int(meta.get("offsetMs", 0))

        use_lanes = 6 if input_mode == "LR6" else lanes
        n2, err = load_chart(cur_artist, cur_song, use_lanes, diff)
        notes = n2 if n2 is not None else []
        status = err or f"Loaded {len(notes)} notes."
        active = []
        ni = 0
        combo = 0
        holding = [None]*6

    def set_song_index(new_idx):
        nonlocal song_idx, cur_artist, cur_song
        song_idx = new_idx % len(song_list)
        cur_artist, cur_song = song_list[song_idx]
        reload_song_assets()
        if state == STATE_SELECT:
            start_preview()

    def lane_keys_mapping():
        if input_mode == "LR6":
            return LR6_KEYS
        return (KEYMAP if key_mode == "KEY" else NUMMAP)

    def lane_from_key(key):
        keys = lane_keys_mapping()
        if key in keys:
            return keys[key]
        return None

    def play_tap_sfx():
        if tap_sfx_on and tap_sfx is not None:
            tap_sfx.play()

    # initial load + preview
    reload_song_assets()
    start_preview()

    key_down_until = [0]*6

    running = True
    while running:
        t = pygame.time.get_ticks()
        now = song_now_ms(offset_ms) if music_started else 0

        # spawn only while playing
        if state == STATE_PLAYING and notes:
            while ni < len(notes) and now >= notes[ni]["tMs"] - SPAWN_TIME:
                n = dict(notes[ni])
                n["hit"] = False
                # default type is tap
                n["type"] = n.get("type", "tap")
                if n["type"] == "hold":
                    n["durMs"] = int(n.get("durMs", 500))
                active.append(n)
                ni += 1

        # auto miss (tap + hold start missed)
        if state == STATE_PLAYING and notes:
            for n in active:
                if n["hit"]:
                    continue
                # for hold: if you didn't start it in time, miss
                if now - n["tMs"] > MISS_AT and (n.get("type","tap") == "tap" or not n.get("hold_started", False)):
                    n["hit"] = True
                    combo = 0
                    fx.show_center("MISS", (255, 90, 90), now)
                    fx.shake_miss(now)

        # hold processing (must stay pressed until end)
        if state == STATE_PLAYING:
            for lane, hn in enumerate(holding):
                if not hn:
                    continue
                end_t = hn["tMs"] + int(hn.get("durMs", 500))
                # release early -> miss
                if not keys_pressed[lane] and now < end_t - 30:
                    hn["hit"] = True
                    holding[lane] = None
                    combo = 0
                    fx.show_center("MISS", (255, 90, 90), now)
                    fx.shake_miss(now)
                    continue
                # success
                if now >= end_t:
                    hn["hit"] = True
                    holding[lane] = None
                    combo += 1
                    fx.show_center("PERFECT", (160, 220, 255), now)
                    hx, hy = lr6_hit_xy_for_lane(lane) if input_mode == "LR6" else (lane_center_x(x0, lane_w, lane), JUDGE_Y)
                    flash.add(hx, hy, now, (160, 220, 255))
                    play_tap_sfx()

        # events
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
                break

            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                    break

                # global toggles
                if e.key == pygame.K_m:
                    tap_sfx_on = not tap_sfx_on
                    fx.show_center("SFX ON" if tap_sfx_on else "SFX OFF", (220,220,255), now, dur=420)

                # SELECT navigation
                if state == STATE_SELECT:
                    if e.key == pygame.K_LEFT:
                        set_song_index(song_idx - 1)
                    elif e.key == pygame.K_RIGHT:
                        set_song_index(song_idx + 1)
                    elif e.key == pygame.K_RETURN:
                        start_countdown()
                    continue

                # COUNTDOWN: allow cancel to select
                if state == STATE_COUNTDOWN:
                    if e.key == pygame.K_BACKSPACE:
                        state = STATE_SELECT
                        start_preview()
                    continue

                # pause/resume
                if state == STATE_PLAYING and e.key == pygame.K_p:
                    pause_with_resume_countdown()
                    continue

                # while paused countdown, ignore hits
                if state == STATE_PAUSE_CD:
                    continue

                # song/mode controls while playing
                if e.key == pygame.K_LEFT:
                    set_song_index(song_idx - 1)
                    state = STATE_SELECT
                    continue
                if e.key == pygame.K_RIGHT:
                    set_song_index(song_idx + 1)
                    state = STATE_SELECT
                    continue

                # difficulty SHIFT+1/2/3
                if e.key in (pygame.K_1, pygame.K_2, pygame.K_3) and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    diff = ["easy", "normal", "hard"][e.key - pygame.K_1]
                    reload_song_assets()
                    state = STATE_SELECT
                    start_preview()
                    continue

                # toggle mode F4
                if e.key == pygame.K_F4:
                    input_mode = "LANE" if input_mode == "LR6" else "LR6"
                    reload_song_assets()
                    state = STATE_SELECT
                    start_preview()
                    continue

                # lane toggles (LANE only)
                if input_mode == "LANE":
                    if e.key == pygame.K_TAB:
                        key_mode = "NUM" if key_mode == "KEY" else "KEY"
                        continue
                    if e.key == pygame.K_F3:
                        lanes = 5 if lanes == 6 else 6
                        KEYMAP, NUMMAP = keymaps_lane_mode(lanes)
                        lane_w, x0 = lane_layout_default(lanes)
                        reload_song_assets()
                        state = STATE_SELECT
                        start_preview()
                        continue

                # hit input (PLAYING only)
                if state != STATE_PLAYING:
                    continue

                lane = lane_from_key(e.key)
                if lane is None:
                    continue
                lane = int(lane)
                if lane < 0 or lane > 5:
                    continue

                keys_pressed[lane] = True
                key_down_until[lane] = now + KEY_HOLD_MS

                # already holding -> ignore new start
                if holding[lane] is not None:
                    continue

                # candidate notes in window (fix "tap not registering")
                cand = [
                    n for n in active
                    if (not n["hit"])
                    and int(n.get("lane", 0)) == lane
                    and abs(now - n["tMs"]) <= GREAT
                ]
                if not cand:
                    fx.show_center("MISS", (255, 90, 90), now)
                    fx.shake_miss(now)
                    combo = 0
                    continue

                n = min(cand, key=lambda x: abs(now - x["tMs"]))
                res, err = judge(now, n["tMs"])

                if res in ("S.PERFECT", "PERFECT", "GREAT"):
                    col = (120,255,160) if res == "S.PERFECT" else ((160,220,255) if res == "PERFECT" else (255,220,160))

                    if n.get("type","tap") == "hold":
                        # start holding; do not score until end
                        n["hold_started"] = True
                        holding[lane] = n
                        fx.show_center("HOLD", (200,255,220), now, dur=240)
                        # flash small on start
                        hx, hy = lr6_hit_xy_for_lane(lane) if input_mode == "LR6" else (lane_center_x(x0, lane_w, lane), JUDGE_Y)
                        flash.add(hx, hy, now, (200,255,220), dur=140)
                        play_tap_sfx()
                    else:
                        n["hit"] = True
                        combo += 1
                        fx.show_center(res, col, now)
                        hx, hy = lr6_hit_xy_for_lane(lane) if input_mode == "LR6" else (lane_center_x(x0, lane_w, lane), JUDGE_Y)
                        flash.add(hx, hy, now, col)
                        play_tap_sfx()

                elif res == "MISS":
                    n["hit"] = True
                    combo = 0
                    fx.show_center("MISS", (255, 90, 90), now)
                    fx.shake_miss(now)

            if e.type == pygame.KEYUP:
                lane = lane_from_key(e.key)
                if lane is not None:
                    lane = int(lane)
                    if 0 <= lane <= 5:
                        keys_pressed[lane] = False

            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if state == STATE_SELECT:
                    if play_btn.collidepoint(e.pos):
                        start_countdown()
                    if sfx_btn.collidepoint(e.pos):
                        tap_sfx_on = not tap_sfx_on
                # no mouse actions during play

        # state transitions
        if state == STATE_COUNTDOWN:
            if pygame.time.get_ticks() >= countdown_until_tick:
                # reset gameplay and start real playback
                reload_song_assets()
                start_song_playback()

        if state == STATE_PAUSE_CD:
            if pygame.time.get_ticks() >= resume_until_tick:
                resume_after_countdown_if_ready()

        # cleanup old notes
        if state == STATE_PLAYING:
            active = [n for n in active if now - n["tMs"] <= 2000]

        # ---------- DRAW ----------
        screen.fill((20, 20, 30))

        # camera shake
        ox, oy = fx.cam(now)

        # select screen
        if state == STATE_SELECT:
            # title
            title =  cur_song
            artist =  cur_artist
            screen.blit(big.render(f"[{song_idx+1}/{len(song_list)}] {title} - {artist}", True, (255,255,255)), (20, 18))
            screen.blit(font.render("←/→ choose song | ENTER or PLAY to start | SHIFT+1/2/3 diff | F4 mode | M toggle sfx", True, (200,200,210)), (20, 52))

            # buttons
            draw_button(screen, play_btn, "PLAY", big)
            draw_button(screen, sfx_btn, f"SFX {'ON' if tap_sfx_on else 'OFF'}", font)

            # hint current mode
            mode_txt = f"MODE={input_mode}" + (f" | lanes={lanes} key={key_mode}" if input_mode == "LANE" else " | LR6 keys: 1 4 7 | 3 6 9")
            screen.blit(font.render(mode_txt, True, (255,200,120)), (20, 86))

        else:
            # gameplay draw
            if input_mode == "LR6":
                render_lr6_beatup_ui(screen, active, now, key_down_until, font, flash)
            else:
                render_multilane(screen, active, now, lanes, lane_w, x0, key_mode, key_down_until[:lanes], font)

            # center messages + shake already
            # center text from fx
            if fx.center_text:
                text, col, stt, dur = fx.center_text
                tt = (now - stt) / dur
                if tt >= 1:
                    fx.center_text = None
                else:
                    alpha = int(255*(1-tt))
                    s = center_font.render(text, True, col)
                    s.set_alpha(alpha)
                    screen.blit(s, (W//2 - s.get_width()//2 + ox, H//2 - s.get_height()//2 + oy))

            # countdown overlays
            if state == STATE_COUNTDOWN:
                remain = max(0, countdown_until_tick - pygame.time.get_ticks())
                num = 1 + (remain // 1000)
                s = center_font.render(str(int(num)), True, (255,255,255))
                screen.blit(s, (W//2 - s.get_width()//2, H//2 - s.get_height()//2))

            if state == STATE_PAUSE_CD:
                remain = max(0, resume_until_tick - pygame.time.get_ticks())
                num = 1 + (remain // 1000)
                s = center_font.render(str(int(num)), True, (255,255,255))
                screen.blit(s, (W//2 - s.get_width()//2, H//2 - s.get_height()//2))
                pause_txt = font.render("PAUSED", True, (255, 220, 160))
                screen.blit(pause_txt, (W//2 - pause_txt.get_width()//2, 36))

            if go_until_tick and pygame.time.get_ticks() < go_until_tick:
                s = center_font.render("GO", True, (200,255,200))
                screen.blit(s, (W//2 - s.get_width()//2, H//2 - s.get_height()//2))

            # HUD
            title = cur_song
            artist = cur_artist
            screen.blit(big.render(f"{title} - {artist}", True, (255,255,255)), (20+ox, 12+oy))
            screen.blit(font.render(f"diff={diff.upper()} | Combo={combo} | offsetMs={offset_ms} | SFX={'ON' if tap_sfx_on else 'OFF'} | P pause", True, (255,200,120)), (20+ox, 44+oy))
            if status:
                screen.blit(font.render(status, True, (180,180,255)), (20+ox, 72+oy))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
