## ADDED Requirements

### Requirement: 伺服器連線斷掉要在數分鐘內發現

所有對伺服器的 SFTP 動作 SHALL 在連線建立後持續確認伺服器仍有回應；伺服器連續約 2 分鐘沒有回應時，該次動作 SHALL 以失敗結束，SHALL NOT 無限期等待。傳輸慢但伺服器仍有回應時，SHALL NOT 因此中斷。

不設定時，連線斷掉要等系統 TCP keepalive 約 2 小時 11 分（7200 秒後開始、每 75 秒一次、9 次）才發現；連續跑十幾天的批次會在無人看管下停住。

#### Scenario: 每一次 SFTP 動作都帶斷線偵測

- **WHEN** 以任何動作（get、put、ls、mkdir、rename、rmdir、批次）呼叫伺服器
- **THEN** 送出的 sftp 指令帶有每 30 秒確認一次、連續 4 次沒回應就斷線的設定

#### Scenario: 伺服器消失

- **WHEN** 下載進行中，伺服器網路中斷且不再回應
- **THEN** 該次下載在約 2 分鐘內以失敗結束，呼叫端收到非零離開碼
