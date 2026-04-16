import pygame
from pygame.locals import *
import sys

# Set up screen dimensions
SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))

# Create snake and food objects
snake = [(100, 100), (90, 100), (80, 100)]  # initial position of the snake
food = (200, 200)  # initial position of the food

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                snake.append((snake[-1][0], snake[-1][1] - 10))
            elif event.key == pygame.K_DOWN:
                snake.append((snake[-1][0], snake[-1][1] + 10))
            elif event.key == pygame.K_LEFT:
                snake.append((snake[-1][0] - 10, snake[-1][1]))
            elif event.key == pygame.K_RIGHT:
                snake.append((snake[-1][0] + 10, snake[-1][1]))

    # draw everything on the screen
    screen.fill((255, 255, 255))
    for pos in snake:
        pygame.draw.rect(screen, (0, 0, 0), (pos[0], pos[1], 5, 5))
    pygame.draw.rect(screen, (255, 0, 0), (*food, 5, 5))

    # update the display
    pygame.display.flip()

print("Snake game running!")
