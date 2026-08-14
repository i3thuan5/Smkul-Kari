# refine-cue-timing 任務

標記 `【使用者】` 的步驟含 git 操作，由使用者執行（Claude 備好指令）。
前提：reorg-subtitle-pipeline 已 archive、working tree 乾淨。

## 1. 前置確認

- [ ] 1.1 SFTP 盤點：`2月原始mxf檔` 22 支俱在、位元組數與 `inventory.json`
      相符；缺集列名（該集維持粗切，不阻塞）
- [ ] 1.2 對現有 `Kari-SRT/srt/*.srt` 建 SHA-256 快照與逐 cue 文字序列
      快照，存 change 目錄（換版時驗「只動時間、不動文字」的基準）
- [ ] 1.3 確認 `.sftp-pass` 可用、STAGE 磁碟餘裕 ≥ 20GB

## 2. 精修核心與 SRT 留白

- [ ] 2.1 `scripts/news/refine_cues.py`：邊界窗 25fps 解碼、逐幀分類
      （D1）、三種邊界規則、不明區段取中點、連續 2 幀採信
- [ ] 2.2 全集原子驗證與寫回（D3）：|Δ|≤0.2s、start<end、不交叉；
      manifest 記 `refined` 並以 ffprobe 回填 `duration`（現有
      manifest 沒有這欄，留白的影片長度上限要靠它）；違規整集不寫、
      列名退出
- [ ] 2.3 參考 mask 抽樣與污染換樣（Risk 2）；分類不明的邊界維持粗切
      並計數回報
- [ ] 2.4 `tests/news/test_refine.py`（離線 fixture）：分類三規則、
      中點規則、±0.2s 安全網、原子性（一個壞邊界→整集不寫）、
      refined 標記
- [ ] 2.5 SRT 留白（design D6）：`make_srt` 組裝時每句前後各延伸
      `min(0.5, 間隔/2)`——間隔不足時中點相接（可相接不重疊），
      再以 `[0, duration]` 截短；只動 SRT 輸出，`cues.json` 不含留白
- [ ] 2.6 `tests/`：留白 scenario（孤立句 ±0.5s、1.0–2.0/2.2–3.2 →
      1.0–2.1/2.1–3.2 中點案例、開頭不出負值、結尾不超過 duration、
      時間軸資料無留白）
- [ ] 2.7 `make_srt` 的 `.qc.json` 品管副產物改寫到
      `kithann/out/qc/`（現在跟著 SRT 寫進 `Kari-SRT/srt/`，
      污染資料正本——已手動清過一次，要根治）
- [ ] 2.8 flake8 + 全套單元測試通過

## 3. verify_band 判準補驗

- [ ] 3.1 `tests/news/test_verify_band.py`：合成剖面 pin spec 兩個
      scenario（紅帶低位 y=917 型→過；紅帶侵入 region→擋）
- [ ] 3.2 實測：下載 `卑南語-20210103S1800.mp4` 跑 verify_band
      （不加 --quiet）、人工看剖面與 sheet_001.png，結果記入
      README「還沒做的」段落收掉該懸案

## 4. 22 集回頭精修

- [ ] 4.1 `scripts/news/refine_fetch.sh`：逐集下載→驗位元組→
      `refine_cues`（讀寫 `Kari-SRT/cues/`）→刪影片；可中斷續跑
      （已 refined 的集跳過）；STAGE 改 `kithann/out/stage/` 並實作
      共用規則（同名同位元組數重用、`.keep` sentinel 不刪、
      `stage.lock` 防並行，design D4）
- [ ] 4.2 第一支順跑 verify_band 全剖面人工確認（D5）
- [ ] 4.3 執行全批；產出 `timing-delta.txt`（逐集偏移分佈統計）存
      change 目錄
- [ ] 4.4 `make_all` 重產 SRT；驗證：逐 cue 文字序列與 1.2 快照相同
      （時間行含精修＋留白兩種變化，文字零改動）；`rebuild --verify`
      以新資料通過
