## 1. 逐集把關

- [x] 1.1 `tests/news/test_publish_gate.py`（紅）：同一批裡「1 集已完成、58 集尚未切 cue」時，已完成的那集出現在要寫入的清單裡——這正是 006午 現在被擋住的處境
- [x] 1.2 `tests/news/test_publish_gate.py`（紅）：未完成的集不會被寫入，而且輸出指名它卡在哪一步（`publishable()` 的 `reason` 要原樣傳出來，不可以被跳過月份的邏輯吃掉）
- [x] 1.3 `tests/news/test_publish_gate.py`（紅）：一批裡沒有任何一集完成時，流程以**零**狀態結束且不寫入任何檔案——回非零會讓批次腳本把「還沒輪到」誤判成失敗
- [x] 1.4 `tests/news/test_publish_gate.py`（紅）：字幕版型異常集（`1-ocr/` 底下沒有任何檔）在同批其他集未完成時照樣寫入並清除 pending
- [x] 1.5 `tests/news/test_publish_gate.py`：既有 `TestGateByMonth` 五條改寫——`gate()` 本身的行為不變（它仍是查詢介面），但要改掉「月份是把關單位」的敘述與測試名，免得留下與實際行為相反的說明
- [x] 1.6 `scripts/news/publish.py`（綠）：`main()` 拿掉 `held` 的計算與月份 `continue`、拿掉 `if held and not ready: return 1`；模組 docstring 與 `gate()` 的註解改寫（兩處目前都明文寫著整批把關的理由）

## 1b. 《開會了》那支同步（被改的 requirement 是兩個語料共用的）

- [x] 1b.1 `tests/aiyalaeho/test_publish.py`（紅）：同一批裡有未完成的集時，已完成的集照樣寫入並清除 pending——現行是 `if blocked: return 1` 一字都不寫
- [x] 1b.2 `scripts/aiyalaeho/publish.py`（綠）：`main()` 拿掉 `if blocked: … return 1`；模組 docstring 與 `gate()` 的註解改寫。**動手前重讀本檔**——`add-aiyalaeho-text-corpus` 那條線在同一個資料夾底下作業

## 1c. 順手修的：store 副本的排版（跑 publish 才發現）

- [x] 1c.1 `tests/news/test_tracker_home.py`（紅）：`publish_one` 寫進 store 的檔是排版過的（`indent=2, sort_keys=True, ensure_ascii=False` 加尾端換行），不是工作目錄檔的逐 byte 複本；已定版的集重跑 `publish` 不改動 store 內既有檔的 byte
- [x] 1c.2 `scripts/news/publish.py`（綠）：`publish_one` 改成讀 JSON 再寫，格式重用 `redump_store.dump()`（本來叫 `_dump`，改成公開）——兩支若差一個換行，publish 與 redump 就會互相蓋來蓋去
- [x] 1c.3 `scripts/news/redump_store.py`：`_dump` 改名 `dump` 並補 docstring 說明為什麼要公開

## 2. 驗收

- [x] 2.1 `.tox/unittest/bin/python -m unittest discover -s tests/news -t .` 與 `-s tests/aiyalaeho` 全綠
- [x] 2.2 `.tox/flake8/bin/flake8 . --count` 為 0
- [x] 2.3 `python3 -m scripts.news.publish --check`：確認它列出的待寫集數是「已完成但還沒發布」的那些，1 月未完成的集仍然被跳過並附理由
- [x] 2.4 `python3 -m scripts.news.publish`：實際寫入
- [x] 2.5 `.tox/rebuild/bin/python -m scripts.news.rebuild --verify` 通過，且它驗的集數＝inventory 內非 pending 的筆數（會從 74 變 75）
- [x] 2.6 `python3 -m scripts.news.name_catalogue --check` 通過
- [x] 2.7 `git status` 與 `git -C Kari-SRT status` 列給使用者，由他 `git add`

## 3. 文件

- [x] 3.1 `scripts/news/README.md`：若有「整批才會定版」的敘述，改成逐集
- [x] 3.2 `.claude/commands/smkul-news.md`：同上
