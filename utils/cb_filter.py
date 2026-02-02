import hanlp
import re

# 1. 初始化
# ----------------------------------------------------
mtl = hanlp.load(
    hanlp.pretrained.mtl.OPEN_TOK_POS_NER_SRL_DEP_SDP_CON_ELECTRA_BASE_ZH
)
FIRST_PERSON = {'我', '自己', '我們'}
COMP_RELS = {'ccomp', 'xcomp', 'advcl', 'acl'}  # 從句補語
NEG_WORDS = {
    '不', '沒', '没有', '無', '未', '別', '别',
    '不是', '不要', '不能', '不想', '不再', '毋', '莫'
}

RE_SPLIT_SENT = re.compile(r"[，。！？?!?\s]+")


def split_into_sentences(text):
    """
    自訂中文斷句規則：
    - 以中文句號、驚嘆號、問號為基礎斷句
    - 額外對逗號、空白進行語意斷句（不破壞詞）
    - 空格後若為中文開頭，則斷
    """
    # 先依主要標點（句號、問號、驚嘆號、換行）分句
    chunks = re.split(r'[。！？!?，”\n]+', text)
    results = []

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


# [(sent, label), ...]
del_list = []


def _get_dep_arcs(sent: str):
    """
    HanLP MTL 依版本不同，dep 可能回傳：
      · list[hanlp.components.parsers.stanford.StanfordParserArc]
      · list[Tuple[int, str]]  (head_id, relation)
    統一包成 (relation:str) 迭代器，方便後續判斷。
    """
    arcs = mtl(sent)['dep']
    for arc in arcs:
        if isinstance(arc, tuple):  # (head, rel)
            yield arc[1]
        else:  # Arc 物件
            yield (
                    getattr(arc, 'relation', None) or
                    getattr(arc, 'rel', None) or
                    getattr(arc, 'type', None)
            )


def has_clausal_complement(sent: str) -> bool:
    return any(rel in COMP_RELS for rel in _get_dep_arcs(sent))


def has_negation(sent: str) -> bool:
    parsed = mtl(sent)

    # ① token level
    tokens = parsed.get('tok/fine') or parsed.get('tok') or []
    if any(tok in NEG_WORDS for tok in tokens):
        return True

    # ② dep level
    if any(rel and rel.lower().startswith('neg') for rel in _get_dep_arcs(sent)):
        return True

    return False


def filter_event_A_dict(ev):
    print("ev:", ev)
    """傳入 event dict，回傳過濾後的 dict"""
    if not isinstance(ev, dict) or 'A' not in ev:
        return ev
    new_A = []
    for sent, label in ev['A']:
        if sent in {'因為我的原生家庭的姊姊已經有三個姊姊都過世了', '你走了一年了', "然後遺忘我吧", "你們卻都走了",
                    "我無意中發現他不在這個行業了", '她並不在意',
                    '沒有價值就會被丟一旁', '她走了說不定連她父母都偷偷鬆了一口氣', '或許她只是不想傷害你所以才會離開',
                    '你要找阿人又不在或不接'}:
            continue
        if sent in {"不知道找誰說。那個能聽我說的人、我失去了"}:
            new_A.append((sent, label))
            continue
        if label == '被_拋棄':
            new_A.append((sent, label))
            continue
        try:
            doc = mtl(sent, tasks=['srl'])
            frame = doc['srl'][-1] if doc['srl'] else []
        except Exception:
            new_A.append((sent, label))
            continue

        delete_flag = False
        for tok, role_lbl, *_ in frame:
            if role_lbl == 'ARG0' and tok in FIRST_PERSON:
                delete_flag = True
                break
            if role_lbl == 'ARG1' and tok not in FIRST_PERSON:
                delete_flag = True
                break

        if delete_flag:
            doc_tok = mtl(sent, tasks=['tok'])
            if label == '他人_死亡':
                print("sent:", sent)
                toks = set(doc_tok['tok'])
                if toks & {'在乎', '想', '想要'}:
                    del_list.append((sent, label))
                else:
                    new_A.append((sent, label))
            else:
                del_list.append((sent, label))
        else:
            new_A.append((sent, label))

    ev['A'] = new_A
    return ev


