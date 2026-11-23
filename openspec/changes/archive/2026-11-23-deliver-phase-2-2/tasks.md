# Tasks

## 1. 清洗範圍與辭典語別表（paths.py）

- [x] 1.1 先寫測試（紅）：`tests/aiyalaeho/cleaning/test_paths.py` 加 `targets()` 的 scenario——fixture 目錄有已交付、pending、版型異常三種集，只留已交付、照成果檔名排序；`dictionary_variety()` 對表上沒有的多集族語中止並指名族語。`.tox/unittest/bin/python -m unittest tests.aiyalaeho.cleaning.test_paths` 失敗在找不到這兩個函式
- [x] 1.2 實作（綠）：`scripts/aiyalaeho/cleaning/paths.py` 刪 `TARGETS`、加 `targets(catalogue)` 與 `dictionary_variety(language)`；`DICTIONARY_VARIETY` 補布農「郡群」、排灣「北排灣」、雅美「」、魯凱「霧台」、賽德克「德固達雅」、拉阿魯哇「」、太魯閣「」，註記 2026-11-23 量 xlsx。1.1 的測試通過

## 2. 逐條語言標記（source.py）

- [x] 2.1 先寫測試（紅）：`fixtures.py` 合成逐條語言標記（純族語、族語夾雜華語、華語、無法確定各有）；`test_source.py` 加 `language_marks()` 的 scenario——條數不同、少一個字幕編號、多一個字幕編號都中止並指名集數與編號；`own_language()` 只留純族語與族語夾雜華語，標籤取自 `langcheck.mark` 的常數。單元測試失敗在找不到函式
- [x] 2.2 實作（綠）：`scripts/aiyalaeho/cleaning/source.py` 加 `language_marks(srt_name, entries, path=None)`（預設讀 `paths.LANGCHECK_MARKS`）與 `own_language(entries, marks)`。2.1 的測試通過

## 3. 命令列接上（__main__.py）

- [x] 3.1 先寫測試（紅）：★ `tests/aiyalaeho/cleaning/test_main.py`——fixture 節目目錄（同族兩集，其中一集夾「無法確定」列；單集一族；一集 pending），建 `Context` 後斷言：候選只有多集那族、別族來賓列的詞不在候選與全語料次數裡、語言別推測只用本族語列、單集族語與「無法確定」的列仍出現在 `_clean_all` 的修改裡、單一語別族語把握為「單一語別」、辭典語別與該集語別相同時權威含辭典。測試失敗
- [x] 3.2 實作（綠）：`__main__.py` 範圍改用 `paths.targets()`；`Context` 每集讀全部 Entry 與篩過的本族語 Entry，推測、候選、`_corpus()` 吃篩過的；`step_lexicon` 的 Kaldi 詞表照多集族語蒸餾、辭典語別經 `dictionary_variety()`；`__init__.py`、`dialect.py` 的說明文字更新。3.1 與整個 `tests/aiyalaeho/cleaning/` 通過
- [x] 3.3 文件：`tests/aiyalaeho/cleaning/README.md` 對照表加 design 那 13 列；`scripts/aiyalaeho/README.md`〈清洗〉改範圍說明。`tox -e flake8`、`tox -e unittest` 全過

## 4. 跑 39 集清洗

- [x] 4.1 `python -m scripts.aiyalaeho.cleaning 詞庫` 與 `候選`：`1-詞庫/Kaldi詞表/` 多出布農、排灣、雅美；`2-候選/` 恰為阿美、布農、泰雅、排灣、雅美、賽夏、卑南七份；印出的 39 集語言別推測中，布農 111／119／122 的郡群覆蓋率比未篩時（22%／24%／33%）高
- [x] 4.2 `送判 文字`，照 `brief_text.md` 派 Opus subagent 同步平行判各批（只送新詞），`匯入 文字` 無缺漏、無多列
- [x] 4.3 `送判 看圖`，照 `brief_image.md` 派 Opus subagent 判各批，`匯入 看圖` 無缺漏
- [x] 4.4 `清洗` 與 `報表`：`4-清洗版/` 39 個檔，逐檔與交付 SRT 比對只有標籤後文字不同；`5-交付/` 四份 CSV 涵蓋 39 集、處理方式只有四個值、UTF-8 無 BOM、LF；重跑一次 `報表` 逐 byte 相同
- [x] 4.5 改 `kithann/out/aiyalaeho-清洗/README.md`：範圍改為節目目錄全部已交付集、多族來賓集只做 a 項、與第2-1期 10 集版本的關係
- [x] 4.6 把關：`tox -e rebuild`（Kari-SRT 逐 byte 不變、集數＝inventory 非 pending 筆數）、`tox -e e2etest`、`python3 -m scripts.news.name_catalogue --check` 全過；`git -C Kari-SRT status --short` 沒有任何變動

## 5. 第2-2期報告（kithann/驗收/第2-2期/交付內容/）

- [x] 5.1 `族語新聞清洗報告_v1.2.md`：複製第2-1期補件 v1.1 再改——修改歷程加 v1.2；〈二、2. 進度〉表改成實際完成數；〈三、雙語字幕〉範圍與數量（集數、組數、高中信心、不採用原因、條數、時長、詞數字數、抽查結果）全部從 Kari-SRT 的 `news/2-asr-whisper/2-csv-analysis/` 與 `news/1-ocr/3-srt/` 重算；新增〈四、交付資料目錄〉（Kari-SRT 全目錄總表；`news/1-ocr/3-srt/` 與 `news/2-asr-whisper/` 三個資料夾細寫）；〈與前期交付的關係〉寫明 133 集全部以本期為準。不手動折行、不寫程式名、不提上字文稿句對
- [x] 5.2 `族語節目《開會了》清洗報告_v1.2.md`：複製 v1.1 再改——範圍 39 集（各集族語別、語言別代號、字幕數表）、逐條語言標記 39 集的分布、清洗 a–d 數字以 4.4 的四份 CSV 重算、多族來賓集只做 a 項的說明、版型異常 5 集說明（083 只有華語字幕；088、090、098、116 沒有字幕，所以無字幕檔）、第2-1期 10 集結果併入本次重算以本次為準
- [x] 5.3 `成果報告書-第2-2期語料處理.md`：「第 2 批族語節目及新聞語料處理」一節，照第2-1期補件版對應段落的結構（新聞與開會了各一張數量表、SRT 節錄、清洗 a–d 對照表、詳見附件），交付方式寫 Kari-SRT 壓縮檔加開會了清洗產出
- [x] 5.4 核對：三份報告裡的每個數字都能從 Kari-SRT 或 `kithann/out/aiyalaeho-清洗/5-交付/` 重算得到（算法寫進回覆檔）；用詞照 CLAUDE.md（偏上／偏下、語言別、Claude Vision 等正式名稱，不用對岸用語）

## 6. 回報

- [x] 6.1 寫 `kithann/tuiue/<MMDD>/<MMDD-HHMM>-<SESSION>.md`：清洗 39 集的數字、與第2-1期的差異、報告三份的位置、使用者要自己搬的檔案清單（`4-清洗版/` 與 `5-交付/` 四份 CSV）、報告數字的算法
