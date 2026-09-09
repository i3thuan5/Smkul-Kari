# cuescore：一次切割是變好還是變壞

```bash
python3 -m tools.cuescore.score TIMELINE VISION_DIR [--cut OTHER]
```

`TIMELINE` 是一份 `cues.json`（store 的 `news/1-ocr/1-cues/<srt_name>.json` 就可以），`VISION_DIR` 是那一集的 `b*.tsv` 所在目錄。**不解任何一格影片**，所以算一個月只要幾秒。

## 為什麼要有這支

切 cue 的每一個參數都是在幾種損失之間換，而三種損失裡有兩種在交付的 SRT 上完全看不出來。實測過：把切換門檻拉高可以少讀一些重覆，但吞掉真字幕的速度差不多一樣快；把比對遮罩縮到字幕實際落點，重覆降 44–69% 而且吞句同時降——這件事只有把三個數字一起看才知道。

`rebuild --verify` 看不到這些：它是從 store 的時間軸與 TSV 離線重建 SRT，從頭到尾不碰遮罩，所以切割壞掉它也不會紅。

## 三個數字

| 名稱 | 意思 | 代價 |
|---|---|---|
| `repeated` | 相鄰、時間相接、文字相同的 cue 對 | 同一句被切成好幾塊，每一塊 Claude Vision 都要再讀一次 |
| `swallowed` | 交付文字有換句，但被 scored 那一份的某一條 cue 整個跨過去 | **少一句字幕** |
| `dropped` | 交付裡有字的 cue，scored 那一份完全沒有涵蓋 | **少一句字幕** |

`repeated` 只要時間軸與 TSV 就算得出來。`swallowed` 與 `dropped` 是拿另一份切割去比交付的那一份，所以要 `--cut`。

## 數字怎麼讀

- **`swallowed` 和 `dropped` 要一起看。** 它們是同一種代價的兩個形狀，只看一個會讓賠錢的改動看起來像賺。
- **`repeated` 降、另外兩個沒升**，才是真的變好。只有 `repeated` 降的話，多半是把字幕吞掉了。
- 有 `--cut` 的時候，`repeated` 是**用時間**去查交付文字的——重切會把每一條 cue 重新編號，新時間軸的編號對那些 TSV 完全沒有意義。

## 為什麼放在 `tools/` 不放 `tests/`

它吃真資料（真的時間軸、真的 TSV），不符合「測試要離線、資料用 fixture 合成」那條規定。定位比照 `tools/measure/`、`tools/mxf2mkv/`。它自己的算術由 `tests/tools/test_cuescore.py` 用合成資料守著。