def filter_event_B_dict(ev):
    if not isinstance(ev, dict) or 'B' not in ev:
        return ev
    attack = {"貶低", "冷眼相待", "甩耳光", "責備", "欺凌", "傷害", "不善待", "笑話", "糟蹋", "取笑", "罵",
              "追殺", "強制", "扼殺", "欺壓", "攻擊", "助紂為虐", "擊潰", "欺負", "訕笑"}
    new_B = []
    for sent, label in ev['B']:
        if sent in {'攻擊那些曾經傷害我的別人', '如果說人渣傷害了她', '那她傷害了她身邊所有愛她的人',
                    '常常說一些真心話卻沒人相信', '最氣人的是我居然心軟讓自己被情勒', '還被情勒要跟他們聚在一起吃飯',
                    '或許她只是不想傷害你所以才會離開', '她一直想死的原因就是因為不想傷害別人',
                    '但沒有妳的日子對我來說每天都是種折磨', '就像剛在一起時妳哭著說想分手想離開不想傷害我一樣',
                    '但別懷疑我對妳的愛', '我一直在想我的存在是不是對妳來說就是一種傷害',
                    '大家都說L不能原諒那個誘姦她的人渣',
                    '感覺從來沒有想到這些事情對我的身體帶來這麼大的傷害就是給我的一個檢討讓我能夠更去看清一些事情很多的事情都沒有那麼嚴重',
                    '不知道你過得好不好',
                    '有想在護理打拼一輩子'}:
            del_list.append((sent, label))
            continue
        if label != '折磨_我':  # 先過濾，不用做 NLP
            new_B.append((sent, label))
            continue
        print(f' - {sent}   ({label})')
        # ---------- HanLP 一次出所有任務 ----------
        try:
            doc = mtl(sent, tasks=['tok', 'pos', 'srl'])
            tokens = doc['tok']  # list[str]
            tags = doc['pos']  # list[str]
            frames = doc['srl']
            frame = frames[-1] if frames else []
        except Exception:
            new_B.append((sent, label))
            continue

        # ---------- 刪除邏輯 ----------
        delete_flag = False

        # 1) ARG0 為第一人稱
        for word, role_lbl, *_ in frame:
            if role_lbl == 'ARG0' and word in FIRST_PERSON:
                delete_flag = True
                break

        # 2) 出現「自己」且「傷害」是動詞
        if not delete_flag and "自己" in tokens:
            for w, tag in zip(tokens, tags):
                if w in attack and tag == 'VV':
                    delete_flag = True
                    break

        # ---------- 收集結果 ----------
        if delete_flag:
            del_list.append((sent, label))
        else:
            new_B.append((sent, label))

    ev['B'] = new_B
    return ev


