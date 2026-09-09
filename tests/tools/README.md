# tests/tools/：spec × scenario × 測試檔對照表

`tools/` 底下的東西不在交付流程上，是拿來量、拿來查的。它們跑真資料，所以**測試只守它們的算術**，用合成資料。

| 測試檔 | 守什麼 | scenario（會出錯的具體情形）|
|---|---|---|
| `test_cuescore.py` | `tools/cuescore/score.py` 的三個指標 | 相鄰但**沒有相接**的同文 cue 不算重覆（字幕離開畫面又回來是兩句真字幕）／空字串的 cue 不計入／雙列語料**兩列合起來**才是文字（只比華語列會把「華語相同、族語不同」的兩句判成同一句）／有 `--cut` 時 `repeated` 要**用時間**查交付文字（重切會重新編號，用編號查會每一次都得到零重覆，任何改動都看起來像大成功）／`swallowed` 與 `dropped` 兩個都要算（只算一個會讓賠錢的改動看起來像賺）|

跑法：

```bash
.tox/unittest/bin/python -m unittest discover -s tests/tools -t .
```
