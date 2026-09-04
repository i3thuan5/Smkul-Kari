# 把《開會了》剩下的影片全部做完並整批定版：字幕版型異常集分流到 `smkul-字幕版型異常.csv`、切 cue 前把遮罩裁到帶上

## Why

《開會了》還有影片沒做完：本機 16 集尚未視覺辨識（106、107、108、109、110、111、112、113、114、115、117、118、120、121、123、164），伺服器上三支檔（116、119、122）尚未下載，整批尚未 `publish`，總驗收沒重跑。前一個 change（`add-aiyalaeho-pipeline`）於 2026-09-03 歸檔（commit e9ccb4d）時這些都還開著，需要一個 change 把它們做完。

做完之前得先解兩件擋在前面的事。

**一、無字幕集把 `publish` 鎖死，而原設計那條路走不到。** 三集（088、090、098，檔名本身標 `-無字幕`）在原設計裡走「切出 0 條 cue → 空集合被空集合涵蓋 → 交付 0 行 SRT、不擋定版」。實測兩處都不成立：`verify_band` 對 no-band 回傳 0，與 OK 相同，批次迴圈只看離開碼，088、090 照切，攝影棚亮景讓 `band_probe` 一直觸發，切出 311／80 條布料紋理的 cue（看過 sheet，純粹是衣服）；而且即使一集真的切出 0 條，`verified.json` 只有 ingest TSV 時才寫，0 條 cue 的集數永遠沒有這個檔，`vision_complete` 回 False——實測 `cues: []` 而無 `verified.json` → False，手放一個 `{}` → True。那條 spec 在正式流程裡走不到，既有測試是靠 fixture 直接寫檔才通過。再退一步，就算走得通，`smkul.csv` 會多幾列成果檔名指向空 SRT，看表的人分不出「畫面本來沒字幕」與「我們讀失敗」。歸檔的 design D10 當初就寫「日後若出現 partial 這類註記需求，屆時再議狀態欄」；屆時已到。

**083 也屬於這一類。** 它的檔名是 `-僅華語字幕`，交付了 694 行、1,174 條華語列、**0 條族語列**（qc 記錄 `formosan_rows: 0`，SRT 內 694 個「族語：」全空）。本語料的交付品是族語文字，083 沒有——它不是雙語交付品，和無字幕三集是同一種東西。使用者裁定（2026-09-03）：**083 也列到那張表**；再裁定：**凡有異常都直接記進表、附理由，不用問要怎麼處理**，表名改為 `smkul-字幕版型異常.csv`。這個類別因此是「字幕版型異常」：凡不是這個節目的雙列雙語版型、走不了雙語交付流程的集數都算——檔名標 `無字幕`／`僅華語字幕` 的、量測判無帶或版型不符的、人工看 sheet 判異常的——理由記在表裡。

**二、切 cue 的遮罩被帶上方的畫面灌爆（A 類漏切）。** `kithann/tuiue/0903-1457.md` 量出來的：083 的帶頂沿在 region 第 48 列，preset 的族語槽卻從第 12 列起算，中間 36 列全是畫面，一格遮罩 88.3% 是白襯衫、11.7% 才是字，換句時遮罩距離只有 0.21–0.27，永遠碰不到 0.35 的門檻，於是一條 cue 跑過四句。把 region 裁到帶上重跑同一段，切點落在 532.00、534.60、537.00——**和實測換句時刻完全一樣**。`verify_band` 早就量得到帶在哪（`band_extent()`），問題是切 cue 那一步從來沒問過它；而 `rows_fit()` 只驗「找到的每一行落在某個槽」，不驗「宣告的槽底下有沒有帶」，083 因此判 `ok`。全 40 集只有 083 一集帶沒蓋滿 region，所以這是**防下次**，不是救現在：083 已離開雙語交付，不重切。使用者裁定：該筆記「五、三個接法」的 **2（切 cue 前先量帶、只裁 Segmenter 看到的遮罩、圖條不動）與 3（`verify_band` 加守門：宣告的槽底下沒有帶就不給過）併入本 change**；接法 1（給 083 專屬 preset）不做。B 類（短騎線 cue、`min_stable` 抖動）另案（12.4b）。

