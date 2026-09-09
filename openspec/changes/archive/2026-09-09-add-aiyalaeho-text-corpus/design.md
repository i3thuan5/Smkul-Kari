## Context

動機見 proposal.md 的〈Why〉。這裡只記做法需要的現況與限制。

來源在 SFTP：`/docker/ilrdf-corpus/族語節目/開會了_a_iyalaeho=上字文稿/`，43 個子目錄（集號 001–045，實際 41 集，缺 039、040、042、043），243 個檔、9.2 MB。逐檔盤點過，量到的性質：

| 面向 | 實際情形 |
|---|---|
| 純文字編碼 | UTF-16（有 BOM）58 檔、Big5 46 檔、UTF-8（有 BOM）2 檔 |
| 文書檔格式 | OOXML docx 127 檔、**OLE2 doc 2 檔** |
| 排版型 | 同行雙語 162、時碼＋同行雙語 25、隔行雙語 30、短片段 11 |
| 規模 | 61,301 個非空行 → 約 5.5 萬列句對 |
| 撇號 | docx：彎撇 15,411／ASCII 11,459；txt：彎撇 5,042／ASCII 17,157 |
| 時間碼 | 25 個檔（分佈在 004、008、028、031、032、033、041、044 共 8 集），逆序只有 1 處 |
| CSV 殺手 | 含 TAB 的行 2,238、含半形逗號 65、含半形雙引號 20 |
| 多重分隔符 | 158 行（占 43,882 個雙語行的 0.36%） |
| 語言別代號 | 41 個目錄名稱裡，40 個含既有規範表裡的族語別或語言別用字，可直接比對出唯一代號；1 個（`開會036-東布青`）目錄名稱查不到，但轉出的文字裡有「itu Bunun tuza tu maza madadaingaz…」——是布農語 |

三個限制決定了架構：

- **上游不在 repo**。9.2 MB 全在 SFTP，主 repo 與 Kari-SRT 都不存原檔，所以交付的 CSV **離線重建不出來**，重跑就是重下載。這和影像側 `rebuild --verify` 的保證不同級。
- **那 41 集沒有影片**，而且集號與手上的 44 支 mp4（068–164）零重疊。`inventory.json` 是檔名驅動的（每筆都要有 `file` 指向 mp4），這批進不去，也不該進。
- **9.2 MB 沒有硬碟壓力**。`scripts/news/fetch_sftp.sh` 那套「逐檔下載、用完即刪、可續跑」是為 2.3 TB／1,065 檔設計的；這裡整批塞進記憶體都行，不需要暫存管理。

## Goals / Non-Goals

**Goals:**

- 一支指令從 SFTP 取檔，一支指令產出交付 CSV。
- 四種排版型都解得開，包含只有隔行雙語格式的六整集（001、002、003、005、006、007）。
- 判不準的行**標記**而不是猜——下游能篩、人能複核。
- 不新增任何 Python 套件。

**Non-Goals:**

- 不產 SRT。8 集有時間碼，但每個「段」的時間碼各自從 0 起算（例如開會031 三段分別是 6.3→1472s、7.4→1009s、6.3→845s，合計 55 分而一集只有約 48 分），那是每卷帶自己的時間軸、不是節目時間軸；沒有影片就對不出段在節目裡的起點。
- 不挑正本、不去重。逐檔照收是使用者裁定。
- 不做 `--check`、不留 UTF-8 鏡像。
- 不碰 `/docker/ilrdf-corpus/族語新聞/110年2月_族語新聞文稿`（RTF、逐則新聞一個檔），那批由另一條 session 處理。

## Decisions

### 一、副檔名決定 parser，不嗅探內容；解不開就中止

盤點初期把開會029 那兩個 `.doc` 判成壞檔，理由寫「zip 裡沒有 `word/document.xml`」。那是錯的：它們是**正常的 Word 97-2003 檔**（OLE2 複合檔，魔術數 `D0 CF 11 E0 A1 B1 1A E1`），LibreOffice 開得起來。

