import pygame

class FX:
    def __init__(self):
        self.center = None         # (text, col, start_now_ms, dur_ms)
        self.bursts = []           # (x,y,col,start_now_ms,dur_ms)
        self.shake_until = 0       # pygame ticks
        self.amp = 0

    def reset(self):
        self.center = None
        self.bursts.clear()
        self.shake_until = 0
        self.amp = 0

    def show(self, text, col, now_ms, dur=420):
        self.center = (text, col, now_ms, dur)

    def burst(self, x, y, col, now_ms, dur=260):
        self.bursts.append((x, y, col, now_ms, dur))

    def shake(self, dur=210, amp=6):
        t = pygame.time.get_ticks()
        self.shake_until = max(self.shake_until, t + dur)
        self.amp = max(self.amp, amp)

    def cam(self):
        t = pygame.time.get_ticks()
        if t >= self.shake_until or self.amp <= 0:
            return 0, 0
        span = self.amp * 2
        ox = (t % span) - self.amp
        oy = ((t // 2) % span) - self.amp
        return ox, oy
