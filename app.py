from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from datetime import datetime
import base64
import requests
from paddleocr import PaddleOCR
from pathlib import Path
import threading
import traceback
import uuid
import time
import io
import os
import tempfile
import torch
import torchaudio
import json
import opencc
from utils.wordcloud_gen import WordcloudService

app = Flask(__name__)
app.secret_key = "change_me_to_random_secret"

# ===== Session 設定 (來自 app_1.py) =====
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # 防止 XSS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 允許跨頁面訪問

PROJECT_ROOT = Path(__file__).resolve().parent
wc_service = WordcloudService(project_root=PROJECT_ROOT, static_dir=app.static_folder)

# ===== 外部 ASR API 設定 =====
ASR_URL = "http://140.116.245.149:5002/proxy"
ASR_LANG = "TA and ZH Medical V1"
ASR_TOKEN = "2025@asr@tai"

# ===== VAD 模型載入 =====
print("正在載入 VAD 模型 (Silero)...")
model_vad, utils = torch.hub.load(
    repo_or_dir="snakers4/silero-vad",
    model="silero_vad",
    force_reload=False,
    onnx=False,
)
(get_speech_timestamps, _, read_audio, *_) = utils
print("VAD 模型載入完成。")

# ===== OCR 設定 =====
ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    lang="ch",
    device="cpu",
)
ocr_lock = threading.Lock()

# ===== 初始化簡轉繁轉換器 =====
cc = opencc.OpenCC("s2t")

# ===== 設定檔案儲存路徑 =====
UPLOAD_DIR = Path("uploads/ocr")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_SAVE_DIR = Path("uploads/audio")
AUDIO_SAVE_DIR.mkdir(parents=True, exist_ok=True)

# 設定日記儲存路徑
DIARY_DIR = Path("/home/kyl/minch/web/diary")
DIARY_DIR.mkdir(parents=True, exist_ok=True)

# ===== Session 管理 (ASR串流用) =====
sessions = {}
session_lock = threading.Lock()

SAMPLE_RATE = 16000
MAX_BUFFER_SECONDS = 15.0
SILENCE_GAP_SECONDS = 0.45
VAD_PADDING_SECONDS = 0.2
SILENCE_GAP = int(SILENCE_GAP_SECONDS * SAMPLE_RATE)
VAD_PADDING = int(VAD_PADDING_SECONDS * SAMPLE_RATE)
OVERLAP_SECONDS = 0.5
OVERLAP_SAMPLES = int(OVERLAP_SECONDS * SAMPLE_RATE)
LOCAL_MIN_WINDOW_SECONDS = 0.5
LOCAL_MIN_WINDOW = int(LOCAL_MIN_WINDOW_SECONDS * SAMPLE_RATE)