**但錯因不是「信了副檔名」，剛好相反。** 會誤判是因為當時拿 `zipfile.is_zipfile()` 當分派器、而且根本沒有 `.doc` 這條分支：Word 把佈景主題當成一小段 zip 放在 OLE 檔尾，`is_zipfile()` 在檔尾找到 EOCD 就回報「是 zip」，接著去那個只有 5 筆（全是 theme）的目錄裡找 `word/document.xml`，當然找不到。

掃過全部 129 個 doc/docx，**副檔名與內容 100% 一致**（2 個 `.doc` 都是 OLE2、127 個 `.docx` 都是 zip）。所以副檔名本來就分得開，是分派器選錯了東西。

**做法**：副檔名決定用哪個 parser（`.doc`→OLE2、`.docx`→OOXML、`.txt`→純文字），**不做任何內容嗅探**。純文字的編碼副檔名管不到，仍由 BOM 決定。

**也不留魔術數當守門。** 曾經想過「副檔名選 parser、魔術數比對驗證」，但那是多一個會壞的零件、換不到東西：如果副檔名和內容真的不合，parser 自己就會失敗——OLE2 的 header 讀不出來、`zipfile` 開不起來——那個失敗訊息就是最準確的診斷。事先比對只是換一個地方講同一件事，還得自己維護一張魔術數表。

**規則是：解不開就中止並指名，不吞掉也不換方式重試。** 這順帶取消了原本設計的 `類型=轉檔失敗` 那一列——「記一列然後繼續」和「有問題就中止」是相反的做法，不能並存。取中止的理由：`pairs.py` 是一次跑完 243 個檔的批次，半份 CSV 比沒有 CSV 更危險（下游看不出少了什麼）；這和影像側「整批拒收」、`judge.py`「整批接受或整批拒收」是同一條規矩。

**否決 `zipfile.is_zipfile()` 分派**：它對 OLE2 說謊，這是已經踩過一次的坑。

**替代方案與否決理由：**

- 裝 `olefile`／`antiword`／`catdoc`：為 2 個檔加依賴，還要走〈外部服務與套件的採購規定〉那一輪稽核。CLAUDE.md 寫「裝得越少越好」。
- 用 LibreOffice 手動轉成 docx 放回 SFTP：會在「從 SFTP 重下載就能重跑」上開一個洞——下次有人重跑，那兩個檔又變回 `.doc`。
- **選：自己讀。** 已驗證可行：走 OLE2 的 FAT／miniFAT／目錄取 `WordDocument` 與 `1Table` 兩個串流，再照 Word97 的分片表（CLX／PlcPcd）解出正文，兩個檔各得 356 行與 199 行，格式標準（`族語//華語`），泰雅語與華語都對。純標準函式庫。

### 二、時間碼原樣存字串

25 個時碼檔混用 drop-frame（`;FF`，多數）與 non-drop（`:FF`，開會004）。29.97 的換算差多少、片頭有沒有偏移，**沒有影片就驗不了**。存原樣是誠實的；現在換算等於先寫死一個沒人驗過的數字，日後影片到了還要回頭改。

**時碼格式比一開始設想的更雜，是實作階段才發現的，修了兩次：**

