## MODIFIED Requirements

### Requirement: 平行語料層可離線重建

`Kari-SRT/news/2-asr-whisper/2-csv-analysis/` 與 `3-srt-paragraph/` 裡每一集的檔，SHALL 能從下列輸入逐 byte 重建：主 repo（程式）、Kari-SRT（該集的 `1-ocr/1-cues/`、`1-ocr/2-vision/`、`2-asr-whisper/1-srt-sapolita/`（含 `辨識紀錄.csv` 的音長秒）、`news/smkul.csv`、`2-csv-analysis/校正基準.csv`）、`kithann/族語辭典/`，以及有補充語言別的集才需要的 `kithann/E樂園-解壓/`。重建 SHALL NOT 呼叫任何模型。

官方辭典 `kithann/族語辭典/` 缺檔時，重建 SHALL 從 SFTP 取得後再驗；SFTP 也取不到時，SHALL 指名中止。E樂園 沒有 SFTP 來源：有補充語言別的集而 `kithann/E樂園-解壓/` 不在時，SHALL 指名中止。兩種情形都 SHALL NOT 略過這一層而宣告通過。

`scripts.news.rebuild --verify` SHALL 涵蓋這兩層。這兩層沒有檔的集數 SHALL NOT 算錯，那只是還沒做到。

#### Scenario: 有人手改了入庫的 CSV

- **WHEN** 某集 `2-csv-analysis/` 的 CSV 被人改了一格
- **THEN** 重建驗證以非零狀態結束並指名該集

#### Scenario: 換機器沒有辭典

- **WHEN** `kithann/族語辭典/` 不存在，執行重建驗證
- **THEN** 先從 SFTP 取得辭典，再照常逐 byte 比對

#### Scenario: 辭典取不到

- **WHEN** `kithann/族語辭典/` 不存在，SFTP 也連不上
- **THEN** 驗證以非零狀態結束，說明是辭典取不到，而不是宣告通過

#### Scenario: 有萬山的集卻沒有 E樂園

- **WHEN** 入庫有 `dru-x-opnh` 的集的平行語料，`kithann/E樂園-解壓/` 不存在
- **THEN** 驗證以非零狀態結束並指名 E樂園 的位置，不宣告通過

#### Scenario: 沒有萬山的集不需要 E樂園

- **WHEN** 入庫的平行語料沒有任何補充語言別的集，`kithann/E樂園-解壓/` 不存在
- **THEN** 照常逐 byte 比對

#### Scenario: 有人手改了入庫的雙語字幕

- **WHEN** 某集 `3-srt-paragraph/` 的 SRT 被人改了一個字
- **THEN** 重建驗證以非零狀態結束並指名該集

#### Scenario: 舊目錄還在就不驗

- **WHEN** Kari-SRT 裡同時有 `2-asr-whisper/2-平行語料/` 與 `2-csv-analysis/`
- **THEN** 重建驗證以非零狀態結束，指名舊目錄要移除，不宣告通過

### Requirement: 片頭辨識改語別時清掉語音側產物

片頭辨識查出節目目錄的語別標錯、改了那一集的語別時，語音側用錯的語言做出來的檔 SHALL 一併刪除等重跑：`2-asr-whisper/1-srt-sapolita/`、`2-asr-whisper/2-csv-analysis/`、`2-asr-whisper/3-srt-paragraph/`，以及 kaldi 那條的各層。跟語言無關的影像側檔（`1-ocr/` 各層）SHALL 只改名、內容不動。

族語別不變、只改語言別時（例：魯凱霧台改萬山），成果檔名不變，影像側檔 SHALL NOT 搬動；whisper 那三層與辨識紀錄那一列 SHALL 刪除等重跑；kaldi 各層用的是族語別模型，SHALL NOT 刪除。改成的語言別不屬於該族、或跟現在相同時，SHALL 拒絕且什麼都不改。

#### Scenario: 改語別後雙語字幕也刪掉

- **WHEN** 20210116_016 晚間從排灣改成卑南，改之前 `3-srt-paragraph/` 已有排灣那一集的 SRT
- **THEN** 那份 SRT 被刪除，不會以卑南的檔名留下排灣語辨識做出來的字幕

#### Scenario: 只改語言別不搬影像側

- **WHEN** 20210618_169 午間魯凱從霧台改成萬山
- **THEN** 目錄那列的語言別改萬山、語言別代號改 `dru-x-opnh`、備註記依據；`1-ocr/` 各層原地不動；whisper SRT、辨識紀錄那一列、平行語料、段落字幕都刪除

#### Scenario: 語言別不屬於該族要拒絕

- **WHEN** 把一集魯凱改成「北排灣」
- **THEN** 流程指名該集並以非零狀態結束，目錄與檔案都不變

#### Scenario: 改成一樣的語言別要拒絕

- **WHEN** 一集已經是萬山，又要改成萬山
- **THEN** 流程以非零狀態結束，whisper 結果不被白刪
