import os
import random
import uuid
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Wordle API Server")

# 目前 client 是桌面程式，不受瀏覽器 CORS 限制。若日後改成網頁，
# 再把 allow_origins 限定為實際前端網址。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
WORD_BANK = [
    "APPLE", "TRAIN", "HOUSE", "PLANT", "SMART", "WORLD", "LIGHT", "BRAIN", "CLOUD", "WATER",
    "ABOUT", "ABOVE", "ACTOR", "ACUTE", "ADMIT", "ADOPT", "ADULT", "AFTER", "AGAIN", "AGENT",
    "AGREE", "AHEAD", "ALARM", "ALBUM", "ALERT", "ALIEN", "ALIKE", "ALIVE", "ALLOW", "ALONE",
    "ALONG", "ALTER", "AMONG", "ANGER", "ANGLE", "ANGRY", "APART", "APPLY", "ARGUE", "ARISE",
    "ARRAY", "ARROW", "ASIDE", "ASSET", "AUDIO", "AUDIT", "AVOID", "AWAKE", "AWARE", "BADGE",
    "BAKER", "BASIC", "BASIS", "BEACH", "BEGIN", "BEING", "BELOW", "BENCH", "BLACK", "BLAME",
    "BLANK", "BLAST", "BLEED", "BLEND", "BLOCK", "BLOOD", "BOARD", "BOAST", "BONUS", "BOOST",
    "BOUND", "BREAD", "BREAK", "BRICK", "BRIEF", "BRING", "BROAD", "BROWN", "BRUSH", "BUILD",
    "BUNCH", "BUYER", "CABLE", "CANDY", "CARGO", "CARRY", "CATCH", "CAUSE", "CHAIN", "CHAIR",
    "CHALK", "CHARM", "CHART", "CHASE", "CHEAP", "CHECK", "CHEST", "CHIEF", "CHILD", "CHOSE",
    "CIVIL", "CLAIM", "CLASS", "CLEAN", "CLEAR", "CLIMB", "CLOCK", "CLOSE", "COACH", "COAST",
    "COUNT", "COURT", "COVER", "CRASH", "CREAM", "CRIME", "CROSS", "CROWD", "CROWN", "CURVE",
    "CYCLE", "DAILY", "DANCE", "DEATH", "DELAY", "DEPTH", "DRAFT", "DRAMA", "DREAM", "DRIVE",
    "EAGLE", "EARLY", "EARTH", "EIGHT", "EMPTY", "ENEMY", "ENJOY", "ENTER", "EQUAL", "ERROR",
    "EVENT", "EVERY", "EXACT", "EXIST", "FAITH", "FALSE", "FAULT", "FIELD", "FIGHT", "FINAL",
    "FIRST", "FLAME", "FLASH", "FLOAT", "FLOOR", "FLOUR", "FLUID", "FOCUS", "FORCE", "FORTH",
    "FORTY", "FORUM", "FRAME", "FRESH", "FRONT", "FRUIT", "GIANT", "GLASS", "GLOBE", "GRACE",
    "GRADE", "GRAND", "GRANT", "GRASS", "GREAT", "GREEN", "GROUP", "GUARD", "GUESS", "GUIDE",
    "HAPPY", "HEART", "HEAVY", "HOTEL", "HUMAN", "IMAGE", "INDEX", "INPUT", "ISSUE", "JUDGE",
    "KNIFE", "LAYER", "LEMON", "LEVEL", "LIMIT", "LUNCH", "MAGIC", "MAJOR", "MARCH", "MATCH",
    "MEDAL", "MONEY", "MONTH", "MUSIC", "NIGHT", "NOVEL", "NURSE", "OCEAN", "OFFER", "ORDER"
]
WORD_SET = set(WORD_BANK)
MAX_ATTEMPTS = 6

# 記憶體儲存遊戲狀態
games_db: Dict[str, dict] = {}

# 全域勝率統計（已結束的局數 / 獲勝局數）
stats = {"total_games": 0, "wins": 0}


class NewGameRequest(BaseModel):
    hard_mode: bool = False