- **只有一個時碼、沒有結束時間**（開會031 三個檔、開會032 兩個檔，整份都是這個格式）。第一版只認 `開始 結束 內容` 的兩時碼格式，這些檔完全對不上，時碼字串直接黏進族語欄——跑一次全語料才看到 1,130 列受影響，不是讀規格文件想得到的。加了單時碼格式的判斷（抓不到兩時碼才試一時碼），`結束時間` 留空。
- **時碼抽出來、但內容判不出類型時，不可以拿回帶時碼的原始行重判。** 加了單時碼支援後還剩 324 列出錯，追下去發現是同一類問題的另一面：`_classify_content` 對「有時碼、但內容既沒有分隔符也不像註記」的行（例如開會004 一整段逐行帶時碼的純華語旁白）回傳 `None`，外層本來的寫法是「判不出來就退回用原始的 `line`」去判斷隔行配對或落單——但原始 `line` 還帶著時碼字串，時碼就這樣重新混進族語或華語欄。**修法是把時碼抽取從「同行雙語」那個分支獨立出來，一開始、對所有分支都先做一次**（`_extract_timecode`），之後不管內容判成同行雙語、隔行配對的一半、還是落單的單語，都是拿抽乾淨的 `content` 去判、時碼原樣帶著走，不會有「回頭用原始行」這條退路。
- **有時碼、後面沒有文字的行**（該窗口沒有話要說，例如開會044 兩個時碼中間只有空白）：這是製作事實，不是漏譯，歸 `註記`，不是 `混合`。

三個問題都是**跑過全語料才現形的**，資料量小的樣本測不出來——這也是為什麼 `Kari-SRT/aiyalaeho/text/README.md` 的時碼集數／檔數要用實際跑出來的數字（8 集、25 個來源檔），不能用還沒發現這些坑之前的推算。

### 三、多重分隔符切最後一個，並且標記

158 行有兩個以上分隔符，是四種不同的病：

```
① 分隔符打兩次      maelranenga////謝謝
② 開頭就是分隔符    //mina nakhini honaehnge: ila//距離上次我們的討論也有一段時間了
③ 族語裡面自己有    imi ni ga pagluw ta//kumaal ci yogi na alang//"聚在一起討論重要事務"的意思
④ 兩條 cue 黏成一行  na semalji a'en uta//我也很好奇uri 'ivadaq a'en ta aicu ti ina audra ui//想問問秋梅長老
                    └─ 族語1 ─┘└華語1┘└──── 族語2 ────┘└── 華語2 ──┘
```

切最後一個對 ①②③ 都正確，對 ④ 錯（族語會吃到華語1）。**④ 沒辦法用規則判斷**——要知道 `uri 'ivadaq a'en ta aicu ti ina audra ui` 是新的一句族語而不是前一句華語的一部分，得讀得懂那是什麼語言。

**逐行核對過 158 行（去重後 135 筆唯一內容），④ 型有 4 行是真的兩句字幕黏死**（其餘要嘛是③、要嘛是①②，規則切割本來就對，或只是差在殘留的分隔符）：

```
開會022 line 5   nanu mha nanu...knwal//那是什麼樣的機緣什麼時baqun ta ciwal...balay//三位來賓都是致力於
開會026 line 59  o mato'asayto...sa'osi//就是法定的原住民老人sanaw...aniniay//從55到64歲的年齡就有原住民給付這件事
開會011 line 8   na semalji a'en uta//我也很好奇uri 'ivadaq...audra ui//想問問秋梅長老
開會044 line 140 mai paapuq nazau satatawikan na metiyu//祭品中的檳榔是不加灰的temawik ta ni temayta ti metiyu//祭師透過占卜能力
```

這四行規則切割不是切錯邊界那麼簡單——後一句的族語文字整段被吃進前一句的華語欄，**一組（族語,華語）根本放不下兩句話**。判法是找族語段落裡有沒有夾著一句**完整的華語子句**（有主詞、有動詞、讀起來自己就是一句話），不是隨便一個 3 字以上的漢字詞就算——同樣含漢字詞的候選（開會020 line 12 的 `【'a'iyalaeho:】親愛村`、開會021／開會017 裡一堆「黑膠唱片」「鈴鈴唱片公司」「南信彥」這類專有名詞）逐一查過，那些是族語句子中間夾雜的借詞或專有名詞，不是完整子句，規則切割本來就對，不必動它——這條界線（借詞／專有名詞 vs. 完整子句）比原先設想的還要細，值得記下來。