Kari-SRT／tests／scripts 三層的改動已在 2026-09-03 的 explore 逐層攤開並經確認。

## What Changes

- **字幕版型異常集分流**（新行為）：
  - inventory 新增「理由」與「影片長度」兩欄，**追加在既有欄位之後**（欄位清單封閉且順序有意義）。理由非空＝異常集（以下說「有旗標」就是這個意思），空＝雙語集照常。
  - 理由怎麼來，三條路，**都不問使用者**：(1) 登記時從檔名的字幕狀態字樣推導——`無字幕`、`僅華語字幕` 照錄（`catalogue` 已解析到這個 token、目前丟棄）；(2) 切 cue 前 `verify_band` 量到無帶 → 記 `無字幕`；量到版型不符 → 先換低版 preset 再量一次（087／094 就是這樣救回來的），仍不符 → 記 `版型不符：<量測指名的問題>`；(3) 切完人工看 sheet_001 判異常 → 記 `人工判定：<一句話>`。no-band 從此不再與 OK 共用「可以切」的離開碼。
  - 有旗標的集數：不切 cue（已切的不讀）、不派讀者、不組裝、不進 `smkul.csv`、**不擋 `publish`**。
  - 批次結束時的報告逐集列出異常集的理由，並標出哪幾集是量測或人工判定、不是檔名標的，讓人最後看一眼。
  - 另產 `Kari-SRT/aiyalaeho/smkul-字幕版型異常.csv`：`smkul.csv` 的九欄原樣、同順序，**再加一欄「理由」**（值就是 inventory 的理由）；成果檔名欄放該集的 `srt_name`（那是鍵，不對應任何檔案）。工作區另有隨時可刷新的快取版本。
  - 影片長度：由登記工具以 ffprobe 取得、寫入 inventory（工具寫、不手填），表由 inventory 重建。`1-ocr/` 底下不為這些集放時間軸、SRT 或 TSV。
  - **083 自雙語交付撤回**：其 `1-ocr/` 下 19 個已 commit 的檔（17 個 TSV、SRT、qc）自工作樹刪除（Claude Code 刪檔，使用者最後 `git add` 收入）；083 在 `kithann/` 的工作目錄與 README 記載的漏切實例保留（那是 12.4b 的證據，仍然成立）。
  - `rebuild --verify` 逐 byte 涵蓋**兩張表**。
- **切 cue 前把遮罩裁到帶上**（接法 2）：遮罩規格新增「帶所在的列範圍」，切 cue 時只比較帶內的列，帶外的畫素不參與切點判斷（讀者照樣看到整條圖條，視覺辨識不受影響）；切 cue 與事後精修都經同一個遮罩規格，所以兩者自動一致；**圖條（strips）與 contact sheet 完全不動**——讀者看到的東西和現在一樣。列範圍由 `verify_band` 量出、寫進工作目錄，切 cue 時讀入並記進 `cues.json` 的 `mask`（重建時原樣帶著）。帶蓋滿 region 的集數（40 集裡 37 集）行為不變。
- **`verify_band` 加守門**（接法 3）：帶存在時，preset 宣告的每一個槽都 SHALL 落在量到的帶上；任一槽底下沒有帶 → `mismatch`，指名該槽與帶的範圍，不給切；批次流程把它連理由記進異常表。這補的正是 083 當初漏過去的缺口。
- **BREAKING（僅 spec 層）**：
  - `aiyalaeho-sourcing`「有影片就做」自「SHALL NOT 依檔名的字幕狀態字樣預先排除或分流」改為**字幕版型異常集 SHALL 依檔名分流**（混雜集仍照常處理）。
  - `srt-data-store`「0-cue 集數照交付且不擋定版」**移除**——它在正式流程走不到，且被分流取代。`vision_complete` 對空集合成立的語意保留（編號集合比對的自然結果），但不再是任何交付路徑所依賴的東西。
  - `cue-timing`「切 cue 前驗證雙列字幕帶位置」加「宣告的槽須落在帶上」；新增「切 cue 前先量帶、遮罩裁到帶上、圖條不裁」。
