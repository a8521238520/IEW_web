#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
單篇文本抽取 emotion / symptom / thought / event（含 pattern）
------------------------------------------------------------
* 抽取 emotion / symptom / thought / event
* event 採「句子級」比對，不跨空白或標點
* 名詞事件型／中立主動型 → 需在前後 ±2 句有負面情緒或症狀才保留

使用方式：
    python extract_single_text.py "你的文章內容……"
    # 或者
    echo "你的文章內容……" | python extract_single_text.py
"""
import json, re, sys
from typing import Dict, List, Tuple

import hanlp
from pprint import pprint
# ---------------- 參數 ---------------- #
FIRST_PERSON = {"我", "我們", "咱們", "自己", "咱倆", "本人"}
OTHER_PERSON = {"他", "她", "他們", "她們", "它", "它們", "你", "妳", "你們", "妳們"}
RE_SPLIT_SENT = re.compile(r"[，。、！？?!?\s]+")

NEGATIONS = {
    "不", "沒", "沒有", "並不", "並沒有", "不是", "無",
    "別", "莫", "反對", "不要", "不能", "結束", "幫助",
    "有助於", "改善", "不用"
}
PADDING = {"再", "很", "想", "會"}

NEUTRAL_EVT_CATS = {"中立主動型", "名詞事件型"}

# ---------------- HanLP ---------------- #
tok_pos = hanlp.pipeline() \
    .append(hanlp.load(hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH)) \
    .append(hanlp.load(hanlp.pretrained.pos.CTB9_POS_ELECTRA_SMALL))
srl = hanlp.load(hanlp.pretrained.srl.CPB3_SRL_ELECTRA_SMALL)
sdp = hanlp.load(hanlp.pretrained.sdp.SEMEVAL16_ALL_ELECTRA_SMALL_ZH)

CMP_LABELS = {"CMP", "ccomp", "comp"}


# ---------------- 工具函式 ---------------- #

def has_neg_cmp(sent: str) -> bool:
    doc = sdp(sent)
    if hasattr(doc, "to_dict"):
        doc = doc.to_dict()
    if not isinstance(doc, dict):
        return False
    toks = doc.get("tok", [])
    deps = doc.get("deps", [])
    if not deps:
        for k in doc:
            if k.startswith("sdp/"):
                deps = doc[k]
                break
    for i, arcs in enumerate(deps):
        for _, rel in arcs:
            if rel in CMP_LABELS and i < len(toks) and toks[i] in NEGATIONS:
                return True
    return False


def load_event_mapping(fp: str) -> Dict[str, str]:
    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    return {p: cat for cat, lst in data.items() for p in lst}


def load_patterns(fp: str, key: str) -> List[str]:
    with open(fp, encoding="utf-8") as f:
        return json.load(f)[key]


def load_thought_mapping(fp: str) -> Dict[str, str]:
    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    return {p: cat for cat, lst in data.items() for p in lst}


def is_negated(sent: str, span: Tuple[int, int], pat: str | None = None) -> bool:
    if has_neg_cmp(sent):
        return True
    b, _ = span
    left_ctx = sent[max(0, b - 8): b]
    for neg in NEGATIONS:
        if neg in left_ctx:
            return True
        if len(left_ctx) >= 2 and left_ctx[-1] in PADDING and left_ctx[:-1].endswith(neg):
            return True
    if pat and "_" in pat:
        parts = pat.split("_")
        cur = b + len(parts[0])
        for part in parts[1:]:
            nxt = sent.find(part, cur)
            if nxt == -1:
                break
            if any(neg in sent[cur:nxt] for neg in NEGATIONS):
                return True
            cur = nxt + len(part)
    return False


def pat2re_event(p: str) -> re.Pattern:
    seg = r"[^，,。、\.！？?!\s]*?"
    return re.compile(seg.join(map(re.escape, p.split("_"))), re.I)


def pat2re(p: str) -> re.Pattern:
    return re.compile(".*?".join(map(re.escape, p.split("_"))), re.I)


def slice_from_pronoun(sent: str, span: Tuple[int, int]) -> str:
    b, e = span
    poss = [sent.find(p) for p in FIRST_PERSON if 0 <= sent.find(p) <= b]
    return sent[min(poss):e] if poss else sent[b:e]


def who(sent: str, frames) -> str:
    subj = "unknown"
    for fr in frames:
        args = fr.get("arguments", []) if isinstance(fr, dict) else fr[1:]
        for arg in args:
            if isinstance(arg, dict):
                role = arg.get("role", "")
                txt = arg.get("text", "")
            elif isinstance(arg, (list, tuple)) and len(arg) >= 3:
                role, b, e = arg[0], arg[1], arg[2]
                txt = sent[b:e] if isinstance(b, int) and isinstance(e, int) else ""
            else:
                continue
            if not str(role).startswith("A0"):
                continue
            if FIRST_PERSON & set(txt):
                return "self"
            if OTHER_PERSON & set(txt):
                subj = "other"
    if FIRST_PERSON & set(sent):
        return "self"
    if OTHER_PERSON & set(sent):
        return "other"
    return subj


# ---------------- 詞典載入 ---------------- #
emo_pats = load_patterns("emotion_old.json", "emotion")
sym_pats = load_patterns("symptom_old.json", "symptom")
thought_map = load_thought_mapping("thought_old.json")
event_map = load_event_mapping("event_pattern_structure.json")

regex_map = {p: pat2re(p) for p in emo_pats + sym_pats + list(thought_map)}
regex_map.update({p: pat2re_event(p) for p in event_map})

event_pats = list(event_map)
MAX_GAP = 3


# ---------------- 主邏輯 ---------------- #

def collect(sent: str) -> List[Dict]:
    res = []
    for pat, rex in regex_map.items():
        base_len = len(pat.replace("_", ""))
        for m in rex.finditer(sent):
            if len(m.group(0)) - base_len > MAX_GAP:
                continue
            res.append({"p": pat, "span": m.span()})
    return res


def _select_longest(hits: List[Dict]) -> Dict | None:
    if not hits:
        return None
    return max(hits, key=lambda h: (len(h["p"].replace("_", "")), h["span"][1] - h["span"][0]))


def extract_snippets(text: str) -> Dict[str, List[List[str]]]:
    emo_pairs, sym_pairs, tho_pairs, evt_pairs = [], [], [], []

    sents = [s for s in RE_SPLIT_SENT.split(text) if s]
    emo_flags, sym_flags = [], []
    for s in sents:
        try:
            frames = srl(s)
        except IndexError:
            frames = []
        if who(s, frames) == "other":
            emo_flags.append(False)
            sym_flags.append(False)
            continue
        hits = [h for h in collect(s) if not is_negated(s, h["span"], h["p"])]
        emo_flags.append(any(h["p"] in emo_pats for h in hits))
        sym_flags.append(any(h["p"] in sym_pats for h in hits))

    for idx, s in enumerate(sents):
        try:
            frames = srl(s)
        except IndexError:
            frames = []
        if who(s, frames) == "other":
            continue
        raw_hits = collect(s)
        hits = [h for h in raw_hits if not is_negated(s, h["span"], h["p"])]

        best_emo = _select_longest([h for h in hits if h["p"] in emo_pats])
        best_sym = _select_longest([h for h in hits if h["p"] in sym_pats])
        best_tho = _select_longest([h for h in hits if h["p"] in thought_map])

        for best, pairs in [(best_emo, emo_pairs), (best_sym, sym_pairs), (best_tho, tho_pairs)]:
            if best:
                pairs.append([slice_from_pronoun(s, best["span"]), best["p"]])

        ev_hits = [h for h in hits if h["p"] in event_pats]
        if ev_hits:
            win_has = any((emo_flags[j] or sym_flags[j]) for j in range(idx - 2, idx + 3) if 0 <= j < len(sents))
            ev_kept = [h for h in ev_hits if not (event_map[h["p"]] in NEUTRAL_EVT_CATS and not win_has)]
            best_evt = _select_longest(ev_kept)
            if best_evt:
                evt_pairs.append([
                    slice_from_pronoun(s, best_evt["span"]),
                    best_evt["p"],
                    event_map.get(best_evt["p"], "")  # 加入事件類型
                ])

    return {
        "extract_emotion": [tuple(p) for p in emo_pairs],
        "extract_symptom": [tuple(p) for p in sym_pairs],
        "extract_thought": [tuple(p) for p in tho_pairs],
        "extract_event": [tuple(p) for p in evt_pairs],
    }


# ---------------- DEMO / CLI ---------------- #

if __name__ == "__main__":
    txt = "醫生說出乳癌兩個字的時候，我真的嚇到說不出話，只覺得心往下陳，很害怕、很慌。一直想為什麼是我，那天回家路上眼淚一直掉，但又告訴自己要冷靜一點，至少先搞清楚下一步怎麼做。想到家人，心裡雖然難過，但也覺得他們因該會支持我。雖然還是很怕手術、很怕治療，但心裡覺得醫療那麼發達應該還有一點點希望，覺得我還有機會慢慢面對，子是現在真的還是很亂，很不安。"
    res = extract_snippets(txt)
    pprint(res)