**使用者裁定：切法表允許一行對出兩列，不加序號欄。** `多重分隔符切法.csv` 欄位不變（`來源檔,原句,族語,華語`），一行真的是兩句字幕黏成一行時，同一個 `來源檔`＋`原句` 底下就出現兩列，順序就是寫進檔案的順序，不必另外標。`parse.py` 的 `split_table` 因此從「內容 → 一組 (族語,華語)」改成「內容 → 一或多組 (族語,華語) 的清單」；查到清單長度 1 的維持原樣（155/158 是這樣），長度 2 的輸出兩列，兩列的 `行號` 相同（都指向同一個原始行）、`類型` 都是 `雙語（多重分隔符，AI切割）`。

所以這 158 行交給 **Claude（opus）判讀**，`類型` 標 `雙語（多重分隔符，AI切割）`。

做法照 `scripts/asrmt/judge.py` 已經立好的規矩，不另發明：

- **提示詞就是定義**（`split_prompt.md`），改了提示詞就是換了問題，版本要跟著跳。
- **Claude 的產出以檔案交回**，程式驗證後匯入——這個 repo 不從 Python 打 API，視覺辨識與品質判定都是這個流程。
- **整批接受或整批拒收**：回覆的項目集合與工作表不符，或某個切法不是原句的合法切分（把兩半接回來不等於原句），整批退掉、一列都不寫。半批接受會把切法安到別的句子上，下游看不出來。
- **鍵是內容不是行號**。`judge.py` 的註解記著這個教訓：重投影一次時間軸就整批重編號，試作集的第 304 條變成 309 條，用編號當鍵會把昨天的判斷悄悄接到別的句子上。這裡同理——來源檔重下載後行號可能位移，但文字沒變就該沿用。

結果存成 `Kari-SRT/aiyalaeho/text/多重分隔符切法.csv`（來源檔、原句、切出來的族語與華語），158 列，人打開就能逐列複核。這是**不可重生的過程資料**，該進 Kari-SRT；有它在，`pairs.py` 這一步就仍然是離線且確定的。

切法表查無的行，退回「切最後一個」並標 `雙語（多重分隔符，規則切割）`。**兩種來歷都寫在 `類型` 上**——不留一個看不出來歷的 `雙語（多重分隔符）`，那種值日後沒人知道是模型切的還是規則切的。

**「AI切割」的意思要在 store README 寫明**：哪一個模型、哪一版提示詞、有沒有經人複核。`judge.py` 立過同樣的規矩——「高」的精確度靠兩個模型互相同意而不是靠人核對，這件事寫在 store 的 README 裡而不是含糊帶過。這裡同理：這 158 列的信心和其他 43,724 列不同級，讀的人有權知道。

**檔名不編號**：`text/` 底下 `1-句對.csv` 是流程階段，切法表是輔助表，比照 `aiyalaeho/` 層的 `inventory.json`、`smkul.csv` 不編號。

### 四、隔行落單不往下硬配

隔行雙語 30 個檔共 13,302 行，用「羅馬字行 → 漢字行」配對得 6,203 對，涵蓋率 93.3%，落單 664 羅／232 漢。

落單不是配對失敗。`開會021_卑南族歌謠/21_第3段.docx` 落單 107 個羅馬字行，那是**歌謠襯字**（`hoiyanahiyuin ho~yanahiyaoyan~nahiyaohayyan`），本來就沒有華語譯文。跳過中間的行去抓下一個漢字行來配，會把不相干的兩句黏在一起。

### 五、交付格式選 CSV，不選 TSV

`1-ocr/2-vision/` 用 TSV，但這批資料有 **2,238 行含 TAB**（Word 的定位字元），TSV 會被咬爛。CSV 加標準跳脫可以吃下逗號（65 行）與雙引號（20 行），寫入時 MUST 用標準 `csv` 模組，不可自己串字串。TAB 在寫入前換成半形空白——那些定位不帶語意，留著只會讓欄位看起來有洞。

### 六、`oledoc.py` 留在 `text/` 底下，不上移到共用層

它是通用格式讀取器，看起來該共用，但目前只有一個使用者，而且新聞那批文稿是 RTF、用不到它。照「裝得越少越好」，等真的有第二個使用者再搬。