- **文件修正**：`scripts/aiyalaeho/README.md` 三集判定表把 098 記成 NO-BAND，log 為 MISMATCH——改正；素材分類把 083 自「干焦華語 1 集」移到字幕版型異常組；SOP 加上「切 cue 前先看旗標、再量帶」。
- **把剩下的影片全部做完並整批定版**：
  - 本機 16 集（106、107、108、109、110、111、112、113、114、115、117、118、120、121、123、164）**已經切好、精修過**（40 集的 `cues.json` 都有 `refined`），不重切——它們的帶都蓋滿 region，裁不裁遮罩結果相同。只補跑 `verify_band --band-json` 讓新守門過一遍：判 mismatch 或 no-band 的才依新 SOP 處理（重切加 `--band-rows`，或分類進另表）。之後派讀者視覺辨識、`ingest`、`make_all`，以 `/loop 20m` 推進。108／111 是華語重的雙語集，派工時要提醒讀者頂列夾漢字整行進 `formosan`。
  - 伺服器三支（`116ALL_無字`、`119-混雜`、`122-混雜`）用 `scripts/news/sftp.sh get` 下載、比位元組數；人看過影片後以 `--language` 指定族語別登記。116 登記時即為第五筆異常集；119／122 依 SOP 過 `verify_band`（不符先換低版 preset），通過才切，切完人工看 sheet_001——任何一關判異常就直接記進異常表附理由，不硬切、不問使用者。
  - 全部讀完：`make_all` → `publish`（報告點名量測分類者）→ `rebuild --verify`（兩張表逐 byte）→ 總驗收（`tox -e unittest`、`tox -e flake8`、news 的 `rebuild --verify` 與 `name_catalogue --check`）。
  - 做完的定義：`smkul.csv` 含全部雙語集、`smkul-字幕版型異常.csv` 含全部字幕版型異常集，兩張表列數相加＝inventory 筆數，inventory 內不再有 pending。
- **不含**：12.4b 的 B 類補救（要借 news 的 `reread`／`resplit`／`rescan_band`，另開 change）；單列版型當第一級公民（083 已離開，唯一的單列集不存在了）；108／111 標「講中文居多」但兩集都標雙語、有族語列，不屬此類，照常讀。
- **順帶**：`openspec/changes/half-res-mask-and-slot-crop/` 只有 `.openspec.yaml`、無任何 artifact，題目正是接法 2 的 slot crop，已由本 change 承接——建議刪除該空目錄（Claude Code 刪，使用者最後 `git add`）。

## Capabilities

### New Capabilities

（無——三件都是既有能力的規則改動。）

### Modified Capabilities

- `aiyalaeho-sourcing`：「有影片就做」改寫為字幕版型異常集分流；新增「異常理由由檔名、量測、人工判定三路寫入，不擋批次、批次結束時報告」與「登記時記錄影片長度」。
- `srt-data-store`：aiyalaeho store 結構加 `smkul-字幕版型異常.csv`；「aiyalaeho 僅靠已 commit 的資料可離線重建」及於兩張表；「aiyalaeho 進度表」加字幕版型異常集不列、另表九欄加理由欄、影片長度來源；「store 只在整批完成時定版」不把字幕版型異常集當未完成；「批次進行中的集數以 pending 標記」補上第四種標記的語意區分；**移除**「0-cue 集數照交付且不擋定版」。
- `cue-timing`：「切 cue 前驗證雙列字幕帶位置」加宣告槽須落在帶上；新增「切 cue 的遮罩裁到量得的帶上，圖條不裁」。

## Impact

**修改（程式）**

