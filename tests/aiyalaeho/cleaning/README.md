# tests/aiyalaeho/cleaning/：開會了字幕清洗（spec × scenario × 測試檔）

`scripts/aiyalaeho/cleaning/`：承辦對第2-1期驗收第 3 點的回應——對已交付的 10 集《開會了》做 a 空白標點、b 同族語跨集拼寫、c 對辭典、d 修改前後對照表。**Kari-SRT 只讀**，產出在 `kithann/out/aiyalaeho-清洗/`。E樂園、Kaldi 詞表的蒸餾在 `scripts/lexicon/`，對照表見 `tests/lexicon/README.md`。

全部離線、fixture 合成：`fixtures.py` 用正式的 `make_srt` 組出一個縮小的 1-cues＋2-vision＋3-srt（相鄰同文字的 cue 會被併，跟交付檔一樣），圖條路徑照真檔寫舊名 `strips/`。

scenario 寫「**會怎麼錯**」。標 ★ 的是 2026-10-15 量真資料或實作時踩到的。

| spec | scenario（會怎麼錯） | 測試檔 |
|---|---|---|
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
| 交付 CSV | 建議寫法沒照依據順序（Claude 建議南王的 `garem`，087 西群該用 `harem`）；平手沒用開會了全語料次數決勝 | `test_report.py` |
| 交付 CSV | 看不出來的錯字被標「已修改」；判語言別差異也給了建議寫法；處理方式出現四個值以外的字 | `test_report.py` |
| 交付 CSV | 語言別判「中」卻填了語言別代號（087 要填 `pyu`，不是 `pyu-x-mkzy`） | `test_report.py` |
| 交付 CSV | 有 BOM 或 CRLF；重跑列順序不同、byte 不同 | `test_report.py` |
| 人工改判 | ★ 看圖確認畫面就是這樣、Claude 判錯字，但其實可能是語言別差異（082 `odal` 整集一致不寫撇號、087 `zalaw` 整集一致用 z），或改了反而錯（087#286 `tatena 'mu` 改成 `tatena' 'mu`）——使用者改判的詞照改就錯；兩份表要標待討論並寫出改判理由 | `test_report.py` |