### 七、下載用 shell，路徑常數進既有的 `paths.py`

`scripts/news/` 的慣例是下載交給 bash（`fetch_sftp.sh` 迴圈呼叫 `sftp.sh get`），Python 只管邏輯。`sftp.sh get` 沒有遞迴（只寫 `get "遠端" "本地"`），所以仍需一支小迴圈腳本，但因為沒有硬碟壓力，不需要續跑與刪檔那套。

路徑常數加進既有的 `scripts/aiyalaeho/paths.py`，不另開 `text/paths.py`——一個語料一份路徑正本是現有慣例。

### 八、語言別代號：重用 `catalogue.py` 的表，不另造一份

`inventory.json`（影像側）已經有一份逐集的語言標記，程式裡對應著
`scripts/aiyalaeho/catalogue.py` 的 `LANGUAGES`（族語別 → 英文拼法、
ISO 639 代號）與 `VARIETIES`（族語別 → {語言別用字: 代號}），兩者都是
照 `kithann/規範/族語及語言別名稱 - *名稱.csv` 抄過來、換機器不會不見
的正本。這批上字文稿要標語言，答案不是重新讀一次規範 CSV 造第二份表，
是直接呼叫這兩個既有的字典。

**做法**：把 41 個集的目錄名稱拿去跟 `VARIETIES` 的每個語言別用字比對
子字串，中的話用那個語言別代號；沒中就拿去跟 `LANGUAGES` 的族語別比對，
中的話用族語別代號。這個規則就是「有確定語言別就用語言別，不知道就用
族語別」的字面翻譯，而且**不用手key 一張 41 列的表**——已驗證這樣可以
乾淨解出 40 個集，沒有任何一集撞出兩個不同的代號。

**唯一的例外，一個明確的覆寫**：`開會036-東布青`的目錄名稱查不到任何
族語別或語言別用字（「東布青」三個字都不在任一個規範用詞裡）。轉出來
的文字給了答案——`itu Bunun tuza tu maza madadaingaz a makuuni maia
maivahvah tu tuhna tan`（布農族耆老拿著獸骨秉告祖靈），逐字唸出
「Bunun」，加上其餘語句用了 `uninang`（謝謝，跟 007 布農集同一個詞）、
`is-` 開頭的氏族名（`isMahasan`、`isTanda`，布農氏族名的慣用前綴）。
所以覆寫成布農語（`bnn`），並在程式裡留一行註解記這個判斷的依據，不是
憑空猜的。

**否決「幫全部 41 集手工建一張表」**：那等於重造一份規範表的複本，
`kithann/規範/` 改了、`catalogue.py` 改了，這裡永遠不會跟著動；而且
40/41 用重用的表就自動解得出來，值得手工處理的只有 1 個。

**沒有任何一集查不出來時的行為**：中止並指名是哪一集，不寫入 `語言別
代號` 留空或編造代號的一列——理由跟解碼那一節的「解不開就中止」一樣：
半份 CSV 比沒有 CSV 更危險。

## 檔案樹與輸出入對應

