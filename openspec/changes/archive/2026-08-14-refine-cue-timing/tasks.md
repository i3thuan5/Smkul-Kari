# refine-cue-timing 任務

標記 `【使用者】` 的步驟含 git 操作，由使用者執行（Claude 備好指令）。
前提：tidy-subtitle-pipeline 已完成（引擎拆檔、文稿路徑移除、
inventory 單一正本＋pending 機制）、working tree 乾淨。集數一律
推導：範圍 = store inventory 非 pending 筆數（寫此文時 35 集）。

## 1. 前置確認

- [x] 1.1 SFTP 盤點：全部已交付集（inventory 非 pending）的 mxf 俱在
      `2月原始mxf檔`、位元組數合理；缺集列名（該集維持粗切，不阻塞）
- [x] 1.2 對現有 `Kari-SRT/srt/*.srt` 建 SHA-256 快照與逐 cue 文字序列
      快照，存 change 目錄（換版時驗「只動時間、不動文字」的基準）
- [x] 1.3 確認 `.sftp-pass` 可用、STAGE 磁碟餘裕 ≥ 20GB

## 2. 精修核心與 SRT 留白

- [x] 2.1 `scripts/news/refine_cues.py`：邊界窗 25fps 解碼、逐幀分類
      （D1）、三種邊界規則、不明區段取中點、連續 2 幀採信
- [x] 2.2 全集原子驗證與寫回（D3）：|Δ|≤0.2s、start<end、不交叉；
      manifest 記 `refined` 並以 ffprobe 回填 `duration`（現有
      manifest 沒有這欄，留白的影片長度上限要靠它）；違規整集不寫、
      列名退出
- [x] 2.3 參考 mask 抽樣與污染換樣（Risk 2）；分類不明的邊界維持粗切
      並計數回報
- [x] 2.4 `tests/news/test_refine.py`（離線 fixture）：分類三規則、
      中點規則、±0.2s 安全網、原子性（一個壞邊界→整集不寫）、
      refined 標記
- [x] 2.5 SRT 留白（design D6）：`make_srt` 組裝時每句前後各延伸
      `min(0.5, 間隔/2)`——間隔不足時中點相接（可相接不重疊），
      再以 `[0, duration]` 截短；只動 SRT 輸出，`cues.json` 不含留白
- [x] 2.6 `tests/`：留白 scenario（孤立句 ±0.5s、1.0–2.0/2.2–3.2 →
      1.0–2.1/2.1–3.2 中點案例、開頭不出負值、結尾不超過 duration、
      時間軸資料無留白）
- [x] 2.7 flake8 + 全套單元測試通過
      （tidy 已把 make_all 改為直接呼叫 `make_srt.run()`，
      `.qc.json` 不再寫進 Kari-SRT——原 2.7 收掉）

## 3. verify_band 判準補驗

- [x] 3.1 `tests/news/test_verify_band.py`：合成剖面 pin spec 兩個
      scenario（紅帶低位 y=917 型→過；紅帶侵入 region→擋）
- [x] 3.2 實測：下載 `卑南語-20210103S1800.mp4` 跑 verify_band
      （不加 --quiet）、人工看剖面與 sheet_001.png，結果記入
      README「還沒做的」段落收掉該懸案

## 4. 全部已交付集回頭精修（含 da2f0b3 補做的 13 集）

- [x] 4.1 `scripts/news/refine_fetch.sh`：逐集下載→驗位元組→
      `refine_cues`（讀寫 `Kari-SRT/cues/`）→刪影片；可中斷續跑
      （已 refined 的集跳過）；STAGE 改 `kithann/out/stage/` 並實作
      共用規則（同名同位元組數重用、`.keep` sentinel 不刪、
      `stage.lock` 防並行，design D4）
- [x] 4.2 第一支順跑 verify_band 全剖面人工確認（D5）
- [x] 4.3 執行全批；產出 `timing-delta.txt`（逐集偏移分佈統計）存
      change 目錄
- [x] 4.4 `make_all` 重產 SRT、`publish` 定版 `smkul.csv`；驗證：
      cue 資料層逐編號文字與 1.2 快照相同（零改動）；SRT 層的
      merge 翻轉差異列入 `timing-delta.txt` 人工審閱（design D8）；
      `rebuild --verify` 以新資料通過
- [x] 4.4b 邊界規則修訂為中點制（spec／design／程式／測試同步）：
      「最後左側幀」與「第一右側幀」的中點，緊鄰與不明區段同一條式。
      35 集首批交付維持舊規則產物（偏晚 ≤0.04s，預算內），
      **不重跑**，中點制自下批起生效——使用者定案
- [x] 4.5 【使用者】Kari-SRT 一個 commit 同時換 `cues/` + `srt/`
      ＋ push；主 repo pointer bump

## 5. 新月份流程整合

- [x] 5.1 `fetch_sftp.sh`：cues 成功後、刪影片前插 `refine_cues`
      （失敗不擋批次，保留粗切並記 log）
- [x] 5.2 `.claude/commands/smkul-news.md` 與 `scripts/news/README.md`
      補精修步驟說明；README「還沒做的」移除已收掉的兩項
- [x] 5.3 【使用者】主 repo 最終 commit

## 6. 二月補集（已由外部完成，本 change 不再包含）

「每族語至少 2 集」的 13 集已於 `da2f0b3` 由另一批次以粗切精度完成
入庫（`add_episodes`→視覺辨識→`publish`），smkul.csv 隨之更新；
文稿對齊與 C-pass 路徑已於 tidy-subtitle-pipeline 移除。該 13 集
納入第 4 組回頭精修範圍，此節無剩餘工作。
