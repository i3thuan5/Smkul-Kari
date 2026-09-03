## 1. preset 搬家（本 change 對 news 唯一的檔案改動）

- [x] 1.1 全 repo grep `amis-xiuguluan-bilingual` 的引用（程式、測試、文件、work dir manifest），列出處置清單；有測試引用者先改測試
- [x] 1.2 建 `scripts/aiyalaeho/presets.json`：`aiyalaeho-bilingual`（region 同、華語列槽 h 60→**64**；上列改名 `formosan`）；自 `scripts/news/presets.json` 刪原筆。**h 收佇 64 是量出來ê**：66 ê時一个 cue ê block 140 px、超過每張 558 px ê裝箱預算 2 px，sheet 對 160 變 213（多三成閱讀量）；094 字腳到 1011，1012 以下 ink 賰 2／1，開到 1012 就夠
- [x] 1.3 驗收：`tox -e unittest` 綠；news 的 `rebuild --verify` 照樣通過（news 行為未變的證明）

## 2. paths（語料常數與名稱保護）

- [x] 2.1 `tests/aiyalaeho/test_paths.py`（紅）：store 版面常數（`Kari-SRT/aiyalaeho/` 頂層、`1-ocr/{1-cues,2-vision,3-srt}`）、`check_srt_name`（`開會了_[0-9]{3}_…`、拒路徑成分）、`stage_path` 不分層、工作區與快取路徑
- [x] 2.2 `scripts/aiyalaeho/paths.py`＋`__init__.py`（綠）：版面與保護沿 `scripts/datadirs.py` 轉出

## 3. catalogue（檔名解析、語言代號、整批登記）

- [x] 3.1 `tests/aiyalaeho/test_catalogue.py`（紅）：檔名解析逐款（標準、變體、括號註記、無字幕、混雜、無法解析略過並指名、人指定族語別補登記）；語言代號對照逐條（含三判讀：變體未註→族語級、德路固→`trv-x-trk`、非霧台→語言別照錄＋`dru`）；整批登記 pending、重跑不重複、可只登記指定集數、目錄無列（068／164）照登
- [x] 3.2 `scripts/aiyalaeho/catalogue.py`（綠）：解析＋對照表常數＋inventory 條目組法＋登記 CLI

## 4. verify_band（黃底雙槽帶前驗）

- [x] 4.1 `tests/aiyalaeho/test_verify_band.py`（紅）：合成量測——兩列各在槽內通過／整帶下移十餘 px 仍通過／單列只有華語通過／無字幕集不算失敗／新聞版型擋下（無帶＋剖面有對比）／逐集判定
- [x] 4.2 `scripts/aiyalaeho/verify_band.py`（綠）：取樣量逐列 ink 剖面，列範圍對槽界，FAIL 帶量測數字

## 5. ingest（TSV 驗證匯入）

- [x] 5.1 `tests/aiyalaeho/test_ingest.py`（紅）：每 cue 兩逝（族語列、han）；列名錯、cue 不在該批 sheet 上整批拒收；空白 cue 尾端 tab 補回；匯入後 verified 記帳
- [x] 5.2 `scripts/aiyalaeho/ingest.py`（綠）：沿 news 版改路徑與預設 TSV 位置（`2-vision/<srt_name>/b*.tsv`）

## 6. make_srt（雙列組裝）

- [x] 6.1 `tests/aiyalaeho/test_make_srt.py`（紅）：每條恆兩行帶標籤「族語：／華語：」；某列空白仍出標籤行（「族語：」後空）；兩列皆空不出；同文合併比兩行合成字串；0.5 s 留白與中點相接；不出負值不超片長；留白只在 SRT 輸出、cues.json 維持真實切換點不被回寫；qc 計數
- [x] 6.2 `scripts/aiyalaeho/make_srt.py`（綠）：走 `srtlib.assemble.chain_with_spans` 同一條鏈

## 7. tracker（9 欄進度表）

- [x] 7.1 `tests/aiyalaeho/test_tracker.py`（紅）：9 欄逐欄與順序（節目名稱、集數、族語別(英)(中)、語言別、語言代號、影片檔案位置、影片長度、成果檔名）；成果檔名＝srt_name；影片長度由 1-cues 推導；pending 不入定版表
- [x] 7.2 `scripts/aiyalaeho/tracker.py`（綠）：utf-8-sig＋CRLF 慣例同 news

## 8. make_all＋publish（整批組裝與定版）

