# utils/wordcloud_gen.py
from __future__ import annotations

from collections import Counter
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont
from wordcloud import WordCloud


def _pick_font_path() -> str:
    # Windows 常見中文字型
    win_candidates = [
        r"C:\Windows\Fonts\msjh.ttc",   # 微軟正黑體
        r"C:\Windows\Fonts\msjhl.ttc",
        r"C:\Windows\Fonts\kaiu.ttf",   # 標楷體
        r"C:\Windows\Fonts\mingliu.ttc" # 細明體
    ]

    # Linux 常見中文字型
    linux_candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]

    candidates = win_candidates + linux_candidates

    for p in candidates:
        if Path(p).exists():
            return p

    raise RuntimeError(
        "找不到中文字型。Windows 請指定 C:\\Windows\\Fonts\\msjh.ttc；"
        "Linux 請安裝 fonts-noto-cjk 或指定字型路徑。"
    )


def _extract_factors_safe(text: str) -> dict:
    """原有：提取 extract_snippets"""
    try:
        from factor_extract import extract_snippets
        return extract_snippets(text)
    except Exception as e:
        print(f"[WordCloud] factor_extract.extract_snippets unavailable: {e}")
        return {}


def _extract_cb_patterns_safe(text: str) -> dict:
    """✅ 新增：提取 cb_pattern_extractor (Neo4j patterns)"""
    try:
        # 優先嘗試從 automatic_extract 匯入
        from automatic_extract import cb_pattern_extractor
        return cb_pattern_extractor(text)
    except ImportError:
        # 若失敗，嘗試從 factor_extract 匯入
        try:
            from factor_extract import cb_pattern_extractor
            return cb_pattern_extractor(text)
        except Exception as e:
            print(f"[WordCloud] cb_pattern_extractor unavailable: {e}")
            return {}
    except Exception as e:
        print(f"[WordCloud] cb_pattern_extractor error: {e}")
        return {}


def _factors_counter(factor_res: dict) -> Counter:
    """統計 extract_snippets 的結果"""
    c = Counter()
    if not factor_res:
        return c

    # 針對特定 key 提取內容
    for k in ("extract_emotion", "extract_symptom", "extract_thought"):
        for it in factor_res.get(k, []) or []:
            if isinstance(it, (list, tuple)) and len(it) >= 1:
                snip = str(it[0]).strip()
                if snip:
                    c[snip] += 1

    for it in factor_res.get("extract_event", []) or []:
        if isinstance(it, (list, tuple)) and len(it) >= 1:
            snip = str(it[0]).strip()
            if snip:
                c[snip] += 1

    return c


def _cb_counter(cb_res: dict) -> Counter:
    """✅ 修改：統計 cb_pattern_extractor 的結果 (使用原始語句)"""
    c = Counter()
    if not cb_res:
        return c
    
    # cb_res 結構範例: {'B': [('不知道你過得好不好', '他人_不太友善')], ...}
    for cat_key, items in cb_res.items():
        if not items:
            continue
        for item in items:
            # item 預期是 (matched_sentence, pattern_name)
            # 修改：取 item[0] (matched_sentence) 作為文字雲顯示內容
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                original_sentence = str(item[0]).strip()
                if original_sentence:
                    c[original_sentence] += 1
    return c