def filter_event_C_dict(ev):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'C' not in ev:
        return ev
    new_C = []
    for sent, label in ev['C']:
        if sent in {'想心理諮商能幫得了我', "後來長大就沒有這種很喜歡某件衣服的感覺", '沒辦法陪到她',
                    "突然遇到沒遇過的情形自己不會處理", '從沒有夢想的人懂不了這種感覺', "希望學生懂得萌這個",
                    "未來我想試著喜歡自己的名字", "我從來沒有喜歡過我自己的名字",
                    "但我又要跟誰道歉啊我其實也沒對不起任何人我只是不在乎這個活著的機會而已", '沒大愛也不打緊',
                    "事後只會越想越怪心理恐懼", "開始有點後悔白天沒有去拜拜尋求一點心理慰藉", "七星藍莓也沒特別喜歡",
                    "別人想要當醫生、畫家、拯救世界、買房子給爸媽、環遊世界、結婚、做研究太多了", "但我累沒力氣理他",
                    "但沒辦法陪你們長大了", '一片混亂沒人整理',
                    "影響他的身體。婆家也不會喜歡媳婦每天往娘家跑的(我看過身邊很多例子了) 我如果要生養小孩就沒辦法工作這樣他們經濟壓力會很大",
                    '他有時候不一定會理我', '所以我始終壓抑自己這些他人不喜歡的行為', '想用最有效率的方式處理',
                    "別人沒有心理能量揹負你的負能量", "剛剛被同學在群組問整理好了沒", '媽媽最終還是沒能接受…',
                    '沒想到顏社老闆連這個新時代的東西也懂', '想要的東西不給他ㄧ個屎臉從沒在意家人的犧牲',
                    '我覺得她只是單純自己不喜歡我', '能想得到的理由是鋰鹽太難吃了',
                    "時不時還得被老友或家人關心工作找的如何", '只是不想接受自己是憂鬱症患者', '會忽略要多關心自己一點',
                    "我覺得我時候自己沒有很關心他們","想當初一開始做化療的時候就有一種被拯救的感覺就每天都在倒數什麼時候化療會結束就覺得命就好了",
                    '但我想整理東西', '再也沒有繼續躲在學校的理由', "也沒有太大的心理因素",
                    '有時候朋友叫我過去我也不太喜歡打擾人家', "所以會覺得這樣子好像這段時間比較沒辦法做到陪伴啊",
                    '不知道你現在做的工作是不是自己喜歡的事情'}:
            del_list.append((sent, label))
            continue
        if label == "沒有人_陪伴":
            if "沒有道理" in sent:
                del_list.append((sent, label))
                continue
            else:
                new_C.append((sent, label))
        elif label == '他人_不_理解':
            delete_flag = False
            for t in sent:
                if t == "理":
                    print(f' - {sent}   ({label})')
                    try:
                        tok = mtl(sent, tasks=['tok'])
                        pos = mtl(sent, tasks=['pos'])
                    except Exception:
                        new_C.append((sent, label))
                        break

                    try:
                        doc = mtl(sent, tasks=['srl'])
                        last_srl_round = len(doc['srl'])
                        frame = doc['srl'][last_srl_round - 1 if last_srl_round > 0 else last_srl_round]
                    except Exception:
                        new_C.append((sent, label))
                        break
                    if "理" not in tok['tok'] and "理解" not in tok['tok']:
                        delete_flag = True
                    else:
                        tokens = tok['tok']
                        tags = pos['pos']
                        if "理解" not in tok['tok']:
                            for i, tag in enumerate(tags):
                                if tokens[i] == '理' and tag != 'VV':
                                    delete_flag = True
                                    break
                    break

            if delete_flag:
                del_list.append((sent, label))
            else:
                new_C.append((sent, label))
        else:
            new_C.append((sent, label))
    ev['C'] = new_C
    return ev


def filter_event_D_dict(ev):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'D' not in ev:
        return ev
    new_D = []
    for sent, label in ev['D']:
        if sent in {"我怕哪天我不在家的時候他就永遠離開我了", '不亞於和父母保持聯絡', '我還是趕快離開世界好了',
                    "我已經脫離了那個世界了", "果然是離開熟悉地方的原因吧", '還是要直接跟大哥說你不要再問我去問老師',
                    '不是我會選擇她而離開妳', '困在小房間的孩子實在太可憐', '我竟想成他要一個人逃走',
                    '離開熟悉的環境什麼的', '今天離開了三年多的老地方了', "不要一直想這個問題",
                    "我獨處的時候就是去公園走路", "所以說我很少獨處", "但是他們其實是拒絕對話的",
                    "然後今天剛好就是有醫師在問我要不要來做這樣的問卷",
                    "也是很長一段時間沒有跟原生家庭的家人住在一起這樣子", "讓我覺得在這一條路上我並不孤單",
                    "一個人要樂觀的去面對", "我平常獨處的時候我就看看一些詩啊、心情不好就聽音樂啊、看看電視啊", "我平常都是獨處的時間比較多",
                    "所以不知道你有沒有讓自己定期放空、遠離工作",
                    "那因為我沒有家族史"}:
            continue
        else:
            new_D.append((sent, label))
    ev['D'] = new_D
    return ev


