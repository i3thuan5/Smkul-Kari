## ADDED Requirements

### Requirement: 開會了交付 SRT 為雙列

aiyalaeho 語料的每條交付字幕 SHALL 恆為兩行、各帶語別標籤：第一行
「族語：」接族語列文字、第二行「華語：」接華語列文字（與語音側
`3-srt-raw` 的款式一致），兩行的文字皆來自畫面上的燒印字幕（依既有要求，
經人校讀的視覺辨識才可供字）。某列該 cue 無字幕時，該行 SHALL 仍輸出
（標籤後留空），SHALL NOT 整行省略——讀的人才分得出「這列沒有字幕」與
「漏了一行」。兩列皆空的 cue SHALL NOT 出現在交付 SRT。相鄰同文合併
SHALL 以兩行合成後的整體文字比對，SHALL NOT 只比其中一行。

#### Scenario: 雙列條目

- **WHEN** 某 cue 族語列與華語列皆有校讀文字
- **THEN** 交付 SRT 該條為兩行：「族語：〈族語文字〉」「華語：〈華語文字〉」

#### Scenario: 族語列空白仍保留標籤行

- **WHEN** 某 cue 畫面只有華語字幕（例如受訪者講華語的段落、僅華語字幕的
  集數）
- **THEN** 該條第一行恰為「族語：」（標籤後空白）、第二行為華語行，
  SHALL NOT 省略族語行

#### Scenario: 同文合併比對合成文字

- **WHEN** 相鄰兩 cue 的族語行相同而華語行不同
- **THEN** 兩條不合併——合併判準是兩行合成後的整體文字相等

### Requirement: 族語列忠於畫面

族語列的文字 SHALL 逐字忠於畫面：畫面夾漢字即照錄漢字（例
`qau aicu a 民族議會 mana…`），SHALL NOT 以「非拉丁字」為由過濾或改寫；
正字法符號（`^`、`'`、`"`、`:`、`ʉ` 等）SHALL 照畫面保留，SHALL NOT 相互
正規化——`'`（一撇）與 `"`（兩撇）是不同符號。

#### Scenario: 夾漢字照錄

- **WHEN** 族語列畫面為 `ungat mais isian kalingku hai pansia 卓溪鄉 tu 太平`
- **THEN** 校讀文字逐字相同，漢字保留

#### Scenario: 一撇與兩撇不互換

- **WHEN** 畫面上同一集內同時出現帶 `'` 與帶 `"` 的詞
- **THEN** 兩種符號各自照錄，SHALL NOT 統一成其中一種
