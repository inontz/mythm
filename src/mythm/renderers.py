import pygame
from mythm.config import BASE_R, NEAR_SCALE, W, H, JUDGE_Y, SPAWN_TIME, LR6_GAP_PX, LR6_LANE_W, LR6_LANE_PAD



class HitFlash:
    def __init__(self):
        self.events = []  # (x,y, start_now, dur, color)

    def add(self, x, y, now, color, dur=180):
        self.events.append((x, y, now, dur, color))

    def draw(self, screen, now):
        for ev in self.events[:]:
            x,y,st,dur,col = ev
            t = (now - st) / dur
            if t >= 1:
                self.events.remove(ev)
                continue
            # expanding ring + fade
            r = int(18 + 70*t)
            a = int(180*(1-t))
            surf = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*col, a), (r, r), r, width=6)
            screen.blit(surf, (x-r, y-r))
            
def lane_layout_default(lanes: int):
    lane_w = 90 if lanes == 6 else 110
    x0 = (W - lanes * lane_w) // 2
    return lane_w, x0

def lane_center_x(x0, lane_w, lane):
    return x0 + lane * lane_w + lane_w // 2

def labels_lane_mode(lanes, key_mode):
    if lanes == 6:
        return ["A","S","D","J","K","L"] if key_mode == "KEY" else ["1","2","3","4","5","6"]
    return ["A","S","D","K","L"] if key_mode == "KEY" else ["1","2","3","4","5"]


def _rows_y():
    center_y = H // 2
    row_gap = 130
    return [center_y + row_gap, center_y, center_y - row_gap]  # bottom, mid, top

def _judge_x():
    # แยกมือซ้าย/ขวาให้เหมือน BeatUp (กว้างหน่อย)
    hand_gap = 250
    return W//2 - hand_gap, W//2 + hand_gap

def lr6_lane_center_xy(lane: int):
    ys = _rows_y()
    lx, rx = _judge_x()
    if lane in (0,1,2):
        return lx, ys[lane]          # 0 bottom,1 mid,2 top
    return rx, ys[lane-3]            # 3 bottom,4 mid,5 top

def _draw_panel(surface, rect, radius=16):
    # panel base
    pygame.draw.rect(surface, (25, 25, 35), rect, border_radius=radius)
    # subtle inner highlight
    inner = rect.inflate(-10, -10)
    pygame.draw.rect(surface, (40, 40, 60), inner, border_radius=radius-6)

def _arrow_points(center, direction, size=18):
    x, y = center
    s = size
    if direction == "UP":
        return [(x, y-s), (x-s, y+s), (x+s, y+s)]
    if direction == "DOWN":
        return [(x, y+s), (x-s, y-s), (x+s, y-s)]
    if direction == "LEFT":
        return [(x-s, y), (x+s, y-s), (x+s, y+s)]
    # RIGHT
    return [(x+s, y), (x-s, y-s), (x-s, y+s)]

def _draw_arrow(surface, center, direction, pressed=False):
    # BeatUp 느낌: outline ลูกศร + pressed เป็น neon fill
    pts = _arrow_points(center, direction, size=18)

    if pressed:
        # glow (วาดหลายชั้นให้ฟุ้ง)
        for w, a in [(10, 40), (6, 70), (3, 140)]:
            glow = pygame.Surface((80, 80), pygame.SRCALPHA)
            pygame.draw.polygon(glow, (90, 255, 120, a), [(p[0]-center[0]+40, p[1]-center[1]+40) for p in pts], width=0)
            surface.blit(glow, (center[0]-40, center[1]-40))
        pygame.draw.polygon(surface, (80, 255, 120), pts, width=0)
        pygame.draw.polygon(surface, (230, 255, 240), pts, width=3)
    else:
        pygame.draw.polygon(surface, (170, 170, 190), pts, width=3)