def load_entries_from_disk(user_id=None):
    """Load diary entries for a specific user (Modified from app_1.py)"""
    entries = {}
    if not user_id:
        return entries
    
    user_dir = DIARY_DIR / user_id
    if not user_dir.exists():
        return entries
    
    for file_path in user_dir.glob("day_*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                idx = data.get("day_index")
                if idx:
                    entries[str(idx)] = data
        except Exception as e:
            print(f"載入日記錯誤 {file_path}: {e}")
    return entries


def call_remote_asr(audio_tensor: torch.Tensor) -> str:
    temp_wav_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_wav_path = f.name

        torchaudio.save(
            temp_wav_path,
            audio_tensor.cpu(),
            SAMPLE_RATE,
        )

        with open(temp_wav_path, "rb") as f:
            audio_bytes = f.read()

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        data = {
            "lang": ASR_LANG,
            "token": ASR_TOKEN,
            "audio": audio_b64,
        }

        t0 = time.time()
        resp = requests.post(ASR_URL, data=data, timeout=30)
        t1 = time.time()
        print(f"[ASR] API 回應時間: {t1 - t0:.2f} 秒, HTTP status: {resp.status_code}")

        if resp.status_code == 200:
            res_json = resp.json()
            text = res_json.get("sentence", "")
            print(f"[ASR] 辨識結果: {text}")
            return text
        else:
            print(f"[ASR API Error] Status: {resp.status_code}, Msg: {resp.text}")
            return ""

    except Exception as e:
        print(f"[ASR Call Failed] {e}")
        traceback.print_exc()
        return ""
    finally:
        if temp_wav_path and os.path.exists(temp_wav_path):
            try:
                os.remove(temp_wav_path)
            except Exception:
                pass


# ===== 使用者管理路由 (來自 app_1.py) =====

@app.route("/set_user", methods=["POST"])
def set_user():
    """Set user_id in session"""
    data = request.get_json()
    user_id = data.get("user_id", "").strip()
    
    if not user_id:
        return jsonify({"ok": False, "error": "User ID cannot be empty"}), 400
    
    # Validate user_id (alphanumeric and underscore only)
    if not user_id.replace("_", "").isalnum():
        return jsonify({"ok": False, "error": "User ID can only contain letters, numbers, and underscores"}), 400
    
    session["user_id"] = user_id
    session.permanent = False  # 使用瀏覽器 session，關閉瀏覽器即登出
    session["last_activity"] = time.time()  # 記錄最後活動時間
    
    # Create user directory if it doesn't exist
    user_dir = DIARY_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[Session] User {user_id} logged in")
    return jsonify({"ok": True, "user_id": user_id})


@app.route("/get_current_user", methods=["GET"])
def get_current_user():
    """Check if user is logged in"""
    user_id = session.get("user_id")
    if user_id:
        return jsonify({"ok": True, "user_id": user_id})
    else:
        return jsonify({"ok": False})


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    """Update last activity time to keep session alive"""
    user_id = session.get("user_id")
    if user_id:
        session["last_activity"] = time.time()
        session.modified = True
        return jsonify({"ok": True, "user_id": user_id})
    else:
        return jsonify({"ok": False, "error": "No active session"}), 401


@app.before_request
def check_session_activity():
    """Check if session has expired due to inactivity"""
    # 跳過靜態檔案和登入相關的請求
    if request.endpoint in ['static', 'set_user', 'get_current_user']:
        return
    
    user_id = session.get("user_id")
    if user_id:
        last_activity = session.get("last_activity", 0)
        current_time = time.time()
        
        # 如果超過 10 分鐘沒有活動，清除 session
        INACTIVITY_TIMEOUT = 10 * 60  # 10 分鐘
        if current_time - last_activity > INACTIVITY_TIMEOUT:
            print(f"[Session] User {user_id} session expired due to inactivity")
            session.clear()


# ===== 主頁面路由 (整合了 app.py 的 Wordcloud 與 app_1.py 的 Session) =====

@app.route("/", methods=["GET", "POST"])
def index():
    # 1. 檢查登入狀態 (來自 app_1.py)
    user_id = session.get("user_id")
    if not user_id:
        # User not logged in, will show user input screen
        return render_template(
            "index.html",
            completed_days=[],
            diary_entries={},
            wc_img=None, wc_msg=None, pos_items=[], neg_items=[]
        )
    
    # 2. 載入該使用者的日記
    diary_entries = load_entries_from_disk(user_id)

    # 3. 準備 Wordcloud 顯示變數 (來自 app.py)
    view = request.args.get("view", "welcome")
    day = request.args.get("day", "")

    wc_img = None
    wc_msg = None
    if view == "wordcloud" and day and str(day) in diary_entries:
        wc_img = diary_entries[str(day)].get("wordcloud_summary")
        wc_msg = diary_entries[str(day)].get("wordcloud_message")

    pos_items = []
    neg_items = []
    if day and str(day) in diary_entries:
        pos_items = diary_entries[str(day)].get("pos_items", []) or []
        neg_items = diary_entries[str(day)].get("neg_items", []) or []

    # 4. 處理日記儲存 (POST)
    if request.method == "POST":
        content = request.form.get("diary_text", "").strip()
        day_index = request.form.get("day_index", "").strip()

        if not content or not day_index:
            flash("請先完成當天的日記內容")
            return redirect(url_for("index"))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_new = day_index not in diary_entries

        entry_data = {
            "day_index": day_index,
            "content": content,
            "updated_at": now,
            "user_id": user_id,
        }

        # 4-1. 執行文字雲分析 (來自 app.py)
        rel_path, top3, message, pos_items_gen, neg_items_gen = wc_service.generate_summary(day_index, content)
        entry_data["pos_items"] = pos_items_gen
        entry_data["neg_items"] = neg_items_gen
        entry_data["wordcloud_summary"] = rel_path
        entry_data["wordcloud_top3"] = top3
        entry_data["wordcloud_message"] = message

        diary_entries[day_index] = entry_data

        # 4-2. 儲存到使用者專屬資料夾 (來自 app_1.py)
        try:
            user_dir = DIARY_DIR / user_id
            user_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"day_{day_index}.json"
            save_path = user_dir / filename
            
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(entry_data, f, ensure_ascii=False, indent=4)
                
            print(f"[Save] User {user_id} 已儲存日記: {save_path}")
        except Exception as e:
            print(f"[Error] 儲存 JSON 失敗: {e}")
            flash("儲存失敗，請聯繫管理員")

        if is_new:
            flash(f"Day {day_index} 日記已完成 ✅")
        else:
            flash(f"Day {day_index} 日記已更新 ✏️")

        # 4-3. 儲存後導向文字雲頁面 (來自 app.py 的行為，但可保留 app_1 的 view='home' 邏輯，這裡選擇保留 app.py 的體驗)
        return redirect(url_for("index", view="wordcloud", day=day_index))

    completed_days = sorted(int(k) for k in diary_entries.keys())

    encouragement_msg = "您的勇敢超乎想像。" # 預設值
    if day and str(day) in diary_entries:
        # 您可以在這裡串接 LLM (如 Gemini API) 
        # 根據 diary_entries[str(day)]['content'] 生成專屬鼓勵
        pass

    return render_template(
        "index.html",
        completed_days=completed_days,
        diary_entries=diary_entries,
        wc_img=wc_img,
        wc_msg=wc_msg,
        pos_items=pos_items,
        neg_items=neg_items,
        encouragement_msg=encouragement_msg,
    )


@app.route("/stream_asr", methods=["POST"])
def stream_asr():
    session_id = request.form.get("session_id")
    is_final = request.form.get("is_final") == "true"
    file = request.files.get("audio")

    if not session_id:
        return jsonify({"ok": False, "error": "No session_id"}), 400

    to_transcribe = None
    response_text = ""
    seg_index = 0
    now = time.time()

    with session_lock:
        if session_id not in sessions:
            sessions[session_id] = {
                "buffer": torch.zeros((1, 0), dtype=torch.float32),
                "raw_bytes": bytearray(),
                "processed_samples": 0,
                "last_update": time.time(),
                "seg_index": 0,
                "last_asr_time": None,
                "created_at": time.time(),
            }
            print(f"\n[Session {session_id}] 新 session 建立")

        session_data = sessions[session_id]

        if file:
            try:
                chunk_bytes = file.read()
                session_data["raw_bytes"].extend(chunk_bytes)

                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_file:
                    temp_file.write(session_data["raw_bytes"])
                    temp_path = temp_file.name

                waveform, sr = torchaudio.load(temp_path)

                if sr != SAMPLE_RATE:
                    waveform = torchaudio.functional.resample(waveform, sr, SAMPLE_RATE)
                if waveform.shape[0] > 1:
                    waveform = torch.mean(waveform, dim=0, keepdim=True)

                total_samples = waveform.shape[1]
                processed = session_data["processed_samples"]

                if total_samples > processed:
                    new_tensor_part = waveform[:, processed:]
                    session_data["processed_samples"] = total_samples
                    session_data["buffer"] = torch.cat((session_data["buffer"], new_tensor_part), dim=1)
                    session_data["last_update"] = time.time()

            except Exception as e:
                print(f"[Session {session_id}] 解碼失敗: {e}")
            finally:
                if "temp_path" in locals() and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        buffer_len = session_data["buffer"].shape[1]
        buffer_seconds = buffer_len / SAMPLE_RATE
        cut_idx = None
        forced_cut = False

        if is_final:
            if buffer_len > 0:
                to_transcribe = session_data["buffer"]
            del sessions[session_id]
        else:
            if buffer_len > 0:
                wav_input = session_data["buffer"].squeeze()
                if wav_input.ndim == 0:
                    wav_input = wav_input.unsqueeze(0)

                timestamps = get_speech_timestamps(
                    wav_input, model_vad, sampling_rate=SAMPLE_RATE
                )

                for i in range(len(timestamps) - 1):
                    gap = timestamps[i + 1]["start"] - timestamps[i]["end"]
                    if gap >= SILENCE_GAP:
                        cut_idx = timestamps[i]["end"]
                        break

                if cut_idx is None and len(timestamps) > 0:
                    last_end = timestamps[-1]["end"]
                    if (buffer_len - last_end) >= SILENCE_GAP:
                        cut_idx = last_end

                if cut_idx is None and buffer_seconds >= MAX_BUFFER_SECONDS:
                    forced_cut = True
                    target = int(MAX_BUFFER_SECONDS * SAMPLE_RATE)
                    start = max(0, target - LOCAL_MIN_WINDOW)
                    end = min(buffer_len, target + LOCAL_MIN_WINDOW)
                    if end > start:
                        region = session_data["buffer"][:, start:end]
                        mono = region[0]
                        energy = mono.pow(2.0)
                        rel_idx = int(torch.argmin(energy).item())
                        cut_idx = start + rel_idx
                    else:
                        cut_idx = target

            if cut_idx is not None:
                if forced_cut:
                    safe_cut = min(cut_idx, buffer_len)
                    cut_for_first = max(0, safe_cut - OVERLAP_SAMPLES)
                    to_transcribe = session_data["buffer"][:, :cut_for_first]
                    remainder = session_data["buffer"][:, cut_for_first:]
                else:
                    safe_cut = min(cut_idx + VAD_PADDING, buffer_len)
                    to_transcribe = session_data["buffer"][:, :safe_cut]
                    remainder = session_data["buffer"][:, safe_cut:]
                session_data["buffer"] = remainder

        if to_transcribe is not None:
            seg_index = session_data.get("seg_index", 0) + 1
            session_data["seg_index"] = seg_index
            session_data["last_asr_time"] = now
        
        if len(session_data.get("raw_bytes", [])) > 10 * 1024 * 1024:
            session_data["raw_bytes"] = bytearray()
            session_data["processed_samples"] = 0

    if to_transcribe is not None:
        if to_transcribe.shape[1] > 8000:
            try:
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_filename = f"{session_id}_{seg_index}_{timestamp_str}.wav"
                save_path = AUDIO_SAVE_DIR / save_filename

                torchaudio.save(save_path, to_transcribe.cpu(), SAMPLE_RATE)
                print(f"[Session {session_id}] 已儲存音檔: {save_path}")
            except Exception as e:
                print(f"[Error] 儲存音檔失敗: {e}")

            print(f"[Session {session_id}] 第 {seg_index} 句，送出辨識...")
            text = call_remote_asr(to_transcribe)
            if text:
                text = cc.convert(text)
                text = text.replace("喫", "吃")
                response_text = text
                print(f"[Session {session_id}] 第 {seg_index} 句完成: {text}")

    return jsonify({"ok": True, "text": response_text})


@app.route("/ocr", methods=["POST"])
def ocr_endpoint():
    file = request.files.get("image")
    if not file or file.filename == "":
        return jsonify({"ok": False, "error": "沒有選擇任何圖片"}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]:
        suffix = ".jpg"

    filename = f"{uuid.uuid4().hex}{suffix}"
    save_path = UPLOAD_DIR / filename

    try:
        file.save(save_path)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": f"圖片儲存失敗: {e}"}), 500

    try:
        with ocr_lock:
            result_pages = ocr.predict(input=str(save_path))

        if not result_pages:
            return jsonify({"ok": False, "error": "OCR 辨識結果為空"}), 200

        lines = []
        for page in result_pages:
            if hasattr(page, "rec_texts"):
                lines.extend(page.rec_texts)
                continue
            if isinstance(page, dict) and "rec_texts" in page:
                lines.extend(page["rec_texts"])
                continue
            if isinstance(page, (list, tuple)):
                for line in page:
                    if isinstance(line, dict) and "text" in line:
                        lines.append(line["text"])
                        continue
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        candidate = line[1]
                        if isinstance(candidate, str):
                            lines.append(candidate)
                        elif isinstance(candidate, (list, tuple)) and candidate:
                            if isinstance(candidate[0], str):
                                lines.append(candidate[0])

        lines = [t.strip() for t in lines if isinstance(t, str) and t.strip()]
        text = "\n".join(lines)

        if text:
            text = cc.convert(text)
            text = text.replace("喫", "吃")

        return jsonify({"ok": True, "text": text})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": f"OCR 執行錯誤: {e}"}), 500

    finally:
        try:
            save_path.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=5267,
        ssl_context=("cert.pem", "key.pem"),
        use_reloader=True,
    )