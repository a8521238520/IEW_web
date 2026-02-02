document.addEventListener("DOMContentLoaded", () => {
  // ======================
  // Helpers
  // ======================
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // ======================
  // Screen Controller
  // ======================
  const screens = {
    userInput: $("#screen-user-input"),
    welcome: $("#screen-welcome"),
    home: $("#screen-home"),
    mode: $("#screen-mode"),
    write: $("#screen-write"),
    review: $("#screen-review"),
    wordcloud: $("#screen-wordcloud"),
    sentiment: $("#screen-sentiment"),
    feedback: $("#screen-feedback"),
    encouragement: $("#screen-encouragement"),
  };

  const appContent = $("#app-content");
  const appMain = document.querySelector(".app");

  const show = (name) => {
    if (appMain) appMain.classList.remove("loading");

    Object.values(screens).forEach((s) => s && s.classList.remove("is-active"));
    if (screens[name]) screens[name].classList.add("is-active");

    if (appContent) {
      appContent.style.display =
        name === "welcome" || name === "userInput" ? "none" : "block";
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // ======================
  // User Authentication & Session
  // ======================
  let currentUserId = null;

  const btnSubmitUser = $("#btn-submit-user");
  const userIdInput = $("#user-id-input");
  const userIdError = $("#user-id-error");

  if (btnSubmitUser && userIdInput) {
    const submitUserId = async () => {
      const userId = userIdInput.value.trim();

      if (!userId) {
        userIdError.textContent = "請輸入使用者 ID";
        userIdError.style.display = "block";
        return;
      }

      if (!/^[a-zA-Z0-9_]+$/.test(userId)) {
        userIdError.textContent = "ID 只能包含英文、數字和底線";
        userIdError.style.display = "block";
        return;
      }

      try {
        const response = await fetch("/set_user", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId }),
        });
        const data = await response.json();

        if (data.ok) {
          currentUserId = data.user_id;
          userIdError.style.display = "none";
          window.location.reload();
        } else {
          userIdError.textContent = data.error || "登入失敗，請重試";
          userIdError.style.display = "block";
        }
      } catch (error) {
        console.error("Failed to set user:", error);
        userIdError.textContent = "連線失敗，請重試";
        userIdError.style.display = "block";
      }
    };

    btnSubmitUser.addEventListener("click", submitUserId);
    userIdInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") submitUserId();
    });
  }

  // ======================
  // Heartbeat
  // ======================
  let heartbeatTimer = null;
  const startHeartbeat = () => {
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    const HEARTBEAT_INTERVAL = 5 * 60 * 1000;

    heartbeatTimer = setInterval(async () => {
      try {
        const response = await fetch("/heartbeat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        const data = await response.json();
        if (!data.ok) clearInterval(heartbeatTimer);
      } catch (error) {
        console.error("[Heartbeat] Error:", error);
      }
    }, HEARTBEAT_INTERVAL);
  };

  // ======================
  // Global refs (先宣告，避免 form 未定義)
  // ======================
  const form = $("#diary-form");
  const textareaWrap = $(".textarea-wrap");
  const textarea = $("#diary_text");

  // ======================
  // Loading Overlay (Submit)
  // ======================
  const loadingOverlay = $("#loading-overlay");
  const submitBtn = $("#btn-submit");

  const showLoading = () => {
    if (!loadingOverlay) return;
    loadingOverlay.style.display = "flex";
    document.body.classList.add("no-scroll");
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "分析中…";
    }
  };

  const hideLoading = () => {
    if (!loadingOverlay) return;
    loadingOverlay.style.display = "none";
    document.body.classList.remove("no-scroll");
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "我已檢查完成，送出 →";
    }
  };

  if (form) {
    form.addEventListener("submit", (e) => {
      if (form.dataset.submitting === "1") {
        e.preventDefault();
        return;
      }
      form.dataset.submitting = "1";
      showLoading();
    });
  }

  window.addEventListener("pageshow", () => {
    if (form) form.dataset.submitting = "0";
    hideLoading();
  });

  // ======================
  // Initialization & Session Check
  // ======================
  const checkUserSession = async () => {
    try {
      const response = await fetch("/get_current_user");
      const data = await response.json();

      if (data.ok && data.user_id) {
        currentUserId = data.user_id;
        startHeartbeat();

        const startView = window.START_VIEW || "welcome";
        show(startView);
      } else {
        show("userInput");
      }
    } catch (error) {
      console.error("Failed to check user session:", error);
      show("userInput");
    }
  };

  checkUserSession();

  // ======================
  // General UI Logic
  // ======================
  const btnEnter = $("#btn-enter");
  if (btnEnter) btnEnter.addEventListener("click", () => show("home"));

  // Modal (instruction)
  const instructionModal = $("#instruction-modal");
  const btnEnterDiary = $("#btn-enter-diary");

  let selectedDay = 1;
  let pendingDaySelection = 1;
  let selectedMode = "voice";

  const dayIndexInput = $("#day_index");
  const modeInput = $("#mode");

  const uiDayMode = $("#ui-day-number");
  const uiDayWrite = $("#ui-day-number-write");
  const uiDayReview = $("#ui-day-number-review");

  const instructionText = $("#ui-instruction-text");
  const voiceControls = $("#voice-controls");
  const ocrControls = $("#ocr-controls");
  const typingControls = $("#typing-controls");

  const reviewMount = $("#review-mount");
  const reviewSplit = $("#review-split");
  const reviewOcrImage = $("#review-ocr-image");
  const reviewOcrEmpty = $("#review-ocr-empty");

  const ocrStorageKey = (day) => `ocrPreviewDay:${day}`;
  const loadOcrPreviewForDay = (day) => {
    try {
      return sessionStorage.getItem(ocrStorageKey(day));
    } catch {
      return null;
    }
  };
  const saveOcrPreviewForDay = (day, dataUrl) => {
    try {
      sessionStorage.setItem(ocrStorageKey(day), dataUrl);
    } catch (e) {
      console.warn("sessionStorage save failed:", e);
    }
  };

  const updateReviewLayout = () => {
    if (!reviewSplit) return;

    const isOcr = selectedMode === "ocr";

    if (!window.__ocrPreviewUrl && selectedDay) {
      const cached = loadOcrPreviewForDay(selectedDay);
      if (cached) window.__ocrPreviewUrl = cached;
    }

    const hasImg = !!window.__ocrPreviewUrl;

    if (isOcr) reviewSplit.classList.remove("is-single");
    else reviewSplit.classList.add("is-single");

    if (!reviewOcrImage) return;

    if (isOcr && hasImg) {
      reviewOcrImage.src = window.__ocrPreviewUrl;
      reviewOcrImage.style.display = "block";
      if (reviewOcrEmpty) reviewOcrEmpty.style.display = "none";
    } else {
      reviewOcrImage.removeAttribute("src");
      reviewOcrImage.style.display = "none";
      if (reviewOcrEmpty) reviewOcrEmpty.style.display = "block";
    }
  };

  // ---------- Day selection ----------
  const bindDayClick = (btn) => {
    btn.addEventListener("click", () => {
      pendingDaySelection = parseInt(btn.dataset.day, 10) || 1;
      if (instructionModal) instructionModal.classList.add("is-open");
      else proceedToModeSelection(pendingDaySelection);
    });
  };

  $$(".day-circle").forEach(bindDayClick);
  $$(".day-dot").forEach(bindDayClick);

  if (btnEnterDiary) {
    btnEnterDiary.addEventListener("click", () => {
      if (instructionModal) instructionModal.classList.remove("is-open");
      proceedToModeSelection(pendingDaySelection);
    });
  }

  function proceedToModeSelection(day) {
    selectedDay = day;

    if (dayIndexInput) dayIndexInput.value = String(selectedDay);
    if (uiDayMode) uiDayMode.textContent = String(selectedDay);
    if (uiDayWrite) uiDayWrite.textContent = String(selectedDay);
    if (uiDayReview) uiDayReview.textContent = String(selectedDay);

    if (textarea) {
      textarea.value = "";
      if (window.DIARY_DATA && window.DIARY_DATA[String(selectedDay)]) {
        textarea.value = window.DIARY_DATA[String(selectedDay)].content;
      }
      textarea.dispatchEvent(new Event("input"));
    }

    if (window.__resetWriteTimer) window.__resetWriteTimer();
    if (window.__resetReviewTimer) window.__resetReviewTimer();

    if (window.__ocrPreviewUrl && String(window.__ocrPreviewUrl).startsWith("blob:")) {
      try {
        URL.revokeObjectURL(window.__ocrPreviewUrl);
      } catch {}
    }
    window.__ocrPreviewUrl = null;

    const cached = loadOcrPreviewForDay(selectedDay);
    if (cached) window.__ocrPreviewUrl = cached;

    updateReviewLayout();
    show("mode");
  }

  // ---------- Mode selection ----------
  $$(".mode-tile").forEach((tile) => {
    tile.addEventListener("click", () => {
      selectedMode = tile.dataset.mode;
      if (modeInput) modeInput.value = selectedMode;

      applyModeUI(selectedMode);
      show("write");

      if (selectedMode === "ocr") {
        setTimeout(() => {
          const ocrInput = $("#ocr-input");
          if (ocrInput) ocrInput.click();
        }, 250);
      }

      updateReviewLayout();
    });
  });

  function applyModeUI(mode) {
    if (voiceControls) voiceControls.style.display = "none";
    if (ocrControls) ocrControls.style.display = "none";
    if (typingControls) typingControls.style.display = "none";

    if (mode === "voice") {
      if (voiceControls) voiceControls.style.display = "flex";
      if (instructionText) {
        instructionText.innerHTML =
          "您將有15分鐘的時間進行心情日記的錄音書寫，系統會在您開始錄音時進行倒數計時。當時間剩下最後 30 秒時，系統會貼心提醒您可以將錄音進行收尾。";
      }
    } else if (mode === "ocr") {
      if (ocrControls) ocrControls.style.display = "flex";
      if (instructionText) {
        instructionText.innerHTML =
          "請點擊左側相機圖示上傳您的手寫日記照片。系統會自動辨識文字並填入下方，您可以在下方文字框進行校對與修改。";
      }
    } else {
      if (typingControls) typingControls.style.display = "flex";
      if (instructionText) {
        instructionText.innerHTML =
          "請直接在下方的文字框中輸入您的日記內容。完成後請點選右下角的「書寫完成」進入下一步。";
      }
    }
  }

  // ---------- Nav buttons ----------
  $$("[data-nav]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.nav;

      const params = new URLSearchParams(window.location.search);
      const dayFromUrl = params.get("day");
      const day = dayFromUrl || String(selectedDay || 1);

      if (action === "back-home") return show("home");
      if (action === "back-mode") return show("mode");

      if (action === "back-write") {
        if (form && textareaWrap && textareaWrap.parentElement !== form) {
          form.insertBefore(textareaWrap, form.querySelector(".nav-row"));
        }
        return show("write");
      }

      if (action === "next-sentiment") return show("sentiment");
      if (action === "back-wordcloud") return show("wordcloud");

      // ✅ 文字雲 -> 問卷頁（改用跳頁）
      if (action === "next-feedback") {
        window.location.href = `/?view=feedback&day=${encodeURIComponent(day)}`;
        return;
      }

      // ✅ 問卷頁 -> 文字雲頁（改用跳頁）
      if (action === "back-wordcloud") {
        window.location.href = `/?view=wordcloud&day=${encodeURIComponent(day)}`;
        return;
      }

      if (action === "finish-feedback") {
        // 檢查問卷是否填寫 (可選)
          const q1 = document.querySelector('input[name="q1_score"]:checked');
          if (!q1) {
            alert("請先完成問卷評分再送出，謝謝。");
            return;
          }
          
          // 執行跳轉
          show("encouragement"); 
          return;
      }
    });
  });

  // ---------- Next -> Review ----------
  const btnNextReview = $("#btn-next-review");
  if (btnNextReview) {
    btnNextReview.addEventListener("click", () => {
      if (reviewMount && textareaWrap) reviewMount.appendChild(textareaWrap);

      if (window.__stopWriteTimer) window.__stopWriteTimer();
      if (window.__resetReviewTimer) window.__resetReviewTimer();
      if (window.__startReviewTimer) window.__startReviewTimer();

      updateReviewLayout();
      show("review");
    });
  }

  // ---------- textarea auto resize ----------
  if (textarea) {
    const autoResize = () => {
      textarea.style.height = "auto";
      textarea.style.height = textarea.scrollHeight + "px";
    };
    textarea.addEventListener("input", autoResize);
    setTimeout(autoResize, 100);
  }

  // ======================
  // Timer (Write 15min / Review 5min)
  // ======================
  const timerDisplay = $("#timer-display");
  const timerToggleBtn = $("#timer-toggle");
  const hourglass = $("#hourglass");

  const timerDisplayReview = $("#timer-display-review");
  const timerToggleReview = $("#timer-toggle-review");
  const hourglassReview = $("#hourglass-review");

  const WRITE_TOTAL = 15 * 60;
  const REVIEW_TOTAL = 5 * 60;

  let writeRemaining = WRITE_TOTAL;
  let reviewRemaining = REVIEW_TOTAL;

  let writeTimerId = null;
  let reviewTimerId = null;
  let writeAutoStarted = false;

  const formatTime = (sec) => {
    const m = Math.floor(sec / 60).toString().padStart(2, "0");
    const s = (sec % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const setProgress = (hgEl, remaining, total) => {
    if (!hgEl) return;
    const elapsed = total - remaining;
    const fraction = Math.min(1, Math.max(0, elapsed / total));
    hgEl.style.setProperty("--hg-progress", fraction.toFixed(4));
  };

  const renderWrite = () => {
    if (!timerDisplay) return;
    timerDisplay.textContent = formatTime(writeRemaining);
    setProgress(hourglass, writeRemaining, WRITE_TOTAL);
  };

  const renderReview = () => {
    if (!timerDisplayReview) return;
    timerDisplayReview.textContent = formatTime(reviewRemaining);
    setProgress(hourglassReview, reviewRemaining, REVIEW_TOTAL);
  };

  const stopWriteTimer = () => {
    if (writeTimerId) {
      clearInterval(writeTimerId);
      writeTimerId = null;
    }
    if (hourglass) hourglass.classList.remove("running");
    if (timerToggleBtn) timerToggleBtn.textContent = "繼續計時";
  };

  const stopReviewTimer = () => {
    if (reviewTimerId) {
      clearInterval(reviewTimerId);
      reviewTimerId = null;
    }
    if (hourglassReview) hourglassReview.classList.remove("running");
    if (timerToggleReview) timerToggleReview.textContent = "繼續計時";
  };

  const startWriteTimer = () => {
    if (!timerDisplay || !timerToggleBtn || !hourglass) return;
    if (writeTimerId) return;

    if (writeRemaining <= 0) writeRemaining = WRITE_TOTAL;

    timerToggleBtn.style.display = "inline-block";
    timerToggleBtn.textContent = "暫停計時";
    hourglass.classList.add("running");

    writeTimerId = setInterval(() => {
      writeRemaining -= 1;
      if (writeRemaining <= 0) {
        writeRemaining = 0;
        clearInterval(writeTimerId);
        writeTimerId = null;
        timerToggleBtn.textContent = "重新計時";
        hourglass.classList.remove("running");
      }
      renderWrite();
    }, 1000);
  };

  const startReviewTimer = () => {
    if (!timerDisplayReview || !timerToggleReview || !hourglassReview) return;
    if (reviewTimerId) return;

    if (reviewRemaining <= 0) reviewRemaining = REVIEW_TOTAL;

    timerToggleReview.textContent = "暫停計時";
    hourglassReview.classList.add("running");

    reviewTimerId = setInterval(() => {
      reviewRemaining -= 1;
      if (reviewRemaining <= 0) {
        reviewRemaining = 0;
        clearInterval(reviewTimerId);
        reviewTimerId = null;
        timerToggleReview.textContent = "重新計時";
        hourglassReview.classList.remove("running");
      }
      renderReview();
    }, 1000);
  };

  window.__startReviewTimer = startReviewTimer;

  const toggleWrite = () => {
    if (!timerToggleBtn) return;
    if (!writeTimerId && writeRemaining === 0) {
      writeRemaining = WRITE_TOTAL;
      renderWrite();
      startWriteTimer();
      return;
    }
    if (writeTimerId) stopWriteTimer();
    else {
      timerToggleBtn.textContent = "暫停計時";
      if (hourglass) hourglass.classList.add("running");
      startWriteTimer();
    }
  };

  const toggleReview = () => {
    if (!timerToggleReview) return;
    if (!reviewTimerId && reviewRemaining === 0) {
      reviewRemaining = REVIEW_TOTAL;
      renderReview();
      startReviewTimer();
      return;
    }
    if (reviewTimerId) stopReviewTimer();
    else {
      timerToggleReview.textContent = "暫停計時";
      if (hourglassReview) hourglassReview.classList.add("running");
      startReviewTimer();
    }
  };

  if (timerToggleBtn) timerToggleBtn.addEventListener("click", toggleWrite);
  if (timerToggleReview) timerToggleReview.addEventListener("click", toggleReview);

  const resetWriteTimer = () => {
    stopWriteTimer();
    writeRemaining = WRITE_TOTAL;
    writeAutoStarted = false;
    if (timerToggleBtn) timerToggleBtn.style.display = "none";
    if (timerToggleBtn) timerToggleBtn.textContent = "暫停計時";
    renderWrite();
  };

  const resetReviewTimer = () => {
    stopReviewTimer();
    reviewRemaining = REVIEW_TOTAL;
    if (timerToggleReview) timerToggleReview.textContent = "開始計時";
    renderReview();
  };

  window.__resetWriteTimer = resetWriteTimer;
  window.__resetReviewTimer = resetReviewTimer;
  window.__stopWriteTimer = stopWriteTimer;

  if (textarea) {
    textarea.addEventListener("input", () => {
      if (
        !writeAutoStarted &&
        !writeTimerId &&
        writeRemaining === WRITE_TOTAL &&
        textarea.value.trim().length > 0
      ) {
        startWriteTimer();
        writeAutoStarted = true;
      }
    });
  }

  renderWrite();
  renderReview();

  // ======================
  // Voice ASR
  // ======================
  const micBtn = $("#mic-btn");
  const micStatus = $("#mic-status");
  let mediaRecorder = null;
  let recording = false;
  let sessionId = null;
  let uploadPromises = [];

  const TAIL_MAX_CHARS = 20;
  const MIN_OVERLAP_CHARS = 2;
  let lastTailForOverlap = "";

  const generateUUID = () => {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  };

  const setMicStatus = (text) => {
    if (micStatus) micStatus.textContent = text || "";
  };
  const stopStreamTracks = (stream) => stream.getTracks().forEach((t) => t.stop());

  const mergeWithPunctuationAndOverlap = (currentVal, segment) => {
    if (!segment || segment.length === 0) return currentVal;
    if (!currentVal || currentVal.length === 0) return segment;

    const tail = lastTailForOverlap || currentVal.slice(-TAIL_MAX_CHARS);
    let trimmed = segment;
    let overlapped = false;

    const maxK = Math.min(tail.length, trimmed.length, TAIL_MAX_CHARS);
    for (let k = maxK; k >= MIN_OVERLAP_CHARS; k--) {
      const tailPart = tail.slice(-k);
      const headPart = trimmed.slice(0, k);
      if (tailPart === headPart) {
        trimmed = trimmed.slice(k);
        overlapped = true;
        break;
      }
    }

    if (trimmed.length === 0) return currentVal;
    const lastChar = currentVal.slice(-1);

    if (overlapped) return currentVal + trimmed;
    if (lastChar !== "\n" && lastChar !== "。" && lastChar !== "，") {
      return currentVal + "，" + trimmed;
    } else {
      return currentVal + trimmed;
    }
  };

  const uploadChunk = async (blob, isFinal = false) => {
    const formData = new FormData();
    formData.append("audio", blob, "chunk.webm");
    formData.append("session_id", sessionId);
    formData.append("is_final", isFinal);

    try {
      const res = await fetch("/stream_asr", { method: "POST", body: formData });
      const data = await res.json();

      if (data.ok && typeof data.text === "string" && textarea) {
        let currentVal = textarea.value;
        const rawText = data.text.trim();
        if (!rawText) return;

        const lower = rawText.toLowerCase();

        if (lower.includes("silent")) {
          if (currentVal.length > 0) {
            const lastChar = currentVal.slice(-1);
            if (lastChar === "，") currentVal = currentVal.slice(0, -1) + "。";
            else if (lastChar !== "。") currentVal = currentVal + "。";
            textarea.value = currentVal;
            lastTailForOverlap = currentVal.slice(-TAIL_MAX_CHARS);
            textarea.dispatchEvent(new Event("input"));
          }
          return;
        }

        currentVal = mergeWithPunctuationAndOverlap(currentVal, rawText);
        textarea.value = currentVal;
        lastTailForOverlap = currentVal.slice(-TAIL_MAX_CHARS);
        textarea.dispatchEvent(new Event("input"));
      }
    } catch (err) {
      console.error("Chunk upload failed:", err);
    }
  };

  if (micBtn) {
    micBtn.addEventListener("click", async () => {
      if (!recording) {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          setMicStatus("此瀏覽器不支援麥克風錄音功能。");
          return;
        }

        try {
          const constraints = {
            audio: {
              channelCount: 1,
              echoCancellation: false,
              noiseSuppression: false,
              autoGainControl: false,
            },
          };

          const stream = await navigator.mediaDevices.getUserMedia(constraints);
          sessionId = generateUUID();
          uploadPromises = [];
          lastTailForOverlap = "";

          let options = { mimeType: "audio/webm;codecs=opus", audioBitsPerSecond: 192000 };
          if (!MediaRecorder.isTypeSupported(options.mimeType)) options = { mimeType: "audio/webm" };

          mediaRecorder = new MediaRecorder(stream, options);

          mediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) {
              const p = uploadChunk(e.data, false);
              uploadPromises.push(p);
            }
          };

          mediaRecorder.onstop = async () => {
            stopStreamTracks(stream);
            setMicStatus("正在處理最後片段...");
            await Promise.all(uploadPromises);
            await uploadChunk(new Blob([], { type: "audio/webm" }), true);
            setMicStatus("錄音結束。");
            uploadPromises = [];
          };

          mediaRecorder.start(1000);
          recording = true;
          micBtn.classList.remove("mic-idle");
          micBtn.classList.add("mic-recording");
        } catch (err) {
          console.error(err);
          setMicStatus("無法使用麥克風，請確認權限。");
        }
      } else {
        recording = false;
        micBtn.classList.remove("mic-recording");
        micBtn.classList.add("mic-idle");
        if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
      }
    });
  }

  // ======================
  // OCR Upload
  // ======================
  const ocrInput = $("#ocr-input");
  const ocrBtn = $("#ocr-btn");
  const ocrStatus = $("#ocr-status");

  const setOcrStatus = (text) => {
    if (ocrStatus) ocrStatus.textContent = text || "";
  };

  if (ocrBtn && ocrInput) {
    ocrBtn.addEventListener("click", () => ocrInput.click());
  }

  if (ocrInput) {
    ocrInput.addEventListener("change", () => {
      const file = ocrInput.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result;
        window.__ocrPreviewUrl = dataUrl;
        saveOcrPreviewForDay(selectedDay, dataUrl);
        updateReviewLayout();
      };
      reader.readAsDataURL(file);

      const formData = new FormData();
      formData.append("image", file);
      setOcrStatus("正在上傳圖片並進行文字辨識…");

      fetch("/ocr", { method: "POST", body: formData })
        .then((res) => res.json())
        .then((data) => {
          if (data.ok) {
            setOcrStatus("辨識完成！已填入文字框，可再修正。");
            if (textarea) {
              const currentVal = textarea.value;
              const separator = currentVal.length > 0 ? "\n" : "";
              textarea.value = currentVal + separator + data.text;
              textarea.dispatchEvent(new Event("input"));
            }
          } else {
            setOcrStatus("辨識失敗：" + (data.error || "未知錯誤"));
          }
        })
        .catch((err) => {
          console.error(err);
          setOcrStatus("連線失敗，請稍後再試。");
        })
        .finally(() => {
          ocrInput.value = "";
        });
    });
  }

  // ======================
  // ✅ 新增功能：問卷第 2 題點「否」 -> 跳出填寫視窗要求補寫
  // ======================
  const getDayFromUrl = () => {
    const params = new URLSearchParams(window.location.search);
    return params.get("day") || String(selectedDay || 1);
  };

  const q2StorageKey = (day) => `q2_detail:${day}`;

  const ensureQ2Modal = () => {
    let modal = $("#q2-modal-overlay");
    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = "q2-modal-overlay";
    modal.className = "modal-overlay";
    modal.innerHTML = `
      <div class="modal-card fade-in-up" style="max-width: 620px;">
        <div class="modal-decor-bg"></div>
        <div class="modal-content">
          <div class="instruction-group" style="margin-bottom:14px;">
            <div class="instruction-text" style="width:100%;">
              <p style="margin:0; font-weight:900; color:#7a5c3a;">
                你剛剛選擇「否」，我們想請你再補充一下
              </p>
              <p style="margin:10px 0 0;">
                請寫下今天最在意、最牽掛的事情（例如：一直放在心裡的想法、讓你放心不下的事）。
              </p>
            </div>
          </div>

          <div style="margin-top: 12px;">
            <textarea id="q2-modal-text"
              rows="6"
              style="width:100%; border-radius:14px; border:1px solid #cbd5e1; padding:14px; font-size:1rem; line-height:1.7; outline:none;"
              placeholder="請在這裡寫下你最在意/最牽掛的事…"></textarea>
            <div style="margin-top:10px; color:#a05345; font-weight:700; display:none;" id="q2-modal-error">
              請先填寫內容再送出
            </div>
          </div>

          <div class="nav-row" style="justify-content:flex-end; margin-top:16px;">
            <button type="button" class="btn ghost" id="q2-modal-cancel">取消</button>
            <button type="button" class="btn primary" id="q2-modal-save">送出</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    return modal;
  };

  const openQ2Modal = () => {
    const modal = ensureQ2Modal();
    const day = getDayFromUrl();
    const ta = $("#q2-modal-text");
    const err = $("#q2-modal-error");

    // 預填已存資料
    const cached = sessionStorage.getItem(q2StorageKey(day)) || "";
    if (ta) ta.value = cached;
    if (err) err.style.display = "none";

    modal.classList.add("is-open");

    // 綁定按鈕
    const btnCancel = $("#q2-modal-cancel");
    const btnSave = $("#q2-modal-save");

    const close = () => modal.classList.remove("is-open");

    if (btnCancel) {
      btnCancel.onclick = () => close();
    }

    if (btnSave) {
      btnSave.onclick = () => {
        const text = (ta?.value || "").trim();
        if (!text) {
          if (err) err.style.display = "block";
          return;
        }

        // 存起來（依 day 分開）
        sessionStorage.setItem(q2StorageKey(day), text);

        // ✅ 自動把 Q2 改成 yes（代表已補寫）
        const q2Yes = document.querySelector('input[name="q2_yesno"][value="yes"]');
        if (q2Yes) q2Yes.checked = true;

        close();
        alert("已完成補寫，謝謝你。");
      };
    }
  };

  // 只在 feedback 畫面才會有這題
  const q2No = document.querySelector('input[name="q2_yesno"][value="no"]');
  if (q2No) {
    q2No.addEventListener("change", () => {
      if (q2No.checked) {
        openQ2Modal();
      }
    });
  }

  // ======================
  // Initial form values (optional)
  // ======================
  if (dayIndexInput && !dayIndexInput.value) dayIndexInput.value = "";
  if (modeInput && !modeInput.value) modeInput.value = "";
});