def render_lr6_beatup_ui(screen, active, now, key_down_until, font, flash: HitFlash):
    panel_w, panel_h = 360, 420
    panel_y = (H - panel_h)//2 + 20

    # ระยะห่างมือซ้าย/ขวา
    hand_gap = 120
    left_x  = W//2 - hand_gap - panel_w
    right_x = W//2 + hand_gap

    left_panel  = pygame.Rect(left_x,  panel_y, panel_w, panel_h)
    right_panel = pygame.Rect(right_x, panel_y, panel_w, panel_h)

    # slot layout
    slot_gap = 14
    slot_h = (panel_h - slot_gap*4)//3
    slot_w = panel_w - 34
    slot_x_in = 17

    row_y = [
        left_panel.y + slot_gap,
        left_panel.y + slot_gap*2 + slot_h,
        left_panel.y + slot_gap*3 + slot_h*2,
    ]

    def slot_rect(panel, i):
        return pygame.Rect(panel.x + slot_x_in, row_y[i], slot_w, slot_h)

    # backgrounds
    def panel_bg(r):
        pygame.draw.rect(screen, (28,28,40), r, border_radius=22)
        inner = r.inflate(-14, -14)
        pygame.draw.rect(screen, (45,45,65), inner, border_radius=18)

    def draw_slot(r, pressed=False):
        pygame.draw.rect(screen, (16,16,24), r, border_radius=18)
        if pressed:
            overlay = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            overlay.fill((90,255,120,55))
            screen.blit(overlay, (r.x, r.y))

    panel_bg(left_panel)
    panel_bg(right_panel)

    # lane mapping per row
    left_labels  = ["7","4","1"]
    right_labels = ["9","6","3"]
    left_lane_by_row  = [2,1,0]
    right_lane_by_row = [5,4,3]

    def slot_target_xy(lane):
        if lane in (2,1,0):
            panel = left_panel
            row = {2:0, 1:1, 0:2}[lane]
        else:
            panel = right_panel
            row = {5:0, 4:1, 3:2}[lane]
        r = slot_rect(panel, row)
        return (r.x + r.w//2, r.y + int(r.h*0.58)), r

    # ✅ เส้นตัดต้องอยู่ตรง target x ของ panel (ไม่ใช่ตรงกลางจอ)
    # ใช้ center ของ slot กลาง (row=1) เป็น ref
    (lx, ly), _ = slot_target_xy(1)  # lane 4/left-middle
    (rx, ry), _ = slot_target_xy(4)  # right-middle
    pygame.draw.line(screen, (220,220,230), (lx, 0), (lx, H), 2)
    pygame.draw.line(screen, (220,220,230), (rx, 0), (rx, H), 2)

    # draw slots + labels
    for i in range(3):
        rL = slot_rect(left_panel, i)
        rR = slot_rect(right_panel, i)

        laneL = left_lane_by_row[i]
        laneR = right_lane_by_row[i]
        pressedL = key_down_until[laneL] > now
        pressedR = key_down_until[laneR] > now

        draw_slot(rL, pressedL)
        draw_slot(rR, pressedR)

        labL = font.render(left_labels[i], True, (235,235,245))
        labR = font.render(right_labels[i], True, (235,235,245))
        screen.blit(labL, (rL.x + 14, rL.y + 10))
        screen.blit(labR, (rR.x + 14, rR.y + 10))

    # ---- big arrow note (direction by lane) + scale near judge ----
    def arrow_poly(center, lane, size):
        x, y = center
        s = size
        if lane == 1:  # LEFT
            return [(x-s, y), (x+s, y-s), (x+s, y+s)]
        if lane == 4:  # RIGHT
            return [(x+s, y), (x-s, y-s), (x-s, y+s)]
        if lane == 2:  # ↖
            return [(x-s, y-s), (x+s, y-s), (x-s, y+s)]
        if lane == 5:  # ↗
            return [(x+s, y-s), (x-s, y-s), (x+s, y+s)]
        if lane == 0:  # ↙
            return [(x-s, y+s), (x+s, y+s), (x-s, y-s)]
        return [(x+s, y+s), (x-s, y+s), (x+s, y-s)]  # 3 ↘

    def draw_note_circle(pos, scale, pressed=False):
        x, y = pos
        r = int(12 * scale)          # ขนาดหลัก
        ring = max(2, int(3 * scale))

        if pressed:
            # glow
            glow_r = r + 18
            surf = pygame.Surface((glow_r*2, glow_r*2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (90,255,120,70), (glow_r, glow_r), glow_r)
            screen.blit(surf, (x-glow_r, y-glow_r))

        # main circle
        pygame.draw.circle(screen, (255,210,210), (x, y), r)
        pygame.draw.circle(screen, (255,255,255), (x, y), r, width=ring)

    # notes travel + scale when close to judge
    # notes travel + scale when close to judge
    for n in active:
        if n.get("hit"):
            continue

        lane = max(0, min(5, int(n.get("lane", 0))))
        (tx, ty), _ = slot_target_xy(lane)

        t0 = int(n.get("tMs", 0))
        note_type = n.get("type", "tap")
        dur = int(n.get("durMs", 500)) if note_type == "hold" else 0
        t1 = t0 + dur

        # progress for head (start)
        p = (now - (t0 - SPAWN_TIME)) / max(1, SPAWN_TIME)  # 0..1 at judge
        if p < 0 or p > 1.25:
            continue

        if lane in (2,1,0):
            start_x = -180
            x = int(start_x + max(0.0, min(1.0, p)) * (tx - start_x))
        else:
            start_x = W + 180
            x = int(start_x + max(0.0, min(1.0, p)) * (tx - start_x))

        # ✅ โตตอนใกล้เส้น (ใกล้ 1.0 ใหญ่สุด)
        pp = max(0.0, min(1.0, p))
        scale = 0.95 + (pp ** 2.2) * NEAR_SCALE

        pressed = key_down_until[lane] > now

        # HOLD body: draw bar from head->tail (tail = end time)
        if note_type == "hold":
            p_end = (now - (t1 - SPAWN_TIME)) / max(1, SPAWN_TIME)
            p_end = max(0.0, min(1.25, p_end))

            if lane in (2,1,0):
                x_end = int(start_x + max(0.0, min(1.0, p_end)) * (tx - start_x))
            else:
                x_end = int(start_x + max(0.0, min(1.0, p_end)) * (tx - start_x))

            r_bar = int(BASE_R * scale)
            bar_h = max(10, int(r_bar * 1.05))
            bx = min(x, x_end)
            bw = abs(x - x_end)
            if bw < 4:
                bw = 4
            bar = pygame.Rect(bx, ty - bar_h//2, bw, bar_h)

            if pressed:
                overlay = pygame.Surface((bar.w, bar.h), pygame.SRCALPHA)
                overlay.fill((90, 255, 120, 55))
                screen.blit(overlay, (bar.x, bar.y))

            pygame.draw.rect(screen, (255,210,210), bar, border_radius=bar_h//2)
            pygame.draw.rect(screen, (255,255,255), bar, width=3, border_radius=bar_h//2)

        draw_note_circle((x, ty), scale, pressed=pressed)


    # ✅ hit flash overlay (ต้องเรียกหลังวาด pad/notes)
    flash.draw(screen, now)

        
def render_multilane(screen, active, now, lanes, lane_w, x0, key_mode, key_down_until, font):
    labs = labels_lane_mode(lanes, key_mode)

    for i in range(lanes):
        x = x0 + i * lane_w
        pygame.draw.rect(screen, (60,60,85), (x, 0, lane_w-6, H), border_radius=8)
        pygame.draw.line(screen, (255,255,255), (x, JUDGE_Y), (x+lane_w-6, JUDGE_Y), 2)

        if key_down_until[i] > now:
            remain = key_down_until[i] - now
            alpha = int(160 * (remain / 120))
            overlay = pygame.Surface((lane_w-6, H), pygame.SRCALPHA)
            overlay.fill((180,220,255, max(0, min(255, alpha))))
            screen.blit(overlay, (x, 0))

        pad = pygame.Rect(x, H-42, lane_w-6, 36)
        pygame.draw.rect(screen, (35,35,50), pad, border_radius=8)
        screen.blit(font.render(labs[i], True, (220,220,220)), (x+10, H-36))

    for n in active:
        if n["hit"]:
            continue
        p = (now - (n["tMs"] - SPAWN_TIME)) / max(1, SPAWN_TIME)
        if p < 0:
            continue
        y = p * JUDGE_Y
        if 0 < y < H:
            lane = int(n.get("lane", 0))
            cx = lane_center_x(x0, lane_w, lane)
            pygame.draw.circle(screen, (255,210,210), (cx, int(y)), 14)

def lr6_x_positions():
    # 3 lanes left + GAP + 3 lanes right
    lane_w = LR6_LANE_W
    gap = LR6_GAP_PX
    total_w = 3*lane_w + gap + 3*lane_w
    x0 = (W - total_w) // 2

    xs = []
    # left 0,1,2
    for i in range(3):
        xs.append(x0 + i*lane_w)
    # right 3,4,5
    right_start = x0 + 3*lane_w + gap
    for i in range(3):
        xs.append(right_start + i*lane_w)
    return xs, lane_w

def lr6_rows():
    # spacing ชัด อ่านง่าย
    center_y = H // 2
    row_gap = 120
    return [
        center_y + row_gap,   # bottom -> 1 / 3
        center_y,             # mid    -> 4 / 6
        center_y - row_gap,   # top    -> 7 / 9
    ]
    
def lr6_judge_x():
    # แยกมือซ้าย/ขวาชัด ๆ
    hand_gap = 220   # ยิ่งมาก ยิ่งแยก
    left_jx  = W//2 - hand_gap
    right_jx = W//2 + hand_gap
    return left_jx, right_jx

def lr6_hit_xy_for_lane(lane: int):
    # ต้องเหมือน layout ใน render_lr6_beatup_ui
    panel_w, panel_h = 360, 420
    panel_y = (H - panel_h)//2 + 20
    hand_gap = 120
    left_x  = W//2 - hand_gap - panel_w
    right_x = W//2 + hand_gap
    left_panel  = pygame.Rect(left_x,  panel_y, panel_w, panel_h)
    right_panel = pygame.Rect(right_x, panel_y, panel_w, panel_h)

    slot_gap = 14
    slot_h = (panel_h - slot_gap*4)//3
    slot_w = panel_w - 34
    slot_x_in = 17
    row_y = [
        left_panel.y + slot_gap,
        left_panel.y + slot_gap*2 + slot_h,
        left_panel.y + slot_gap*3 + slot_h*2,
    ]
    def slot_rect(panel, i):
        return pygame.Rect(panel.x + slot_x_in, row_y[i], slot_w, slot_h)

    lane = max(0, min(5, int(lane)))
    if lane in (2,1,0):
        panel = left_panel
        row = {2:0, 1:1, 0:2}[lane]
    else:
        panel = right_panel
        row = {5:0, 4:1, 3:2}[lane]
    r = slot_rect(panel, row)
    return (r.x + r.w//2, r.y + int(r.h*0.58))

def render_lr6_horizontal(screen, active, now, key_down_until, font):
    ys = lr6_rows()
    left_jx, right_jx = lr6_judge_x()

    # draw 2 judge lines (vertical)
    pygame.draw.line(screen, (255,255,255), (left_jx, 0), (left_jx, H), 2)
    pygame.draw.line(screen, (255,255,255), (right_jx, 0), (right_jx, H), 2)

    # lane pads (labels)
    # lane -> label
    labs = {2:"7", 1:"4", 0:"1", 5:"9", 4:"6", 3:"3"}

    # draw pads near judge lines
    pad_w, pad_h = 140, 68
    for lane in range(6):
        jx, y = lr6_lane_center_xy(lane)
        x = jx - pad_w//2
        r = pygame.Rect(x, y - pad_h//2, pad_w, pad_h)

        pygame.draw.rect(screen, (60,60,85), r, border_radius=14)

        if key_down_until[lane] > now:
            overlay = pygame.Surface((pad_w, pad_h), pygame.SRCALPHA)
            overlay.fill((200,235,255,140))
            screen.blit(overlay, (x, y - pad_h//2))

        screen.blit(font.render(labs[lane], True, (230,230,230)), (x + 12, y - 14))

    # notes travel horizontally toward judge line
    for n in active:
        if n["hit"]:
            continue

        lane = int(n.get("lane", 0))
        lane = max(0, min(5, lane))

        jx, y = lr6_lane_center_xy(lane)

        p = (now - (n["tMs"] - SPAWN_TIME)) / max(1, SPAWN_TIME)  # 0..1 at judge
        if p < 0:
            continue
        if p > 1.2:
            continue

        # left lanes: from offscreen left -> left_jx
        # right lanes: from offscreen right -> right_jx
        if lane in (0,1,2):
            start_x = -80
            x = int(start_x + p * (jx - start_x))
        else:
            start_x = W + 80
            x = int(start_x + p * (jx - start_x))

        if -100 < x < W + 100:
            pygame.draw.circle(screen, (255,210,210), (x, int(y)), 16)