class GuessRequest(BaseModel):
    game_id: str
    guess: str


def get_stats() -> dict:
    total = stats["total_games"]
    wins = stats["wins"]
    win_rate = round(wins / total * 100, 1) if total > 0 else 0.0
    return {"total_games": total, "wins": wins, "win_rate": win_rate}


@app.post("/api/new-game")
def start_new_game(req: Optional[NewGameRequest] = None):
    """ 建立新一局遊戲，回傳 game_id（可選 hard_mode，預設 False） """
    hard_mode = req.hard_mode if req else False
    game_id = str(uuid.uuid4())
    target_word = random.choice(WORD_BANK)
    games_db[game_id] = {
        "target": target_word,
        "status": "PLAYING",
        "attempts": 0,
        "hard_mode": hard_mode,
        "greens": {},  # 已揭露的綠色位置：{index: letter}
    }
    return {
        "game_id": game_id,
        "message": "New game started!",
        "hard_mode": hard_mode,
        "stats": get_stats(),
    }


@app.get("/api/stats")
def read_stats():
    """ 回傳總局數、獲勝局數、勝率 """
    return get_stats()


@app.post("/api/guess")
def process_guess(req: GuessRequest):
    """ 接收玩家猜測，比對答案並回傳顏色結果 """
    game_id = req.game_id
    guess = req.guess.upper()

    if game_id not in games_db:
        raise HTTPException(status_code=404, detail="Game session not found.")

    game = games_db[game_id]

    if game["status"] != "PLAYING":
        raise HTTPException(status_code=400, detail="Game is already over.")

    if len(guess) != 5:
        raise HTTPException(status_code=400, detail="Word must be 5 letters.")

    # 任務二：單字合法性檢查（不合法不扣次數）
    if guess not in WORD_SET:
        raise HTTPException(status_code=400, detail="Word not in dictionary")

    # 任務四：硬核模式，必須沿用已確認的綠色字母（不合法不扣次數）
    if game["hard_mode"]:
        for pos, letter in game["greens"].items():
            if guess[pos] != letter:
                raise HTTPException(
                    status_code=400,
                    detail="Hard Mode: Must use revealed hint at green position",
                )

    target = game["target"]
    feedback = ["absent"] * 5  # 預設灰色 absent
    target_letter_counts = {}

    # 1. 先計算目標單字的各字母數量
    for char in target:
        target_letter_counts[char] = target_letter_counts.get(char, 0) + 1

    # 2. 標記綠色 correct
    for i in range(5):
        if guess[i] == target[i]:
            feedback[i] = "correct"
            target_letter_counts[guess[i]] -= 1

    # 3. 標記黃色 present
    for i in range(5):
        if feedback[i] != "correct" and guess[i] in target:
            if target_letter_counts[guess[i]] > 0:
                feedback[i] = "present"
                target_letter_counts[guess[i]] -= 1

    # 記錄本次的綠色位置（供硬核模式使用）
    for i in range(5):
        if feedback[i] == "correct":
            game["greens"][i] = guess[i]

    game["attempts"] += 1
    attempts_left = MAX_ATTEMPTS - game["attempts"]

    # 檢查是否過關 / 結束
    is_correct = (guess == target)
    game_over = False
    if is_correct:
        game["status"] = "WON"
        stats["total_games"] += 1
        stats["wins"] += 1
        game_over = True
    elif attempts_left <= 0:
        game["status"] = "LOST"
        stats["total_games"] += 1
        game_over = True

    return {
        "guess": guess,
        "feedback": feedback,  # 例如: ["correct", "present", "absent", "absent", "correct"]
        "is_correct": is_correct,
        "attempts_left": attempts_left,
        "game_over": game_over,
        # 任務一：猜對或第 6 次用完時揭曉答案，否則為 None
        "target_word": target if game_over else None,
        "stats": get_stats(),
    }


if __name__ == "__main__":
    import uvicorn
    # Render 會透過 PORT 環境變數指定服務埠；本機則預設使用 8000。
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
