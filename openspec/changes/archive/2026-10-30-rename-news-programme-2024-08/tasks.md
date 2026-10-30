# Tasks

## 1. 先寫測試，讓它們紅

- [x] 1.1 `tests/catalogue/test_catalogue_checks.py` 補時段解析、括號寫法、日期對照三組案例（design 對照表前 8 列）。驗證：跑 `.tox/unittest/bin/python -m unittest tests.catalogue.test_catalogue_checks`，新案例失敗、舊案例全過
- [x] 1.2 `tests/news/test_name_catalogue.py`、`test_episodes.py`、`test_sources.py` 各補 1 例（新名稱列的 `--check`、工作區名、挑檔的時段規則）。驗證：各檔單跑，新案例失敗、舊案例全過
- [x] 1.3 `tests/news/test_redate.py` 補跨界線兩個方向各 1 例。驗證：單跑，新案例失敗、舊案例全過

## 2. 實作，讓測試變綠

- [x] 2.1 `scripts/catalogue_checks.py`：`SLOTS` 擴成六個名稱、新增 `RENAMED_ON` 與 `programme_for(時段, 播出日期)`、新增日期對照檢查並掛進 `row_problems`、`slot_of` 錯誤訊息補全形括號提示。驗證：1.1、1.2 的案例全綠，開會了的檢查不受影響
- [x] 2.2 `scripts/news/redate.py`：`redate_row` 改日期後以 `programme_for` 重寫節目名稱。驗證：1.3 的案例全綠
- [x] 2.3 `.tox/unittest/bin/python -m unittest discover -s tests -t .` 全過、`.tox/flake8/bin/flake8 . --count` 為 0

## 3. 遷移 smkul.csv

- [x] 3.1 寫 `migrations/rename_programme.py`：dry-run 印出「改 337 列（午間 147、晚間 146、晨間 44）、不動 2,816 列、總列數不變」，數字不符就中止；寫入時保留 BOM 與 CRLF；重跑時已改的列不再動。驗證：對合成的小目錄跑，先 dry-run 不寫檔，再寫入，再重跑一次檔案逐 byte 相同
- [x] 3.2 對真實 `Kari-SRT/news/smkul.csv` 跑遷移。驗證：`git -C Kari-SRT diff --stat news/smkul.csv` 只有 337 列各改一個欄位；`python3 -m scripts.news.name_catalogue --check` 不合 0 列

## 4. 文件同步

- [x] 4.1 `Kari-SRT/README.md` 第 100 行改成兩組名稱與界線，不寫死列數；`tests/catalogue/README.md` 補 1.1、1.2 的對照列並把「983 列零例外」改成不寫死列數；`tests/news/README.md` 補 redate 的新一列。驗證：講節目名稱與時段的那幾句不再寫「983 列」（`Kari-SRT/README.md` 另一句講語言別代號的數字是別件事，不在本次範圍）
- [x] 4.2 `scripts/README.md` 的 `catalogue_checks.py`、`redate.py` 兩列補一句；`.claude/commands/smkul-catalogue-import.md` 補「2024-08-01 起節目名稱寫看見族語（時段）、括號全形」。驗證：`tests/news/test_readme_covers_scripts.py` 通過

## 5. 驗收

- [x] 5.1 `.tox/rebuild/bin/python -m scripts.news.rebuild --verify` 通過，且它說的集數等於目錄總列數（會對真實目錄跑新的日期對照檢查）
- [x] 5.2 `.tox/unittest/bin/python -m unittest discover -s tests -t .`、`.tox/flake8/bin/flake8 . --count`、`python3 -m scripts.news.name_catalogue --check` 都通過
- [x] 5.3 在 `kithann/tuiue/<MMDD>/` 寫回覆紀錄，內容含做了什麼、驗收數字、外部單位可能依賴「節目名稱」這一點

## Workflow follow-up

- 全部完成後 `/opsx:archive`，把本 change 的 delta 併進 `openspec/specs/episode-catalogue/spec.md`