def filter_event_E_dict(ev):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'E' not in ev:
        return ev
    new_E = []
    for sent, label in ev['E']:
        if sent in {"只是因為他覺得我的精神病況已經嚴重到需要關心我了", "而且我不想依賴別人的回饋",
                    "她身邊充滿了樂意達成她願望的人渴慕她的人依賴她的人對她充滿幻想的人", '但焦慮到底是什麼鬼東西….',
                    '希望有人可以迴響', '別人想要當醫生、畫家、拯救世界、買房子給爸媽、環遊世界、結婚、做研究太多了',
                    "也是我最期望的、希望可以趕快達到的",
                    "然後可是另外一方面我覺得說感謝神讓我發現之前沒有很好好的照顧自己的身體",
                    "然後我又要讓他們擔心我就有一段時間是覺得自己好像愧對他們沒有把自己的身體照顧好","沒有人安慰我、沒有人拍拍我、沒有人說會沒事的、沒有人站在我這邊"}:
            continue
        if label == "依賴_他人":
            if "不可取" in sent:
                del_list.append((sent, label))
                continue
            else:
                new_E.append((sent, label))
        else:
            new_E.append((sent, label))
    ev['E'] = new_E
    return ev


def filter_event_F_dict(ev):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'F' not in ev:
        return ev
    new_F = []
    for sent, label in ev['F']:
        if sent in {'我太過於敏感', '因為她怕我丟錯東西', '一開始置我於焦慮跟恐慌的人到底有什麼立場發言',
                    '其實我好害怕孤單', "現在至少煩躁程度不會爆表", '什麼都不害怕失去', '也不知道能不能吹出聲音',
                    '我沒有吃過任何一顆抗憂鬱抗焦慮劑', '跟老師說憂鬱的事還要擔心老師會不會覺得我很壞',
                    "所以其實相信醫生就配合治療覺得沒有這麼害怕這件事情了",
                    "所以我以前擔心將這件事情分享給別的的時候我會更加的憂傷"}:
            continue
        else:
            new_F.append((sent, label))
    ev['F'] = new_F
    return ev


