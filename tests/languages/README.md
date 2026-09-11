# tests/languages/：族語別與語言別代號對照表

`scripts/languages.py`（頂層，兩個語料共用）的測試。規範正本是
`kithann/規範/族語及語言別名稱 - 族語名稱.csv` 與同目錄的
`- 語言別名稱.csv`，兩份都在 gitignore 的 `kithann/` 底下——換一台機器就
不見，所以程式裡要有一份跟著 repo 走的對照表。規範若改，兩邊一起改、
一起跑這組測試。

```bash
.tox/unittest/bin/python -m unittest discover -s tests/languages -t .
```

## spec × scenario × 測試檔

| spec | scenario | 測試檔 |
|---|---|---|
| episode-catalogue | 族語新聞 983 列用到的 16 種族語別全部查得到代號——缺一種就有一整族的集數填不出 `語言別代號` | `test_languages.py` |
| episode-catalogue | `族語別(中)` 與 `族語別(英)` 一對一，兩個都是六張表的共同欄位，撞名就 join 不起來 | `test_languages.py` |
| episode-catalogue | 太魯閣的代號是 `trv-x-truku`（變體代號），不可因為帶 `-x-` 就攤平成共用的 `trv` | `test_languages.py` |
| episode-catalogue | 檔名寫「德路固」的是**賽德克**底下的 `trv-x-trk`，不可混成太魯閣的 `trv-x-truku`——兩者 ISO 碼相同但是不同的語言 | `test_languages.py` |
| episode-catalogue | 查得出語言別就用語言別代號，查不出來退族語別代號；新聞 983 列只有 1 列（`魯凱語-霧台`）查得出變體，`語言別` 空是常態 | `test_languages.py` |
| episode-catalogue | 規範查無的變體字樣（`083-魯凱語-非霧台`）保留在 `語言別` 欄、代號退族語級，不可自己編一個標籤 | `test_languages.py` |
| episode-catalogue | 規範寫「霧臺」、檔名寫「霧台」——查表前要正規化，否則同一個變體查不到 | `test_languages.py` |
| episode-catalogue | 查不到的族語別要指名並列出認得的，不可留空也不可猜 | `test_languages.py` |
| aiyalaeho-text-corpus | 由 `語言別代號` 反查補齊 `族語別(英)`／`族語別(中)`／`語言別`（`ami-x-frng` → Amis／阿美／馬蘭）——句對表那 41 集只有代號 | `test_languages.py` |
| aiyalaeho-text-corpus | 族語級代號反查的 `語言別` 是空字串，不是猜一個變體 | `test_languages.py` |
| CSV 的「語言別代號」欄位 | `und` 是 ISO 639-2／639-3 對「未確定語言」的標準答案，反查得回「（未知）」，不是錯誤 | `test_languages.py` |
| CSV 的「語言別代號」欄位 | 對照表以外的代號要指名，不可默默接受 | `test_languages.py` |
| aiyalaeho-sourcing | 變體字樣自己就說得出屬於哪一族（`98-東魯凱-無字幕.mp4` 把變體寫在族語別的位置） | `test_languages.py` |
