from pathlib import Path
import pygame, os, json

W,H=980,620
JUDGE_Y=520
SPAWN=2600
PERFECT=35; GREAT=80; MISS=120

def list_songs():
    songs = []
    base = "songs"
    for artist in os.listdir(base):
        artist_dir = os.path.join(base, artist)
        if not os.path.isdir(artist_dir):
            continue
        for song in os.listdir(artist_dir):
            song_dir = os.path.join(artist_dir, song)
            if os.path.isdir(song_dir):
                songs.append((artist, song))
    return songs

def load_song(artist, song, lanes, diff):
    base = os.path.join("songs", artist, song)
    meta = json.load(open(os.path.join(base, "meta.json"), encoding="utf-8"))
    chart = json.load(open(os.path.join(base, "charts", f"{lanes}_{diff}.json"), encoding="utf-8"))

    notes = sorted(chart["notes"], key=lambda n: n["tMs"])
    return {
        "title": meta["title"],
        "artist": meta["artist"],
        "offset": chart.get("offsetMs", 0),
        "audio": os.path.join(base, "song.wav"),
        "notes": notes
    }

def main():
    pygame.init()
    pygame.mixer.init()
    screen=pygame.display.set_mode((W,H))
    font=pygame.font.SysFont("Arial",22)
    clock=pygame.time.Clock()

    # songs=list_songs()
    # si=0
    lanes=6; diff="normal"
    song_list = list_songs()   # [(artist, song), ...]
    song_idx = 0

    current = load_song(song_list[song_idx][0],
                        song_list[song_idx][1],
                        lanes, diff)
    pygame.mixer.music.load(current)
    pygame.mixer.music.play()

    KEY_ASD={pygame.K_a:0,pygame.K_s:1,pygame.K_d:2,pygame.K_j:3,pygame.K_k:4,pygame.K_l:5}
    KEY_NUM={pygame.K_1:0,pygame.K_2:1,pygame.K_3:2,pygame.K_4:3,pygame.K_5:4,pygame.K_6:5}
    LANE_KEYS=KEY_ASD
    key_mode="ASDJKL"
    key_flash=[0]*lanes

    active=[]
    ni=0; combo=0

    def now_ms(): 
        p=pygame.mixer.music.get_pos()
        return max(0,p)+offset

    running=True
    while running:
        now=now_ms()
        screen.fill((20,20,30))

        while ni<len(notes) and now>=notes[ni]["tMs"]-SPAWN:
            active.append(dict(notes[ni], hit=False))
            ni+=1

        for e in pygame.event.get():
            if e.type==pygame.QUIT: running=False
            if e.type==pygame.KEYDOWN:
                if e.key==pygame.K_TAB:
                    if key_mode=="ASDJKL":
                        key_mode="123456"; LANE_KEYS=KEY_NUM
                    else:
                        key_mode="ASDJKL"; LANE_KEYS=KEY_ASD
                if e.key==pygame.K_F3:
                    lanes=5 if lanes==6 else 6
                    artist, song = song_list[song_idx]
                    current = load_song(artist, song, lanes, diff)
                    # meta,notes,offset,audio=load(songs[si],lanes,diff)
                    pygame.mixer.music.load(audio); pygame.mixer.music.play()
                    active=[]; ni=0; combo=0; key_flash=[0]*lanes
                if e.key in (pygame.K_1,pygame.K_2,pygame.K_3):
                    diff=["easy","normal","hard"][e.key-pygame.K_1]
                    meta,notes,offset,audio=load(songs[si],lanes,diff)
                    pygame.mixer.music.load(audio); pygame.mixer.music.play()
                    active=[]; ni=0; combo=0
                if e.key==pygame.K_LEFT:
                    si=(si-1)%len(songs)
                    meta,notes,offset,audio=load(songs[si],lanes,diff)
                    pygame.mixer.music.load(audio); pygame.mixer.music.play()
                    active=[]; ni=0; combo=0
                if e.key==pygame.K_RIGHT:
                    si=(si+1)%len(songs)
                    meta,notes,offset,audio=load(songs[si],lanes,diff)
                    pygame.mixer.music.load(audio); pygame.mixer.music.play()
                    active=[]; ni=0; combo=0
                if e.key in LANE_KEYS:
                    ln=LANE_KEYS[e.key]
                    if ln<lanes:
                        key_flash[ln]=now+120

        lane_w=90 if lanes==6 else 110
        x0=(W-lanes*lane_w)//2

        for i in range(lanes):
            x=x0+i*lane_w
            pygame.draw.rect(screen,(60,60,80),(x,0,lane_w-6,H))
            pygame.draw.line(screen,(255,255,255),(x,JUDGE_Y),(x+lane_w-6,JUDGE_Y),2)
            if key_flash[i]>now:
                a=int(160*(key_flash[i]-now)/120)
                s=pygame.Surface((lane_w-6,H),pygame.SRCALPHA)
                s.fill((180,220,255,a))
                screen.blit(s,(x,0))

        for n in active[:]:
            if n["hit"]: continue
            p=(now-(n["tMs"]-SPAWN))/SPAWN
            if p<0: continue
            y=p*JUDGE_Y
            if y>H+60:
                active.remove(n); continue
            cx=x0+n["lane"]*lane_w+lane_w//2
            pygame.draw.circle(screen,(255,210,210),(cx,int(y)),14)

        hud=f"{meta['title']} - {meta['artist']} | {lanes}L {diff.upper()} | {key_mode}"
        screen.blit(font.render(hud,True,(255,255,255)),(20,15))
        screen.blit(font.render("← → เพลง | 1-3 diff | F3 lanes | TAB key",True,(200,200,200)),(20,40))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    
if __name__ == "__main__":
    main()
