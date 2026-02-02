from collections import Counter
from neo4j import GraphDatabase
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import pprint
from utils.cb_filter import *

# 設定 Neo4j 連線資訊
NEO4J_URI = "bolt://140.116.245.146:57687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "jimmy666666"
import pandas as pd


def split_into_sentences(text):
    """
    自訂中文斷句規則：
    - 以中文句號、驚嘆號、問號為基礎斷句
    - 額外對逗號、空白進行語意斷句（不破壞詞）
    - 空格後若為中文開頭，則斷
    """
    # 先依主要標點（句號、問號、驚嘆號、換行）分句
    # print("split_into_sentences:", text)
    assert isinstance(text, str), f"Expected String but got {type(text)}"
    chunks = re.split(r'([>。！？!?，”“\n]+)|(\s*\d\.\s*)|(\s*\d\)\s*)', text)
    chunks = [chunk for chunk in chunks if chunk]
    results = []
    # print("chunks:", chunks)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        # 進一步將 chunk 中的中文空白處斷句（前後都是中文/標點）
        sub_chunks = re.split(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', chunk)
        for part in sub_chunks:
            if part.strip():
                results.append(part.strip())

    return results


class KnowledgeGraphMatcher:
    def __init__(self, uri, user, password, database, pattern_cache=None, synonym_cache=None):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        self.pattern_cache = pattern_cache
        self.synonym_cache = {}

    def close(self):
        self.driver.close()

    def get_all_patterns(self):
        if self.pattern_cache:
            return self.pattern_cache
        """從 Neo4j 讀取所有 Pattern 與 count、type 值"""
        with self.driver.session(database=self.database) as session:
            result = session.run("MATCH (p:Pattern) RETURN p.type AS type, p.name AS pattern, p.count AS count")
            patterns = [{"type": r["type"], "text": r["pattern"], "count": r["count"]} for r in result]
            self.pattern_cache = patterns
            return patterns

    def get_synonyms(self, word):
        if word in self.synonym_cache:
            return self.synonym_cache[word]
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (w:Word)-[:SYNONYM_OF*1..2]->(s:Word)
                WHERE w.name = $word AND w <> s
                RETURN DISTINCT s.name AS synonym
            """, word=word)
            synonyms = [r["synonym"] for r in result]
            self.synonym_cache[word] = synonyms
            return synonyms

    def generate_regex_from_pattern(self, pattern):
        """根據 Pattern 生成正則表達式"""
        words = pattern.split("_")
        regex_parts = []

        for word in words:
            synonyms = self.get_synonyms(word)
            synonyms.append(word)  # 包含自己
            synonyms = list(set(synonyms))
            regex_parts.append(f"(?:{'|'.join(map(re.escape, synonyms))})")
        # print(regex_parts)
        return ".*?".join(regex_parts)

    def match_text_against_patterns(self, input_text, window_size=1):
        """將輸入文本分句後，滑動兩句一起比對 pattern"""
        sentences = split_into_sentences(input_text)
        sentences = [s for s in sentences if s not in {'，', '。'}]
        """檢查輸入文字是否符合 Neo4j 中的任何 Pattern"""
        patterns = self.get_all_patterns()
        matched_results = []
        window_size2_pattern = {'他人_我_失去', "失去_他人_我_走不出來", "我_沒有勇氣_離開", "沒有_他人_怎麼_存活",
                                "天生麗質_才能_受到_矚目", "努力_卻_嘲諷", "期許_做_活躍人",
                                "什麼都想做到_什麼都想做好", "打破誓言_無法完成_計劃", "不能_成為_焦點_讓我心碎",
                                "不顧_他人_自己_為主", "你會失去妳的工作_因為我", "一直_躲房間_沒在承擔_責任",
                                "遇到_好吃_無法忍耐_事後_催吐", "不想吃藥_就_假裝忘", "沒有好好吃藥_都亂吃",
                                "提不起勁_做事情_不想_起床", "要_上課_但_我_沒動力", "知道_該做什麼_就是_逃避",
                                "什麼事都不想做_只想_沉淪", "知道_有很多事_要做_但_不想去做", "人際關係_不懂",
                                "吃_怕胖_吐出來", "信賴_被_撕碎", "外在_窒息", "逃到_沒有人_的地方",
                                "老子_放棄_只要_開_藥_就可以", "不喜歡_但可以接受", "有_事情想做_但是_想_休息","被傷害_還_擔心他_會不會_受傷"
                                "拜託_他人_跟我聊天", "他人_陪伴_我_壓力_大", "怎麼_才_不麻煩_他人","不想_造成_負擔_假裝_沒有_異常","信任_他人_拿我_當擋箭牌", "要告訴自己_很棒_可是_我_無法","自我價值_崩塌", "知道_熬夜_會_掉進黑洞_我還是做", "身而為人_很抱歉"}
        i = 0
        while i < len(sentences):
            matched = False
            for pattern_data in patterns:
                pattern = pattern_data["text"]

                # 若此 pattern 為指定 pattern，則使用 window_size = 2
                current_window_size = 2 if pattern in window_size2_pattern else window_size

                if i + current_window_size > len(sentences):
                    continue  # 避免超出範圍

                combined = "。".join(sentences[i:i + current_window_size])
                regex_pattern = self.generate_regex_from_pattern(pattern)

                if re.search(regex_pattern, combined, re.IGNORECASE):
                    matched_results.append([pattern_data, combined])
                    matched = True
                    i += current_window_size  # 若有 match，跳過整個 window_size
                    break  # 一旦有匹配，停止檢查此視窗中的其他 pattern

            if not matched:
                i += 1  # 沒 match 就照舊滑動一格

        return matched_results


def cb_match_threaded(test_cases, database):
    """單一資料庫的比對任務（用於執行緒）"""
    kg_matcher = KnowledgeGraphMatcher(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, database)
    matched_patterns = kg_matcher.match_text_against_patterns(test_cases)
    kg_matcher.close()
    return matched_patterns


pattern_cache_dict = {}
synonym_cache_dict = {}


def init_db_cache(db):
    # print(f"🔍 初始化 {db} 中...")
    kg = KnowledgeGraphMatcher(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, db)
    pattern_cache = kg.get_all_patterns()
    synonym_cache = {}
    for pat in pattern_cache:
        for word in pat["text"].split("_"):
            if word not in synonym_cache:
                synonym_cache[word] = kg.get_synonyms(word)
    kg.close()
    pattern_cache_dict[db] = pattern_cache
    synonym_cache_dict[db] = synonym_cache
    # print(f"✅ {db} 完成")


def get_cached_matcher(db):
    return KnowledgeGraphMatcher(
        NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, db,
        pattern_cache=pattern_cache_dict[db],
        synonym_cache=synonym_cache_dict[db]
    )


def single_db_match(database, text: str):
    matcher = get_cached_matcher(database)
    matches = matcher.match_text_against_patterns(text)
    # print(matches)
    matcher.close()
    if matches:
        print(f"✅ {database} 匹配到 {len(matches)} 筆 ")
    return matches


def event_matches(text: str):
    # print("正在初始化 pattern 與同義詞快取...")
    databases = ["cba", "cbb", "cbc", "cbd", "cbe", "cbf", "cbg", "cbh", "cbi", "cbj", "cbk", "cbl", "cbm"]

    # print("🔄 正在初始化所有資料庫的 pattern/synonym 快取...")
    with ThreadPoolExecutor(max_workers=len(databases)) as executor:
        futures = [executor.submit(init_db_cache, db) for db in databases]
        for future in futures:
            future.result()
    # print("✅ 所有資料庫快取初始化完成！")
    # 預先抓取 pattern 與 synonym（只需從一個資料庫中取得）
    all_results = []

    # 使用 ThreadPoolExecutor 執行多執行緒任務
    type_to_sentences = defaultdict(list)

    with ThreadPoolExecutor(max_workers=len(databases)) as executor:
        futures = {executor.submit(single_db_match, db, text): db for db in databases}
        for future in futures:
            matches = future.result()
            if matches:
                for pattern_info, matched_sentence in matches:
                    type_to_sentences[pattern_info["type"]].append((matched_sentence, pattern_info["text"]))

    result = {}

    for label in sorted(type_to_sentences.keys()):
        # print(f"{label}: {type_to_sentences[label]}")
        result[label] = list(set(type_to_sentences[label]))  # 去重
    for label in [chr(c) for c in range(ord('A'), ord('N'))]:
        if label not in result:
            result[label] = []
    all_results.append(result)
    pprint.pprint(all_results)
    return all_results


def collect_all_patterns(database):
    # databases = ["cba", "cbb", "cbc", "cbd", "cbe", "cbf", "cbg", "cbh", "cbi", "cbj", "cbk", "cbl", "cbm"]
    all_patterns = set()

    kg = KnowledgeGraphMatcher(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, database)
    patterns = kg.get_all_patterns()
    kg.close()

    for pat in patterns:
        all_patterns.add(pat["text"])  # 只取 pattern 文字
        # 轉成 dict 並初始化為 0
    pattern_dict = {p: 0 for p in all_patterns}
    return pattern_dict

def cb_extraction(input_text: str):
    # 指定 A~M 類別
    cb_types = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']
    events = event_matches(input_text)
    # 取出第一篇文章的 A~M list
    cb_lists = {key: events[0][key] for key in cb_types}
    print("cb_lists:", cb_lists)
    return cb_lists

def cb_pattern_extractor(input_text: str):
    cb_extract = cb_extraction(input_text)
    cb_extract = filter_event_A_dict(cb_extract)
    cb_extract = filter_event_B_dict(cb_extract)
    cb_extract = filter_event_C_dict(cb_extract)
    cb_extract = filter_event_D_dict(cb_extract)
    cb_extract = filter_event_E_dict(cb_extract)
    cb_extract = filter_event_F_dict(cb_extract)
    cb_extract = filter_event_G_dict(cb_extract, input_text)
    cb_extract = filter_event_H_dict(cb_extract)
    cb_extract = filter_event_I_dict(cb_extract)
    cb_extract = filter_event_J_dict(cb_extract)
    cb_extract = filter_event_K_dict(cb_extract)
    cb_extract = filter_event_L_dict(cb_extract)
    cb_extract = filter_event_M_dict(cb_extract)
    return cb_extract

if __name__ == "__main__":
    # pprint.pprint(collect_all_patterns())
    res = cb_pattern_extractor(
        "社畏 歷程 國小甚至幼稚園開始，因為小聰明，總是被導師選為班長之類的討人厭的角色，我討厭與眾不同我不是主流的那種社交咖，我長得很醜女生嫉妒成績好、男生不把我當女生看，我討厭上台管秩序，因為像我這種成績優異的廖扒仔好像不懂民間疾苦一樣，老師什麼都聽我的，同學把我的話當耳邊風，霸凌從此開始，抗拒上台，到領完市長獎畢業。 某師：希望你可以以K女為目標 小六：為什麼？(我連國中都還沒選好) 某師：因為你成績很好，這樣才可以考上好大學 小六：好大學要幹嘛 某師：這樣你才能找到好工作轉大錢 小六：就這樣？？？ 彼時我沒有任何夢想，別人想要當醫生、畫家、拯救世界、買房子給爸媽、環遊世界、結婚、做研究太多了 家庭背景使我沒有任何夢想以及敢做夢的能力，母親一心一意要全部小孩去考他那養活一家子的國營事業，只想著那就考上K女吧，然後考P大，一輩子不愁吃住工作。 一方面也只是為了滿足母親未完成的學歷的替代品罷了，也許念了K工，人生就會不同了 ，不重要 一方面覺得在二三志願無法抉擇時，考第一志願就沒這麼煩惱了。 人生就是這樣，我就是台灣教育體制下的敗類，面對新工作前輩比自己小多年，能力又強實在慚愧壓力大。 大學能選考試課就不選報告課，在系上同學眼裡也是十足怪咖，直到研究所，推了一所只看書審的系，再也沒有繼續躲在學校的理由，我害怕口試別忘了，想到論文寫完要口試我還沒下手論文時就先退學了，這輩子一直在用激烈逃避的方式和我的社畏為伍。 上班開始，因為內業需要接電話，我仍然很抗拒，沒人在的話我會讓它響到停，為此被罵很多次，阿就不是找我阿，你要找阿人又不在或不接，電話、簡報、面試，大概是社畏對我造成最大困擾。 多年前北醫主任有問我要不要參加心理治療工作坊，因為懶抗拒回絕了，突然想要面對一下 新工作一週，每天胃糾結、胸口灼熱、手汗直流，給自己一個月，只是室友說太短了要兩個月。 前輩每天7AM上班11PM下班，準時下班的我內心真的過不去 雖然我他媽的沒有想多留一刻 ，下班，再見。 建立生活，從吃藥、運動、衣櫃換季、拖地、洗床單、曬棉被、翻書出來看開始，明明下班時間很多，卻常常滑手機到半夜，好好生活好難，連心臟不要亂跳、手腳停止流汗開始。 希望有人可以迴響，玻璃心求拍拍 吃了兩顆安眠藥還清醒，慘。")
    print(res)