```
scripts/ocr/                      共用引擎（news 照舊不傳帶範圍，行為不變）
├── cuelib.py       MaskSpec 加 band_rows（region 內的列範圍，可省略）；text_mask 只在該範圍內找字；to_dict／from_dict 帶著它
└── cli.py          cues 加 --band-rows LO,HI（絕對列，轉成 region 內偏移寫進 spec）

scripts/aiyalaeho/
├── paths.py        INVENTORY_FIELDS 追加理由與影片長度（尾端）；smkul-字幕版型異常.csv 的 store／快取路徑常數；工作目錄內帶範圍檔的路徑
├── catalogue.py    parse()：字幕狀態 token（無字幕、僅華語字幕）→ 理由；登記時 ffprobe 長度（借既有 probe，不另寫）；--annotate 補既有條目、也收批次迴圈的自動分類（<srt_name>=<理由>）
├── verify_band.py  帶存在時檢查每個宣告槽落在帶上，否則 mismatch；no-band 離開碼改為非零；--band-json 把量到的帶範圍寫進工作目錄
├── tracker.py      is_abnormal()；tracker_rows() 排除有旗標者；abnormal_rows() 多帶理由欄；影片長度對有旗標者改讀 inventory
├── make_all.py     make_one() 對有旗標者回「字幕版型異常」不組裝；同時刷新第二張表的快取版
├── publish.py      gate／publishable 對有旗標者不問 vision_complete；定版時寫第二張表
├── rebuild.py      check_inputs 對有旗標者不要求輸入；verify 比對兩張表
└── README.md       判定表修正；素材分類；SOP：旗標→verify_band（--band-json）→cues（--band-rows）→refine；兩張表的說明
```

**修改（測試，先紅後綠）**

```
tests/ocr/                 text_mask 在 band_rows 外一律 False；band_rows 省略時行為不變；from_dict／to_dict 來回
tests/aiyalaeho/
├── test_paths.py          新欄位宣告與順序；帶範圍檔路徑
├── test_catalogue.py      無字幕／僅華語字幕 → 理由；雙語字幕 → 空；長度由 ffprobe（mock）；--annotate 指名寫入任意非空理由、不覆蓋既有
├── test_verify_band.py    帶只蓋 region 下半（083：y924..1014）而槽宣告在上面 → mismatch 並指名；帶蓋滿 → 既有案例全部照舊；no-band 離開碼非零
├── test_tracker.py        有旗標者不在 smkul.csv、在 smkul-字幕版型異常.csv、九欄同再加理由欄；長度取自 inventory
├── test_publish.py        有旗標者不擋 publish、不組裝；既有兩個 no_subtitle 測試改寫；test_an_episode_with_no_cues_is_complete 保留
└── test_rebuild.py        有旗標者免輸入；兩張表逐 byte；既有 no_subtitles 測試改寫
```

**修改（資料，Kari-SRT）**

```
Kari-SRT/aiyalaeho/
├── inventory.json                 083／088／090／098 四筆加旗標與長度（116 下載後為第五筆）——程式寫
├── smkul.csv                      定版時不含字幕版型異常集——程式寫
├── smkul-字幕版型異常.csv               新檔，定版時寫入——程式寫
└── 1-ocr/{2-vision/開會了_083_Rukai_魯凱/, 3-srt/開會了_083_Rukai_魯凱.*}   自工作樹刪除——Claude Code rm，使用者 git add
```

`1-ocr/` 不為字幕版型異常集新增任何檔案。088／090 工作區內那兩份雜訊 `cues.json` 與 083 的工作目錄在 `kithann/out/`（快取、gitignore），不進 store，可留。

**修改（文件）**：`tests/README.md`（spec × scenario 表：cue-timing 一列加守門與遮罩裁帶；srt-data-store 加兩張表）、`Kari-SRT/README.md`（樹）、`Kari-SRT/aiyalaeho/1-ocr/README.md`（重建及於兩張表）、`scripts/README.md`（ocr 引擎新參數）。

**依賴**：無新套件。`ffprobe` 已在用。

**驗收**：`tox -e unittest`（ocr、aiyalaeho 兩組）、`tox -e flake8`；aiyalaeho 的 `rebuild --verify` 兩張表逐 byte；news 的 `rebuild --verify` 與 `name_catalogue --check` 照樣通過（news 未被動到的證明——news 的 preset 不傳帶範圍，`text_mask` 行為必須一模一樣）；整批 `publish` 後 `smkul.csv` 含全部雙語集、`smkul-字幕版型異常.csv` 含全部異常集且每列有理由，兩張表列數相加＝inventory 筆數；對 083 母帶跑 `verify_band` 得 mismatch 並指名族語槽底下無帶（守門的活體驗證）。
