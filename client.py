import sys
import os
import pygame
import requests

# 桌面 client 在本機執行，透過這個網址呼叫雲端 FastAPI server。
API_BASE_URL = "https://wordle2-wqkq.onrender.com"
#API_BASE_URL = "http://127.0.0.1:8000"

# 顏色定義
COLOR_BG = (18, 18, 19)
COLOR_TEXT = (255, 255, 255)
COLOR_EMPTY = (58, 58, 60)
COLOR_CORRECT = (83, 141, 78)   # 綠色
COLOR_PRESENT = (181, 159, 59)  # 黃色
COLOR_ABSENT = (58, 58, 60)     # 灰色
COLOR_PANEL_LINE = (90, 90, 92)
COLOR_HARD = (220, 80, 80)

pygame.init()
WIDTH, HEIGHT = 700, 650          # 任務三：視窗寬度 500 -> 700
GAME_WIDTH = 500                  # 左側遊戲區寬度（側邊欄從 x=500 開始）
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pygame Wordle + FastAPI Client")
font = pygame.font.SysFont("Arial", 36, bold=True)
small_font = pygame.font.SysFont("Arial", 18)
tiny_font = pygame.font.SysFont("Arial", 14, bold=True)


def fit_font_render(text, max_width, color, start_size=16, bold=True):
    """ 自動縮小字體，確保文字不超出側邊欄 """
    size = start_size
    while size > 8:
        f = pygame.font.SysFont("Arial", size, bold=bold)
        surf = f.render(text, True, color)
        if surf.get_width() <= max_width:
            return surf
        size -= 1
    return pygame.font.SysFont("Arial", 8, bold=bold).render(text, True, color)


