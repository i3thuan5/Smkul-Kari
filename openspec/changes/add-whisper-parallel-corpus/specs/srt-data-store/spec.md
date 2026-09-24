## ADDED Requirements

### Requirement: 平行語料層可離線重建

`Kari-SRT/news/2-asr-whisper/2-平行語料/` 裡每一集的檔，SHALL 能從下列輸入逐 byte 重建：主 repo（程式）、Kari-SRT（該集的 `1-ocr/1-cues/`、`1-ocr/2-vision/`、`2-asr-whisper/1-srt-sapolita/`、`news/smkul.csv`、`2-平行語料/校正基準.csv`）、`kithann/族語辭典/`。重建 SHALL NOT 呼叫任何模型。

辭典是這條規則唯一的外部來源：`kithann/族語辭典/` 缺檔時，重建 SHALL 從 SFTP 取得後再驗；SFTP 也取不到時，SHALL 指名中止，SHALL NOT 略過這一層而宣告通過。

`scripts.news.rebuild --verify` SHALL 涵蓋這一層。這一層沒有檔的集數 SHALL NOT 算錯，那只是還沒做到。

#### Scenario: 有人手改了入庫的 CSV

- **WHEN** 某集 `2-平行語料/` 的 CSV 被人改了一格
- **THEN** 重建驗證以非零狀態結束並指名該集

#### Scenario: 換機器沒有辭典

- **WHEN** `kithann/族語辭典/` 不存在，執行重建驗證
- **THEN** 先從 SFTP 取得辭典，再照常逐 byte 比對

#### Scenario: 辭典取不到

- **WHEN** `kithann/族語辭典/` 不存在，SFTP 也連不上
- **THEN** 驗證以非零狀態結束，說明是辭典取不到，而不是宣告通過

## MODIFIED Requirements

### Requirement: 下游階段的集數必為上游的子集

離線重建驗證 SHALL 檢查各階段之間的包含關係：`3-srt/` 的成果檔名集合 SHALL 是 `2-vision/` 的子集，`2-vision/` SHALL 是 `1-cues/` 的子集。`2-asr-whisper/2-平行語料/` 的成果檔名集合 SHALL 同時是 `1-ocr/3-srt/` 與 `2-asr-whisper/1-srt-sapolita/` 的子集。

下游有而上游沒有的集數 SHALL 使驗證以非零狀態結束，並指名是哪一集在哪一層缺——那份交付物重建不出來。上游有而下游沒有 SHALL 視為正常，那只表示還沒做到那一步。

#### Scenario: 交付 SRT 沒有對應的時間軸

- **WHEN** `3-srt/` 有某集的 SRT，`1-cues/` 沒有該集的時間軸
- **THEN** 驗證以非零狀態結束，指名該集與缺的那一層

#### Scenario: 上游多出來的集數不算錯

- **WHEN** `1-cues/` 有 75 集，`3-srt/` 只有 40 集
- **THEN** 驗證通過

#### Scenario: 平行語料沒有對應的辨識結果

- **WHEN** `2-平行語料/` 有某集的 CSV，`1-srt-sapolita/` 沒有該集的 SRT
- **THEN** 驗證以非零狀態結束，指名該集與缺的那一層