def _make_soft_bg(width=1600, height=600) -> Image.Image:
    img = Image.new("RGBA", (width, height), (250, 250, 250, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    random.seed(7)

    blobs = [
        (173, 195, 214, 110),
        (170, 210, 190, 110),
        (210, 195, 180, 90),
    ]
    for _ in range(10):
        c = random.choice(blobs)
        w = random.randint(160, 340)
        h = random.randint(120, 260)
        x = random.randint(-80, width - 80)
        y = random.randint(-60, height - 60)
        draw.ellipse([x, y, x + w, y + h], fill=c)

    line_c = (140, 160, 170, 70)
    for y in (80, 150, 240):
        pts = []
        for x in range(0, width + 1, 160):
            pts.append((x, y + random.randint(-18, 18)))
        draw.line(pts, fill=line_c, width=3)

    return img


def _palette_color_func():
    palette = ["#8B6A5A", "#7FA88A", "#7E9BB7", "#6E8E78", "#9C7C6C"]
    def f(word, font_size, position, orientation, random_state=None, **kwargs):
        if font_size >= 90:
            return random.choice(["#8B6A5A", "#6E8E78"])
        if font_size >= 60:
            return random.choice(["#7FA88A", "#7E9BB7"])
        return random.choice(palette)
    return f


def _parse_color_to_rgba(c, alpha=210):
    if isinstance(c, tuple) and len(c) >= 3:
        return (int(c[0]), int(c[1]), int(c[2]), alpha)
    if isinstance(c, str):
        s = c.strip().lower()
        if s.startswith("#") and len(s) in (7, 9):
            r = int(s[1:3], 16)
            g = int(s[3:5], 16)
            b = int(s[5:7], 16)
            return (r, g, b, alpha)
        if s.startswith("rgb(") and s.endswith(")"):
            nums = s[4:-1].split(",")
            r, g, b = [int(x.strip()) for x in nums[:3]]
            return (r, g, b, alpha)
    return (90, 90, 90, alpha)


def _zh_times(n: int) -> str:
    zh = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    if n in zh:
        return f"{zh[n]}次"
    return f"{n}次"


def _build_top3_message(top3):
    # ✅ 如果前三名最高也只有 1 次，當作「沒有明顯重複」
    if not top3 or int(top3[0][1]) <= 1:
        return "系統目前沒有在這篇日記中找到明顯重複的詞語。"

    parts = [(w, int(c)) for w, c in top3]

    if len(parts) == 1:
        w1, c1 = parts[0]
        return (
            "系統從您剛剛的書寫內容中找出了最常出現的詞語，代表這些感受或想法在您的文章裡比較常被提到。"
            f"這次看到的詞語是：「{w1}」出現了{_zh_times(c1)}。"
            "這些詞語可以幫助您回頭看看，哪些情緒在您心裡比較明顯或反覆出現。"
        )

    if len(parts) >= 3:
        (w1, c1), (w2, c2), (w3, c3) = parts[:3]
        if c2 == c3:
            tail = f"而「{w2}」和「{w3}」各出現了{_zh_times(c2)}。"
        else:
            tail = f"而「{w2}」出現了{_zh_times(c2)}，「{w3}」出現了{_zh_times(c3)}。"
        return (
            "系統從您剛剛的書寫內容中找出了最常出現的三個詞語，代表這些感受或想法在您的文章裡比較常被提到。"
            f"這次看到的三個詞語是：「{w1}」出現了{_zh_times(c1)}，{tail}"
            "這些詞語可以幫助您回頭看看，哪些情緒在您心裡比較明顯或反覆出現。"
        )

    (w1, c1), (w2, c2) = parts[:2]
    return (
        "系統從您剛剛的書寫內容中找出了最常出現的兩個詞語，代表這些感受或想法在您的文章裡比較常被提到。"
        f"這次看到的兩個詞語是：「{w1}」出現了{_zh_times(c1)}，而「{w2}」出現了{_zh_times(c2)}。"
        "這些詞語可以幫助您回頭看看，哪些情緒在您心裡比較明顯或反覆出現。"
    )


# ====== 你可以在這裡調參數 ======
MAX_WORDS = 40                # 詞雲最多詞數
SHOW_COUNT_MIN = 3            # ✅ 小於這個次數就不在字下方畫 (N次)


class WordcloudService:
    """
    服務物件：
    現在整合了 extract_snippets 與 cb_pattern_extractor 的結果來生成詞雲。
    """
    def __init__(
        self,
        project_root: str | Path,
        static_dir: str | Path,
        font_path: str | None = None,
    ):
        self.project_root = Path(project_root)
        self.static_dir = Path(static_dir)

        self.wordcloud_dir = self.static_dir / "generated" / "wordcloud"
        self.wordcloud_dir.mkdir(parents=True, exist_ok=True)

        self.font_path = font_path or _pick_font_path()

    def generate_summary(self, day_index: str, content: str):
        """
        回傳：
          rel_path: 圖片相對 static 的路徑
          top3: [(word, count), ...]
          message: 上方要顯示的說明文字
          pos_items: [] (已移除詞典來源，故回傳空列表)
          neg_items: [] (已移除詞典來源，故回傳空列表)
        """
        
        # 1. 取得 NLP 提取結果 (Snippets)
        factor_res = _extract_factors_safe(content)
        fac_counts = _factors_counter(factor_res)

        # 2. 取得 CB Pattern 提取結果 (Neo4j)
        cb_res = _extract_cb_patterns_safe(content)
        cb_counts = _cb_counter(cb_res)

        # 3. 合併兩者的計數 (都使用原始語句/片段)
        merged_raw = fac_counts + cb_counts

        # 由於移除了正負面詞典，這裡直接設為空
        pos_items = []
        neg_items = []

        top3 = merged_raw.most_common(3)
        message = _build_top3_message(top3)

        # 4. 詞雲權重：使用合併後的計數
        merged_weighted = merged_raw

        # 如果完全沒有提取到任何詞，給一個預設值避免報錯
        if not merged_weighted:
            merged_weighted = {"(無)": 1}

        merged_weighted = Counter(dict(merged_weighted.most_common(MAX_WORDS)))

        bg = _make_soft_bg(1600, 600)

        wc = WordCloud(
            width=1600,
            height=600,
            background_color=None,
            mode="RGBA",
            font_path=self.font_path,
            prefer_horizontal=1.0,     # 幾乎全水平，方便畫次數
            collocations=False,
            max_words=MAX_WORDS,
            min_font_size=14,
            random_state=8,
            relative_scaling=0.6,
            margin=2,
        ).generate_from_frequencies(dict(merged_weighted))

        wc.recolor(color_func=_palette_color_func())
        wc_img = wc.to_image().convert("RGBA")

        # 5. 在每個詞下面畫 (N次)
        draw = ImageDraw.Draw(wc_img, "RGBA")

        for (word, _freq), font_size, position, orientation, color in wc.layout_:
            if orientation is not None and orientation != 0:
                continue

            count = int(merged_raw.get(word, 0))
            if count < SHOW_COUNT_MIN:      # ✅ 1次就不畫
                continue

            try:
                word_font = ImageFont.truetype(self.font_path, int(font_size))
            except Exception:
                continue

            x, y = position
            bbox = draw.textbbox((x, y), word, font=word_font)
            if not bbox:
                continue

            wx0, wy0, wx1, wy1 = bbox

            count_text = f"({_zh_times(count)})"
            count_size = max(12, int(font_size * 0.28))

            try:
                count_font = ImageFont.truetype(self.font_path, count_size)
            except Exception:
                continue

            cb = draw.textbbox((0, 0), count_text, font=count_font)
            cw = cb[2] - cb[0]
            ch = cb[3] - cb[1]

            cx = wx0 + ((wx1 - wx0) - cw) // 2
            cy = wy1 + 2

            if cy + ch > wc_img.size[1]:
                cy = max(0, wy0 - ch - 2)

            fill = _parse_color_to_rgba(color, alpha=200)
            draw.text((cx, cy), count_text, font=count_font, fill=fill)

        out = bg.copy()
        out.alpha_composite(wc_img)

        out_path = self.wordcloud_dir / f"day_{day_index}_summary.png"
        out.save(out_path)

        rel_path = f"generated/wordcloud/day_{day_index}_summary.png"
        
        return rel_path, top3, message, pos_items, neg_items