import pygame

# LR6 mapping:
# LEFT: 1/4/7 -> lanes 0/1/2
# RIGHT: 3/6/9 -> lanes 3/4/5
LR6_KEYS = {
    pygame.K_1:0, pygame.K_KP1:0,
    pygame.K_4:1, pygame.K_KP4:1,
    pygame.K_7:2, pygame.K_KP7:2,

    pygame.K_3:3, pygame.K_KP3:3,
    pygame.K_6:4, pygame.K_KP6:4,
    pygame.K_9:5, pygame.K_KP9:5,
}

def keymaps_lane_mode(lanes: int):
    # KEY mode:
    # 6 lanes: A S D J K L
    # 5 lanes: A S D K L
    key_6 = {pygame.K_a:0, pygame.K_s:1, pygame.K_d:2, pygame.K_j:3, pygame.K_k:4, pygame.K_l:5}
    key_5 = {pygame.K_a:0, pygame.K_s:1, pygame.K_d:2, pygame.K_k:3, pygame.K_l:4}

    # NUM mode:
    num_6 = {
        pygame.K_1:0, pygame.K_2:1, pygame.K_3:2, pygame.K_4:3, pygame.K_5:4, pygame.K_6:5,
        pygame.K_KP1:0, pygame.K_KP2:1, pygame.K_KP3:2, pygame.K_KP4:3, pygame.K_KP5:4, pygame.K_KP6:5,
    }
    num_5 = {
        pygame.K_1:0, pygame.K_2:1, pygame.K_3:2, pygame.K_4:3, pygame.K_5:4,
        pygame.K_KP1:0, pygame.K_KP2:1, pygame.K_KP3:2, pygame.K_KP4:3, pygame.K_KP5:4,
    }
    return (key_6 if lanes == 6 else key_5), (num_6 if lanes == 6 else num_5)