```
scripts/aiyalaeho/
├── paths.py                     【改】加 TEXT_STORE／TEXT_PAIRS／TEXT_WORK／TEXT_REMOTE
└── text/                        【新】
    ├── __init__.py
    ├── fetch.sh                 吃：SFTP 遠端路徑    產：kithann 暫存的 243 個原檔
    ├── oledoc.py                吃：.doc 的 bytes    產：正文字串
    ├── decode.py                吃：來源檔路徑        產：(UTF-8 文字, 格式標記)；.doc 轉呼叫 oledoc
    ├── lang.py                  吃：來源目錄名稱      產：語言別代號（重用 catalogue.LANGUAGES／VARIETIES）
    ├── parse.py                 吃：一個檔的文字      產：列的串列 (行號,類型,族語,華語,開始,結束)
    ├── split_prompt.md          多重分隔符怎麼切的定義；改它就要跳版本
    ├── split.py                 吃：解析出的多重分隔符行／Claude 的回覆
    │                            產：工作表；驗證後寫入 多重分隔符切法.csv
    └── pairs.py                 吃：暫存目錄＋多重分隔符切法.csv  產：1-句對.csv（CLI 進入點）

tests/aiyalaeho/
├── test_paths.py                【改】「store 版面」那條 scenario 擴充到 text/
└── text/                        【新】
    ├── __init__.py
    ├── README.md                本文件下面那張 spec × scenario × 測試檔對照表
    ├── test_oledoc.py           fixture 程式化組出最小 OLE2＋Word97 檔
    ├── test_decode.py
    ├── test_lang.py
    ├── test_parse.py
    ├── test_split.py
    └── test_pairs.py

tests/README.md                  【改】加一行指到 tests/aiyalaeho/text/README.md

kithann/out/aiyalaeho-text/      暫存，gitignore，隨時可重下載重跑
└── 上字文稿/                    fetch.sh 產：243 個原檔照抄

Kari-SRT/
├── README.md                    【改】結構圖補 aiyalaeho/text/
└── aiyalaeho/text/              【新】
    ├── README.md                這層是什麼、從哪來、誰讀它、十欄各是什麼
    ├── 多重分隔符切法.csv       split.py 產：來源檔,原句,族語,華語（158 列，人可複核）
    └── 1-句對.csv               pairs.py 產：集,來源檔,來源檔編碼格式,行號,類型,語言別代號,族語,華語,開始時間,結束時間
```

資料流：

```
SFTP ──fetch.sh──▶ kithann 暫存 ──decode──▶ 文字 ──parse──▶ 列 ──┬──▶ 1-句對.csv
                        ↑                                        │
                 離線做不到（上游在 SFTP）        多重分隔符切法.csv
                                                        ↑
                                    split.py 出工作表 → Claude(opus) → 整批驗收
                                    （做一次；之後 pairs 讀表，離線且確定）
```

`text/` 底下目前只有一個階段，編號仍從 `1-` 起——影片若到手，時間軸與 SRT 會是後面的階段。

## spec × scenario × 測試檔對照

