# tests/aiyalaeho/cleaning/：開會了字幕清洗（spec × scenario × 測試檔）

`scripts/aiyalaeho/cleaning/`：承辦對第2-1期驗收第 3 點的回應——對已交付的《開會了》（第2-1期 10 集，第2-2期起是節目目錄全部已交付集）做 a 空白標點、b 同族語跨集拼寫、c 對辭典、d 修改前後對照表。**Kari-SRT 只讀**，產出在 `kithann/out/aiyalaeho-清洗/`。E樂園、Kaldi 詞表的蒸餾在 `scripts/lexicon/`，對照表見 `tests/lexicon/README.md`。

全部離線、fixture 合成：`fixtures.py` 用正式的 `make_srt` 組出一個縮小的 1-cues＋2-vision＋3-srt（相鄰同文字的 cue 會被併，跟交付檔一樣），圖條路徑照真檔寫舊名 `strips/`。

scenario 寫「**會怎麼錯**」。標 ★ 的是 2026-10-15 量真資料或實作時踩到的；標 ☆ 的是 2026-11-23 擴到 39 集時量到的。`test_main.py` 用 fixture 組小目錄、patch 掉 Kari-SRT 的路徑，直接建命令列的 Context。

| spec | scenario（會怎麼錯） | 測試檔 |
|---|---|---|
| 清洗範圍取自節目目錄 | ☆ 寫死清單：節目目錄 39 集、程式只跑 10 集，報告寫 39 集但清洗版只有 10 個檔 | `test_paths.py`、`test_main.py` |
| 清洗範圍取自節目目錄 | ☆ 版型異常 5 集（083 只有華語字幕、088／090／098／116 無字幕）被算進範圍，找不到 SRT 而中途倒掉 | `test_paths.py` |
| 清洗範圍取自節目目錄 | pending 的集被算進「多於 1 集」，單集族語被當多集送 b、c | `test_paths.py`、`test_main.py` |
| b、c 項與語言別推測只看本族語的字幕列 | ☆ 布農 119 的 223 條別族來賓（賽夏、排灣、雅美、噶瑪蘭）進了布農候選與全語料次數，布農查無詞形暴增（不篩 3,944 個） | `test_source.py`、`test_main.py` |
| b、c 項與語言別推測只看本族語的字幕列 | 「無法確定」的列被整條丟掉，連 a 項規則清洗都沒做，修改前後對照表少了那些空白修正 | `test_main.py` |
| b、c 項與語言別推測只看本族語的字幕列 | 交付 SRT 重組過、逐條語言標記沒重建，字幕編號錯位，篩到的是別條字幕的標籤——缺、多、重複都要中止並指名集數與編號 | `test_source.py` |
| b、c 項與語言別推測只看本族語的字幕列 | 標籤用字面值比對，langcheck 改了措辭後全部列被篩掉、候選變空也不報錯 | `test_source.py` |
| 多族來賓集整集不做 b、c | ☆ 布農 111 標「純族語」的列還有卑南語（逐條語言檢查要別族高 40 點才標無法確定），篩掉無法確定後郡群覆蓋率仍只有 29%，2,445 個只在 111／119／122 的詞形被送判——「無法確定」佔一成以上的集整集不比 | `test_source.py`、`test_main.py` |
| 多族來賓集整集不做 b、c | 門檻設太低，阿美 082（6.0% 無法確定）被整集排除；三集是 22.0～27.1%，門檻一成切在中間 | `test_source.py`、`test_main.py` |
| 語言別推測 | ☆ 119 整集郡群覆蓋率 24%、只因領先卡群 10 點被判「高」——別族來賓的列進了分母 | `test_main.py` |
| 語言別推測 | E樂園 只有一個語別的族語（雅美、太魯閣）跑覆蓋率比較、把握寫「高」而不是「單一語別」 | `test_main.py` |
| b、c 項候選與證據 | ☆ 辭典語別表用 `.get(族, "")`：沒量過的族語被當不分語別，辭典永遠不當權威、錯得悄悄的——要中止並指名族語 | `test_paths.py` |
| b、c 項候選與證據 | 辭典語別與該集語別相同（布農辭典郡群、114 判郡群）時，權威要含辭典才有的詞 | `test_main.py` |
| a 項規則清洗 | ☆ 單集族語（太魯閣 123）不做 b、c，被整集跳過，連 a 項都沒做 | `test_main.py` |
| 產出只寫 kithann/out | 輸出目錄設到 Kari-SRT 底下沒擋，交付資料被改；只比字串開頭的話 `Kari-SRT-copy` 也被誤擋 | `test_paths.py` |
| Claude 判定的送出與匯入 | ★ 1-cues 清單的圖條路徑寫舊名 `strips/`，實際目錄是 `2-strips/`，照清單拼找不到 | `test_source.py` |
| Claude 判定的送出與匯入 | ★ 一條字幕由多個同文字 cue 合成（084 有 7 條），看圖只送第一個 cue 的圖條 | `test_source.py` |
| Claude 判定的送出與匯入 | 2-vision 改過而 3-srt 沒重組，字幕編號對 cue 整串錯位，送去看圖的是別條字幕的圖 | `test_source.py` |
| a 項規則清洗 | ★ 冒號被當詞尾標點刪掉（`'a'iyalaeho:`、`kapayaka:i'`、`abaw:`）——`kithann/規範/` 沒有冒號規定，辭典照收 | `test_rules.py` |
| a 項規則清洗 | ★ `’` 後夾空白（全語料 10 行，087 `mena’   u`）被規則自己併掉，沒等看圖 | `test_rules.py` |
| a 項規則清洗 | ★ 雙撇 `"`（085 `"awsa'`、092 `'a"iy`）被當重複標點或撇號正規化 | `test_rules.py` |
| a 項規則清洗 | ★ 華語斷句空白（086 有 12 條）被整個刪掉，而不是縮成一個 | `test_rules.py` |
| a 項規則清洗 | ★ 3 點刪節號被縮掉；081 `Padaka...........` 沒縮成 3 點 | `test_rules.py` |
| a 項規則清洗 | ★ 族語列本來空的（082 有 171 條）清洗後標籤行不見 | `test_rules.py`、`test_apply.py` |
| 語言別推測 | ★ 已標語別的 068（秀姑巒只比海岸高 3 點）被重推成「中」 | `test_dialect.py` |
| 語言別推測 | ★ 只領先 2～3 點（084 海岸對秀姑巒、087 西群對知本）被判「高」 | `test_dialect.py` |
| 語言別推測 | ★ 分段第一名交錯（082，南勢只佔 5/10 段）被判成全集最高的南勢，而不是「混合」 | `test_dialect.py` |
| 語言別推測 | 詞次不夠的段投票，把高判成混合；賽夏只有一個語別卻跑推測 | `test_dialect.py` |
| b、c 項候選與證據 | ★ 套 `vocab.fold` 語言別正音，082 `kaku` 被折成 `kako`，語言別差異從表上消失 | `test_candidates.py` |
| b、c 項候選與證據 | ★ 用辭典當權威：087 `harem` 南王辭典沒有（只收 `garem`），西群 E樂園 有，被列成錯字 | `test_candidates.py` |
| b、c 項候選與證據 | ★ 只差一個字母（`kamo`／`kamok`）被直接判錯字 | `test_candidates.py` |
| b、c 項候選與證據 | ★ 送判的詞經「差一個字母」一路連鎖，卑南串成 68 個詞的一組；候選這層只把語言別差異對連成組 | `test_candidates.py` |
| b、c 項候選與證據 | ★ 族語列夾漢字（約 430 條，`李芳媚老師`）、注音、數字進了候選 | `test_candidates.py` |
| b、c 項候選與證據 | ★ 節目名錯拼（`'a'iylaeho:`、`'a'alaeho:`、`'a'iylahaeho:`）分散在各族語；衍生詞 `'a'iyalaeho:an`（冒號後還接詞綴）被誤當錯拼 | `test_candidates.py` |
| b、c 項候選與證據 | `’ 夾空白` 切開後 `mena'` 查無，被當拼寫候選——比對要用暫時併起來的 `mena'u` | `test_candidates.py` |
| b、c 項候選與證據 | Kaldi 詞表見過的被送判或當建議寫法；大小寫、`ʼ`／`'` 被當不同詞形 | `test_candidates.py` |
| Claude 判定的送出與匯入 | 判定少列、多列、類別不在字彙裡被恬恬吞掉；判錯字沒附建議寫法；OCR 讀錯沒寫畫面上的寫法 | `test_verdicts.py` |
| Claude 判定的送出與匯入 | 重跑把已送過的又送一次；還沒回答的批次沒被點名 | `test_verdicts.py` |
| 清洗版 SRT | ★ 在 cue 層清洗後重組，相鄰同文字被併掉、字幕編號位移，對照表對不上交付版 | `test_apply.py` |
| 清洗版 SRT | 沒有判定（語言別差異、不確定、看不出來）的詞也被改；以字串替換改到別的詞裡面（`kako` 改到 `kakoay`）；句首大寫改完變小寫 | `test_apply.py` |
| 清洗版 SRT | 錯字的出現位置對錯一條，改到別條字幕——要中止並指名第幾條 | `test_apply.py` |
| 交付 CSV | 同一條改好幾處只記一列，看不出改了哪裡 | `test_apply.py` |
| 交付 CSV | ☆ 泰雅 118 Isat：Claude 依華語「印刷」建議借詞 Insat（任何語別教材都沒有），程式挑權威裡長得像的 iyat（「不是」）照改——39 集量到 35 處這樣被取代，多數改壞。只有 Claude 的建議見於別的語別、權威詞只差一個字母（garem → harem）才取代，其餘保留 Claude 的建議、待討論、不改 | `test_report.py` |
| 交付 CSV | ☆ 泰雅 120 Goko：Claude 建議的 Gako 見於四季、澤敖利，但權威詞 Goho 差兩個字母，不算語別替換 | `test_report.py` |
| 交付 CSV | ☆ 布農 119 篩掉無法確定後郡群仍只有 34%，照算判「高」、填 `bnn-x-isbk`——多族來賓集把握寫「多族來賓」、退族語別代號 | `test_report.py` |
| 交付 CSV | 建議寫法沒照依據順序（Claude 建議南王的 `garem`，087 西群該用 `harem`）；平手沒用開會了全語料次數決勝 | `test_report.py` |
| 交付 CSV | 看不出來的錯字被標「已修改」；判語言別差異也給了建議寫法；處理方式出現四個值以外的字 | `test_report.py` |
| 交付 CSV | 語言別判「中」卻填了語言別代號（087 要填 `pyu`，不是 `pyu-x-mkzy`） | `test_report.py` |
| 交付 CSV | 有 BOM 或 CRLF；重跑列順序不同、byte 不同 | `test_report.py` |
| 人工改判 | ★ 看圖確認畫面就是這樣、Claude 判錯字，但其實可能是語言別差異（082 `odal` 整集一致不寫撇號、087 `zalaw` 整集一致用 z），或改了反而錯（087#286 `tatena 'mu` 改成 `tatena' 'mu`）——使用者改判的詞照改就錯；兩份表要標待討論並寫出改判理由 | `test_report.py` |