class WordleGame:
    def __init__(self):
        self.game_id = None
        self.grid = [["" for _ in range(5)] for _ in range(6)]
        self.colors = [[COLOR_EMPTY for _ in range(5)] for _ in range(6)]
        self.row = 0
        self.col = 0
        self.game_over = False
        self.hard_mode = False
        self.history = []  # 側邊欄歷史猜測：[(單字, [顏色, ...]), ...]
        self.stats = {"total_games": 0, "wins": 0, "win_rate": 0.0}
        self.message = "Press ENTER to submit, R to restart, H for Hard Mode"
        self.start_new_game()

    def update_stats(self, data):
        """ 從後端 Response 更新勝率統計 """
        if data and "stats" in data and data["stats"]:
            self.stats = data["stats"]

    def fetch_stats(self):
        """ 呼叫 /api/stats 取得最新統計（失敗時保留舊資料） """
        try:
            res = requests.get(f"{API_BASE_URL}/api/stats", timeout=10)
            if res.status_code == 200:
                self.stats = res.json()
        except requests.exceptions.RequestException:
            pass

    def start_new_game(self):
        """ 向 FastAPI 伺服器請求建立新的一局 """
        try:
            # Render 免費服務休眠後，第一次請求可能需要較久才會喚醒。
            res = requests.post(
                f"{API_BASE_URL}/api/new-game",
                json={"hard_mode": self.hard_mode},
                timeout=60,
            )
            if res.status_code == 200:
                data = res.json()
                self.game_id = data["game_id"]
                self.grid = [["" for _ in range(5)] for _ in range(6)]
                self.colors = [[COLOR_EMPTY for _ in range(5)] for _ in range(6)]
                self.row = 0
                self.col = 0
                self.game_over = False
                self.history = []
                self.update_stats(data)
                self.message = "New game started!"
            else:
                self.message = "Server error starting new game."
        except requests.exceptions.RequestException:
            self.message = "Cannot connect to FastAPI server!"

    def toggle_hard_mode(self):
        """ 任務四：切換硬核模式並重新開始一局 """
        self.hard_mode = not self.hard_mode
        self.start_new_game()
        mode = "HARD" if self.hard_mode else "Normal"
        if self.message == "New game started!":
            self.message = f"Mode: {mode}. New game started!"

    def submit_guess(self):
        """ 將當前行單字發送至 FastAPI 驗證 """
        if self.col < 5:
            self.message = "Not enough letters!"
            return

        guess_word = "".join(self.grid[self.row])
        try:
            payload = {"game_id": self.game_id, "guess": guess_word}
            res = requests.post(f"{API_BASE_URL}/api/guess", json=payload, timeout=60)

            if res.status_code == 200:
                data = res.json()
                feedback = data["feedback"]
                row_colors = []

                # 依據後端回傳更新格子顏色
                for i in range(5):
                    if feedback[i] == "correct":
                        color = COLOR_CORRECT
                    elif feedback[i] == "present":
                        color = COLOR_PRESENT
                    else:
                        color = COLOR_ABSENT
                    self.colors[self.row][i] = color
                    row_colors.append(color)

                # 任務三：加入側邊欄歷史紀錄
                self.history.append((guess_word, row_colors))
                self.update_stats(data)

                if data["is_correct"]:
                    self.message = "Congratulations! You won! Press R to restart."
                    self.game_over = True
                else:
                    self.row += 1
                    self.col = 0
                    # 任務一：第 6 次猜完，揭曉答案
                    if self.row == 6 or data.get("game_over"):
                        answer = data.get("target_word") or "?????"
                        self.message = f"Game Over! The word was {answer}. Press R to restart."
                        self.game_over = True
                    else:
                        left = data.get("attempts_left", 6 - self.row)
                        self.message = f"Keep guessing! ({left} tries left)"
            else:
                # 任務二：不合法時不增加 self.row，玩家可 Backspace 修改
                try:
                    detail = res.json().get("detail", "Error processing guess")
                except ValueError:
                    detail = "Error processing guess"
                if detail == "Word not in dictionary":
                    self.message = "Not in word list!"
                else:
                    self.message = detail
        except requests.exceptions.RequestException:
            self.message = "Network error during guess!"

    def handle_keydown(self, event):
        if event.key == pygame.K_r:
            self.start_new_game()
            return

        # 任務四：H 鍵切換硬核模式
        if event.key == pygame.K_h:
            self.toggle_hard_mode()
            return

        if self.game_over:
            return

        if event.key == pygame.K_BACKSPACE:
            if self.col > 0:
                self.col -= 1
                self.grid[self.row][self.col] = ""
        elif event.key == pygame.K_RETURN:
            self.submit_guess()
        elif event.unicode.isalpha() and len(event.unicode) == 1:
            if self.col < 5:
                self.grid[self.row][self.col] = event.unicode.upper()
                self.col += 1

    def draw_side_panel(self, surface):
        panel_x = GAME_WIDTH
        panel_w = WIDTH - GAME_WIDTH
        inner_x = panel_x + 12
        inner_w = panel_w - 24

        # 分隔線
        pygame.draw.line(surface, COLOR_PANEL_LINE, (panel_x, 0), (panel_x, HEIGHT), 2)

        # 右上角：目前模式
        mode_text = "Mode: HARD" if self.hard_mode else "Mode: Normal"
        mode_color = COLOR_HARD if self.hard_mode else COLOR_TEXT
        mode_surf = small_font.render(mode_text, True, mode_color)
        surface.blit(mode_surf, (WIDTH - mode_surf.get_width() - 12, 12))

        # 側邊欄上方：統計
        stats_text = (
            f"Total: {self.stats['total_games']} | "
            f"Wins: {self.stats['wins']} | "
            f"Win Rate: {self.stats['win_rate']:g}%"
        )
        stats_surf = fit_font_render(stats_text, inner_w, COLOR_TEXT)
        surface.blit(stats_surf, (inner_x, 45))

        # 歷史紀錄
        title_surf = small_font.render("History", True, COLOR_TEXT)
        surface.blit(title_surf, (inner_x, 90))

        mini = 28
        mini_gap = 4
        for idx, (word, colors) in enumerate(self.history):
            y = 125 + idx * (mini + 14)
            for c in range(5):
                x = inner_x + c * (mini + mini_gap)
                rect = pygame.Rect(x, y, mini, mini)
                pygame.draw.rect(surface, colors[c], rect, border_radius=3)
                ch = tiny_font.render(word[c], True, COLOR_TEXT)
                surface.blit(ch, ch.get_rect(center=rect.center))

    def draw(self, surface):
        surface.fill(COLOR_BG)
        # 繪製 6x5 網格
        margin_x, margin_y = 75, 50
        box_size = 60
        gap = 10

        for r in range(6):
            for c in range(5):
                x = margin_x + c * (box_size + gap)
                y = margin_y + r * (box_size + gap)
                rect = pygame.Rect(x, y, box_size, box_size)

                # 畫背景框
                pygame.draw.rect(surface, self.colors[r][c], rect, border_radius=4)
                if self.colors[r][c] == COLOR_EMPTY:
                    pygame.draw.rect(surface, (80, 80, 80), rect, width=2, border_radius=4)

                # 畫字母
                char = self.grid[r][c]
                if char:
                    text_surface = font.render(char, True, COLOR_TEXT)
                    text_rect = text_surface.get_rect(center=rect.center)
                    surface.blit(text_surface, text_rect)

        # 畫底部提示訊息（置中於左側遊戲區）
        msg_surface = small_font.render(self.message, True, COLOR_TEXT)
        msg_rect = msg_surface.get_rect(center=(GAME_WIDTH // 2, HEIGHT - 40))
        surface.blit(msg_surface, msg_rect)

        self.draw_side_panel(surface)


def main():
    clock = pygame.time.Clock()
    game = WordleGame()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                game.handle_keydown(event)

        game.draw(screen)
        pygame.display.flip()
        clock.tick(30)

if __name__ == "__main__":
    main()