def filter_event_G_dict(ev, input_text):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'G' not in ev:
        return ev
    new_G = []
    for sent, label in ev['G']:
        if sent in {"脫離自卑", '只因為你們不這麼認為就要否定我', "我恨透自己的無能",
                    "今天的治療無法道盡兩週來發生的事情", "我已經將近兩年沒有正面跟這個廢物講過任何一句話了",
                    "自己做的事後悔整天怪人", '但求之不得是最糟糕的',
                    '婆家也不會喜歡媳婦每天往娘家跑的(我看過身邊很多例子了) 我如果要生養小孩就沒辦法工作這樣他們經濟壓力會很大',
                    '我想起z曾說難道要讓這個家繼續爛下去嗎', '我很怕我自殺造成別人的困擾', "我想即使我痛恨自己的憂鬱",
                    "說出來是不是被別人討厭", '但我不想隱瞞而由自己承擔一切你們的錯誤我好想說出來',
                    "也發現自己沒有愛人的能力", '請原諒我的笨拙但請相信我一直都在努力讓每件事都好'}:
            continue
        if label == '討厭_自己':
            if sent in {"也開始厭惡自己的存在", "最讓我討厭的人還是我自己"}:
                new_G.append((sent, label))
                continue
            # —— 1. 做 SRL ——
            try:
                doc = mtl(sent, tasks=['srl'])
                last_srl_round = len(doc['srl'])
                frame = doc['srl'][last_srl_round - 1 if last_srl_round > 0 else last_srl_round]
            except Exception:
                # SRL 失敗就當作保留
                new_G.append((sent, label))
                continue

            # —— 2. 檢查是否需刪除 ——
            delete_flag = False
            for tok, role_lbl, *_ in frame:
                # ARG0 不是第一人稱 → 刪除
                if role_lbl == 'ARG0' and tok not in FIRST_PERSON:
                    delete_flag = True
                    break

            if delete_flag:
                del_list.append((sent, label))
            else:
                new_G.append((sent, label))
        elif label in {'我_爛', '是_廢物', '覺得_爛'}:
            delete_flag = False
            input_list = split_into_sentences(input_text)
            idx = input_list.index(sent)
            prev_sentence_2 = input_list[idx - 2] if idx - 2 >= 0 else ''
            prev_sentence_1 = input_list[idx - 1] if idx - 1 >= 0 else ''
            next_sentence = input_list[idx + 1] if idx + 1 < len(input_list) else ''
            combined = prev_sentence_2 + prev_sentence_1 + sent + next_sentence
            special_word = {"工作", "職場", "學業", "學習", "做得不夠好", "做不好", "職涯"}
            for word in special_word:
                if word in combined:
                    delete_flag = True
                    del_list.append((sent, label))
                    break
            if delete_flag:
                continue
            else:
                new_G.append((sent, label))
        else:
            new_G.append((sent, label))

    ev['G'] = new_G
    return ev


def filter_event_H_dict(ev):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'H' not in ev:
        return ev
    new_H = []
    for sent, label in ev['H']:
        if sent in {"沒辦法忍受無所事事的我不知道這時候該怎麼辦", '那也無法改變我對於事情的看法',
                    '就算出門前好好整理自己也沒用', "沒有什麼事情讓我留戀的", "而我又對現實無能為力",
                    "我根本沒有改變的能力跟勇氣", "我已經將近兩年沒有正面跟這個廢物講過任何一句話了",
                    "也不會特別為了什麼事太開心", "我到今天還是無法接受這樣的事實", "我很乖也沒用",
                    "好像也不得不面對一些過往沒有細想的事情", '一些無法解釋的事情', '會不會其實現在做的任何事',
                    '會不會其實現在做的任何事', "也發現自己沒有愛人的能力",
                    '請原諒我的笨拙但請相信我一直都在努力讓每件事都好', '不會每次都去想到生病這件事啦',
                    "比較不會去想說怎麼癌症這件事情", "好像沒有什麼事情困擾著", "沒有什麼事情難以釋懷",
                    "也沒有想要去做這件事情", "所以其實相信醫生就配合治療覺得沒有這麼害怕這件事情了",
                    "沒有沒有什麼事情困擾我","我不會有什麼事情困擾、難以釋懷", '沒有什麼事情達不到',
                    "感覺從來沒有想到這些事情對我的身體帶來這麼大的傷害就是給我的一個檢討讓我能夠更去看清一些事情很多的事情都沒有那麼嚴重",
                    "所以不知道你有沒有讓自己定期放空、遠離工作"}:
            continue
        else:
            new_H.append((sent, label))
    ev['H'] = new_H
    return ev


def filter_event_I_dict(ev):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'I' not in ev:
        return ev
    new_I = []
    for sent, label in ev['I']:
        if sent in {"你沒有看到別的同學背後付出的努力」", "沒有人嗆回去感覺好像整個世界都認同這種扭曲價值觀一樣",
                    "覺得就算他沒有完全病理解除至少也是可以癌細胞和平共處",
                    "有的時候當食慾沒有辦法像一班的時候會看到家人的心急然後擔心"}:
            continue
        if label == "沒有人_稱讚":
            if "痛苦" in sent:
                del_list.append((sent, label))
                continue
            else:
                new_I.append((sent, label))
        else:
            new_I.append((sent, label))
    ev['I'] = new_I
    return ev