| spec | scenario | 測試檔 |
|---|---|---|
| aiyalaeho-text-corpus | **`zipfile.is_zipfile()` 對 OLE2 回傳 True，不可據此當成 docx**（Word 把佈景主題當一小段 zip 放在 OLE 檔尾；盤點初期就是這樣把兩個好檔判成壞檔） | `text/test_decode.py` |
| aiyalaeho-text-corpus | 副檔名選 parser（`.doc`→OLE2、`.docx`→OOXML、`.txt`→純文字），不嗅探內容 | `text/test_decode.py` |
| aiyalaeho-text-corpus | **解不開就中止並指名**——不改用另一種方式重試、不寫半份 CSV、不記一列然後繼續 | `text/test_decode.py`、`text/test_pairs.py` |
| aiyalaeho-text-corpus | UTF-16 有 BOM 的檔（58 個）不可被當成 Big5 解；無 BOM 的當 Big5；UTF-8 BOM 不留在輸出 | `text/test_decode.py` |
| aiyalaeho-text-corpus | docx 取段落：`<w:p>` 一段一行、`<w:br>` 換行、`<w:tab>` 定位 | `text/test_decode.py` |
| aiyalaeho-text-corpus | 彎撇 `’`（U+2019）與 `‘`（U+2018）一律換成 ASCII `'`——docx 有 15,411 個彎撇對 11,459 個 ASCII，一半以上的喉塞音是壞的 | `text/test_decode.py` |
| aiyalaeho-text-corpus | OLE2：走 FAT／miniFAT／目錄取到 `WordDocument` 與 `1Table` 兩個串流 | `text/test_oledoc.py` |
| aiyalaeho-text-corpus | OLE2：`fWhichTblStm` 決定用 `0Table` 還是 `1Table`，選錯就解不出分片表 | `text/test_oledoc.py` |
| aiyalaeho-text-corpus | OLE2：分片表兩種編碼都要——壓縮（1 byte／字）與 UTF-16LE；中文走後者，英數可能走前者 | `text/test_oledoc.py` |
| aiyalaeho-text-corpus | 同一行雙語，`//` 與 `\\` 兩種分隔符都認（時碼檔用 `\\`） | `text/test_parse.py` |
| aiyalaeho-text-corpus | 時碼行拆成四欄，時間**原樣不換算**——drop-frame 與 non-drop 混用，沒有影片驗不了換算 | `text/test_parse.py` |
| aiyalaeho-text-corpus | **只有一個時碼（無結束時間）的行只填開始時間**——開會031、032 有幾個檔整份是這個格式，一開始漏了這條分支，1,130 列的族語欄開頭黏著原始時碼字串 | `text/test_parse.py` |
| aiyalaeho-text-corpus | **時碼抽出來之後才判斷這行的類型，不可以在「內容判不出類型」時拿還帶著時碼的原始行重判**——開會004 一整段逐行帶時碼的純華語旁白就是這樣被抓到的：324 列的時碼字串跑進族語或華語欄，即使加了單時碼支援也還在，直到把時碼抽取搬到判斷之前才修好 | `text/test_parse.py` |
| aiyalaeho-text-corpus | 有時碼、無內容的行（該窗口沒有話要說）歸 `註記`，不是 `混合` | `text/test_parse.py` |
| aiyalaeho-text-corpus | 多重分隔符（158 行）照切法表切、標 `雙語（多重分隔符，AI切割）`；表中查無就退回切最後一個並標 `雙語（多重分隔符，規則切割）`——**兩種來歷都寫在 `類型` 上**，不留看不出來歷的值 | `text/test_parse.py` |
| aiyalaeho-text-corpus | **切法整批接受或整批拒收**——項目集合不符、或某個切法接回來不等於原句，一列都不寫（半批接受會把切法安到別的句子上） | `text/test_split.py` |
| aiyalaeho-text-corpus | **切法以內容為鍵不以行號為鍵**——重下載後行號位移但文字沒變就沿用；`judge.py` 記過這個教訓（重投影一次，第 304 條變成 309 條） | `text/test_split.py` |
| aiyalaeho-text-corpus | 切法表逐列有來源檔、原句、族語、華語，不執行程式就看得懂 | `text/test_split.py` |
| aiyalaeho-text-corpus | **一行真的是兩句字幕黏在一起時（158 行裡實測 4 行是這樣）切法表可以給出兩列**，不因為要湊成一列硬黏在一起或丟掉其中一句；不加序號欄，順序就是列在檔案裡的順序 | `text/test_split.py`、`text/test_parse.py` |
| aiyalaeho-text-corpus | **判斷「族語段落裡的漢字是不是完整子句」不能只看字數**——借詞與專有名詞（黑膠唱片、鈴鈴唱片公司、南信彥、多元文化）常常也有 3 個字以上，但不是子句；要看有沒有主詞動詞、讀起來自己是不是一句話 | `text/test_split.py` |
| aiyalaeho-text-corpus | 隔行配對：羅馬字行＋漢字行成一列（全語料實測涵蓋率 74.8%，落單的歸僅族語／僅華語，不是配對失敗） | `text/test_parse.py` |
| aiyalaeho-text-corpus | **隔行落單不往下硬配**——歌謠襯字歸 `僅族語`，跳過中間行去抓下一個漢字行會把不相干的兩句黏起來 | `text/test_parse.py` |
| aiyalaeho-text-corpus | 族華混在一行又沒有分隔符 → 不硬切，整行進族語欄、歸 `混合` | `text/test_parse.py` |
| aiyalaeho-text-corpus | 註記判定：`OS1`、`Bite`、`035101`、`刪除 113208~` 歸 `註記`，仍留在 CSV | `text/test_parse.py` |
| aiyalaeho-text-corpus | 空行不出列 | `text/test_parse.py` |
| aiyalaeho-text-corpus | **語言別代號重用 `catalogue.py` 的 `LANGUAGES`／`VARIETIES`**，不另造一份表——40/41 集光靠目錄名稱比對既有表就解得出來 | `text/test_lang.py` |
| aiyalaeho-text-corpus | 判得出語言別就用語言別代號，判不出來才退到族語別代號，不得憑空指定 | `text/test_lang.py` |
| aiyalaeho-text-corpus | 目錄名稱與內容都比對不出任何代號時中止並指名，不留空不亂猜——`開會036-東布青` 就是這樣才靠內容裡「itu Bunun」這句話覆寫成布農語，不是規則自動解出來的 | `text/test_lang.py` |
| aiyalaeho-text-corpus | CSV 十欄與順序；`類型` 只出現列舉內的八個值；TAB（2,238 行）換半形空白；逗號（65 行）與雙引號（20 行）由 csv 模組跳脫 | `text/test_pairs.py` |
| aiyalaeho-text-corpus | **逐檔照收不去重**——同一集的 txt 與 docx 內容相同也各出一份，`來源檔` 分得開 | `text/test_pairs.py` |
| aiyalaeho-text-corpus | 列順序固定（集 → 來源檔 → 行號），重跑逐 byte 相同 | `text/test_pairs.py` |
| aiyalaeho-text-corpus | 每列回溯得到出處：`來源檔` 是相對上字文稿根的路徑、`行號` 對得回原檔 | `text/test_pairs.py` |
| aiyalaeho-text-corpus | 上字文稿不供字：產出後 `1-ocr/` 與兩張進度表一個位元組都沒動 | `aiyalaeho/test_paths.py`（store 版面：`text/` 與 `1-ocr/` 各自獨立） |