- [ ] 4.5 【使用者】Kari-SRT 一個 commit 同時換 `cues/` + `srt/`
      ＋ push；主 repo pointer bump

## 5. 新月份流程整合

- [ ] 5.1 `fetch_sftp.sh`：cues 成功後、刪影片前插 `refine_cues`
      （失敗不擋批次，保留粗切並記 log）
- [ ] 5.2 `.claude/commands/smkul-news.md` 與 `scripts/news/README.md`
      補精修步驟說明；README「還沒做的」移除已收掉的兩項
- [ ] 5.3 【使用者】主 repo 最終 commit

## 6. 二月補集：每族語至少 2 集（不管有沒有文稿）

範圍（design D7）：不做全部 64 集，先補到每族語 ≥2 集，缺額取 2 月內
播出較早的集數。候選 13 集（經使用者確認）：

| 族語 | 已完成 | 補集 |
|---|---|---|
| 卑南 | 0 | 038晚、045晚 |
| 拉阿魯哇 | 0 | 038晨、045晨 |
| 邵 | 0 | 037晨、044晨 |
| 排灣 | 0 | 037晚、044晚 |
| 布農 | 1 | 042晚 |
| 撒奇萊雅 | 1 | 041晚 |
| 賽夏 | 1 | 043晚 |
| 雅美 | 1 | 040晚 |
| 鄒 | 1 | 041午（034午 目錄無影片路徑，跳過） |

排灣 037晚 與 鄒 041午 本機那份是上傳不完整的 mxf，但 SFTP 上的
版本應是完整的——**這兩支排最前面先做**，下載後以位元組數驗證；
若 SFTP 版本仍不完整，遞補：排灣 → 051晚、鄒 → 055午。

- [ ] 6.1 smkul.csv 先補上 13 列「待處理」（design D7 pending 語意）：
      兩份 `inventory.json` 擴充 13 集（11 新增＋解除 037晚／041午
      的 truncated 標記）；`rebuild.py` 增「未交付集」判定——cues 與
      srt **皆無** → 產「待處理（尚未切cue）」列、不比對；只缺其一
      仍照舊指名失敗（照舊靠 tracker 逐 byte 比對把關）；`make_all` 重產
      `smkul.csv`（22 已產生＋13 待處理）；`rebuild --verify` 通過、
      測試對應更新；【使用者】commit
- [ ] 6.2 SFTP 盤點確認：13 支影片俱在、位元組數合理（CBR 換算）、
      優先驗 037晚／041午 兩支是否完整（不完整即啟動遞補並回改
      6.1 的 inventory）；估 sheet 數與視覺辨識 token，
      【使用者】同意後才放 subagent
- [ ] 6.3 `build_inventory.py` 改目錄驅動（design D7）：重跑可重現
      6.1 的 35 集 inventory，`srt_name`／slug 規則沿用
- [ ] 6.4 逐集 fetch→cues→精修→刪影片（走 5.1 整合後的
      `fetch_sftp.sh`）；第一支開 `sheets/sheet_001.png` 確認圖條
      只有對白（晨間版型第一次見，必看）
- [ ] 6.5 文稿處理：有文稿的集照舊 `gap_sheets` 對齊（2 月文稿本機
      已有）；無文稿的集全 gap，流程相同
- [ ] 6.6 視覺辨識：subagent 每批 24 張、TSV 直寫
      `Kari-SRT/vision/<srt_name>/`；逐集 `ingest` 驗證匯入；
      有文稿的集跑 C-pass 普查（`rtf_sheets`＋`compare_rtf --apply`）
- [ ] 6.7 `make_all` 組裝新集（含精修時間與留白）；`rebuild --verify`
      全體（22＋新集）通過；`smkul.csv` 狀態列更新
- [ ] 6.8 【使用者】Kari-SRT commit 新集資料＋push；主 repo pointer
      bump 與 `inventory.json` 等變更 commit