def filter_event_J_dict(ev):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'J' not in ev:
        return ev

    new_J = []
    for sent, label in ev['J']:
        if sent in {"努力的假裝自己是個正常人", "那又何必迎合他人的期待浪費時間又浪費錢呢",
                    '不安爆表但是也不敢跟老公說', '不要在乎他人眼光', '不要在意別人對我的看法'
                                                                      '但得知其他人因為家庭環境優渥而可以隨意達成我辛辛苦苦才能達成的目標',
                    "但是就是變成是你要維持體重所以你必須要告訴自己三餐就是要正常吃",
                    "然後照顧我照顧小朋友就覺得會比較有種對他比較有點小小抱歉的感覺啦", "我再發生什麼事情我都會忍耐"}:
            continue
        if label == '我_迎合':
            print(f' - {sent}   ({label})')
            # 只有同時符合「從句補語」&&「否定」才刪
            delete_flag = has_clausal_complement(sent) and has_negation(sent)
            if "遵從醫囑" in sent:
                delete_flag = True

            if delete_flag:
                del_list.append((sent, label))
            else:
                new_J.append((sent, label))
        else:
            new_J.append((sent, label))

    ev['J'] = new_J
    return ev


def filter_event_K_dict(ev):
    if not isinstance(ev, dict) or 'K' not in ev:
        return ev

    new_K = []
    for sent, label in ev['K']:
        if sent in {'我到今天還是無法接受這樣的事實', "說著「你為什麼一定要逼我這些問題呢」",
                    '以前某次逼我逼到我想要全家一起死一死', '我還是強迫自己思考'}:
            continue
        if label != '逼死_自己':  # 先過濾，不用做 NLP
            new_K.append((sent, label))
            continue
        print(f' - {sent}   ({label})')
        # ---------- HanLP 一次出所有任務 ----------
        try:
            doc = mtl(sent, tasks=['tok', 'pos', 'srl'])
            tokens = doc['tok']  # list[str]
            tags = doc['pos']  # list[str]
            frames = doc['srl']
            frame = frames[-1] if frames else []
        except Exception:
            new_K.append((sent, label))
            continue

        # ---------- 刪除邏輯 ----------
        delete_flag = False

        # 1) ARG0 為第一人稱
        for word, role_lbl, *_ in frame:
            if role_lbl == 'ARG0' and word not in FIRST_PERSON:
                delete_flag = True
                break
            if role_lbl == 'ARG1' and word not in FIRST_PERSON:
                delete_flag = True
                break
        # ---------- 收集結果 ----------
        if delete_flag:
            del_list.append((sent, label))
        else:
            new_K.append((sent, label))
    ev['K'] = new_K
    return ev


def filter_event_L_dict(ev):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'L' not in ev:
        return ev
    new_L = []
    for sent, label in ev['L']:
        if sent in {"所以是不是我一個小錯誤就是要被唸", "現在至少煩躁程度不會爆表",
                    "但是就是變成是你要維持體重所以你必須要告訴自己三餐就是要正常吃",
                    "還有就是可能不能像以前那樣想吃什麼就吃什麼",
                    "但我就是會覺得想要把關注點、生活重心放在自己跟小孩子身上"}:
            continue
        else:
            new_L.append((sent, label))
    ev['L'] = new_L
    return ev


def filter_event_M_dict(ev):
    """傳入一列的 event (str / dict)，回傳過濾後的 event 字串"""
    if not isinstance(ev, dict) or 'M' not in ev:
        return ev
    new_M = []
    for sent, label in ev['M']:
        if sent in {"就是長輩自己原生家庭有人酗酒的問題"}:
            continue
        else:
            new_M.append((sent, label))
    ev['M'] = new_M
    return ev