- [x] 8.1 `tests/aiyalaeho/test_publish.py`（紅）：0-cue 集視為校讀完成、以 0 行交付、不擋整批；任一 pending 未完成整批不寫；定版後 pending 清除、smkul.csv 落 store；vision_complete 為「cue 編號集合被校讀集合涵蓋」（空集合成立），比對集合不比數量
- [x] 8.2 `scripts/aiyalaeho/make_all.py`＋`publish.py`（綠）——smkul 定版表 9 欄、無狀態欄

## 9. rebuild（離線重建驗證）

- [x] 9.1 `tests/aiyalaeho/test_rebuild.py`（紅）：僅 store 資料重建雙列 SRT＋smkul.csv 逐 byte；缺件指名非零結束；pending 跳過
- [x] 9.2 `scripts/aiyalaeho/rebuild.py`（綠）

## 10. 文件（跟程式同步，不留到最後）

- [x] 10.1 `scripts/aiyalaeho/README.md`（跑法與檔案表）；`scripts/README.md` 加 aiyalaeho 一節（`test_readme_covers_scripts` 綠）
- [x] 10.2 根 `README.md` 資料夾架構、`tests/README.md` spec × scenario 表加 aiyalaeho、`Kari-SRT/README.md` 語料層說明——並把「cue 邊界精度 0.05 秒；SRT 輸出含 0.5 秒邊界留白；時間軸永存真實切換點」寫明為**全語料**慣例（不是 news 專屬）
- [x] 10.3 文件內 preset 名稱更新（`.claude/skills/video-subtitle-srt/SKILL.md` 等提及舊名處改 `aiyalaeho-bilingual` 並註明搬家）

## 11. 068 端對端驗收（實資料）

- [x] 11.1 以登記 CLI 只登記 068（pending）；`verify_band` 對 068 通過
- [x] 11.2 沿用試跑 work dir（cues＋refine 已切）；`Kari-SRT/aiyalaeho/1-ocr/` 目錄與 README 建立
- [x] 11.3 068 視覺辨識全集（約 169 張 sheet ≈ 8 批 subagent，TSV 直接落 `2-vision/開會了_068_Amis_阿美/`），`ingest` 匯入
- [x] 11.4 `make_all` 組裝；與 `kithann/out/068-…planB-vision.srt` 逐條抽查（文字為主；時間因精修容 ±0.2 s）
- [x] 11.5 `publish` 定版（068 一集）→ `rebuild --verify` 逐 byte 通過
- [x] 11.6 總驗收：`tox -e unittest`、`tox -e flake8`、news 的 `rebuild --verify` 與 `name_catalogue --check` 照樣通過

## 12. 整批：全部有影片的集數做完（068 之外約 43 集）

> 順序要緊：**068 定版（11.5）了後才登記其餘集數**。`publish` 是整批把關——任何一集 pending 猶未做煞，規批就袂使定版，先登記 40 集會kā 068 鎖牢。

- [x] 12.1 登記其餘全部集數（catalogue 登記 CLI；本機 41 支＋伺服器上的 116ALL_無字、119-混雜、122-混雜，皆 pending）
- [ ] 12.2 三支不在本機的用 `scripts/news/sftp.sh get` 逐支下載、比位元組數；混雜兩支（119／122）切前人工看 sheet_001 確認版型——異常者暫緩、報使用者裁定，不硬切
- [~] 12.3（進行中）逐集：雙槽驗版型 → `cues --preset aiyalaeho-bilingual --sheets < /dev/null` → `refine_cues`（背景批次、跳過已切、可續跑；估約 4 h）
- [ ] 12.4 視覺辨識整批（估 ~5,800 張 sheet ≈ 240 批 × 24 張 subagent，10 批／h 約 24 h——開跑前照慣例把集數／批數／時數說出來再開始）；逐集 `ingest`
- [ ] 12.4b **長 cue 補救**（切 cue 對這批素材會切傷少，一條 cue 內底藏兩四句字幕，讀者干焦讀會著佔上久彼句，其他ê規句消失。三位讀者各自佇 083 掠著具體實例，逐集攏有 9–11 條 ≥10 秒ê cue）：**降 `change` 門檻佮收緊 `max_spread` 兩條路攏量過無效**（68→73%、~70%），愛照新聞彼爿ê做法事後補救。`scripts/news/blind_cues.py` 平行 session 這馬咧建，等in做好借過來改，莫另外造一套
- [ ] 12.5 `make_all` → `publish`（整批把關；88／90／98／116 這類 0-cue 集以 0 行交付）→ aiyalaeho `rebuild --verify` 逐 byte 全綠
- [ ] 12.6 總驗收重跑：`tox -e unittest`、`tox -e flake8`、news 與 aiyalaeho 的 `rebuild --verify`、`name_catalogue --check`；smkul.csv 定版含全部集數
