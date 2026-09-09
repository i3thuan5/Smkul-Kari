## MODIFIED Requirements

### Requirement: store 只在整批完成時定版

清除 pending 標記並定版進度表的流程 SHALL **逐集**檢查該集是否已校讀完成；
字幕版型異常集 SHALL 視為已完成，SHALL NOT 對其要求時間軸、逐字稿或 SRT。
已完成的集 SHALL 寫入，未完成的集 SHALL 跳過並指名它卡在哪一步，且
**未完成的集 SHALL NOT 阻擋其他集的寫入**。沒有任何一集完成時 SHALL NOT
視為失敗——那只代表這一批還沒有集數做完，逐集的理由已經印出。

每一集都自帶它的輸入與交付物，所以逐集寫入 SHALL NOT 使 store 產生
不自洽的狀態：進度表只列非 pending 的集，重建驗證也只走非 pending 的集，
兩者永遠指同一組集數。

#### Scenario: 未完成的集不擋已完成的集

- **WHEN** 同一批裡有些集已校讀完成、有些還沒切 cue，執行定版流程
- **THEN** 已完成的集寫入 store 並清除其 pending 標記，未完成的集原樣留著
  並印出它卡在哪一步

#### Scenario: 寫入後 store 自洽

- **WHEN** 逐集寫入之後隨即執行重建驗證
- **THEN** 驗證通過，且它驗的集數等於 inventory 內非 pending 的筆數

#### Scenario: 一集都沒完成時不算失敗

- **WHEN** 這一批沒有任何一集校讀完成，執行定版流程
- **THEN** 流程以零狀態結束、store 一個 byte 都沒動，並逐集印出卡在哪一步

#### Scenario: 字幕版型異常集不必等其他集

- **WHEN** inventory 內有字幕版型異常集，其 `1-ocr/` 底下沒有任何檔案，
  同批其他集尚未完成
- **THEN** 該集照樣寫入並清除 pending，不因其他集未完成而被擋下