全部離線、fixture 合成。`test_oledoc.py` 最重——fixture 要程式化組出一個最小的 OLE2 複合檔（header＋FAT＋目錄＋兩個串流），不可放二進位檔進 repo。

## Risks / Trade-offs

- **交付物離線重建不出來** → 上游在 SFTP，`rebuild --verify` 涵蓋不到。緩解：`來源檔`＋`行號` 兩欄讓每一列都回溯得到出處；列順序固定，同一批來源重跑逐 byte 相同，所以「重下載重跑」就是驗證手段。
- **④ 型多重分隔符靠模型判讀，模型會錯** → 兩條 cue 黏成一行時，切點是語意判斷。緩解三層：整批驗證（切開再接回來必須等於原句，擋掉憑空增刪字）、切法表人讀得懂可逐列複核、`類型` 標明 `AI切割` 讓下游知道這 158 列的來歷與其他 43,724 列不同。
- **AI 那一步不是離線的** → 需要一次 Claude 判讀。緩解：只做一次，結果進 Kari-SRT；之後 `pairs.py` 讀表，這一步就回到離線且確定。提示詞改了才需重跑，版本跟著跳。
- **隔行配對是啟發式的** → 93.3% 涵蓋率不是 100%。緩解：`類型=隔行配對` 讓下游知道這些列的信心與 `雙語` 不同級；落單標 `僅族語` 而不是丟掉。
- **OLE2 讀取器是 120 行二進位解析，只服務 2 個檔** → 維護成本對比效益不划算。緩解：獨立成 `oledoc.py` 一個模組、自己一支測試檔，壞了不會牽動別處；若日後 `.doc` 絕跡可整支刪掉。
- **`類型` 的判定規則會隨資料長見識而改** → 改了規則，CSV 內容就變。緩解：規則集中在 `parse.py` 一處，重跑成本是一次下載加一次解析（9.2 MB，分鐘級）。
- **`tox -e shellcheck` 基準線是紅的** → `kithann/` 底下三個臨時檔在報 SC2009／SC2012／SC2148，與本 change 無關。緩解：驗收時只確認 `fetch.sh` 自己乾淨，不把既有的紅算在這條線上。
