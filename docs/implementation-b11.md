# NetworkLab B11：離線 Self-test 實作

## 目的

實作既有 A03 契約中的 `netlab-c self-test` 與 `netlab-s self-test`。這是 **v0.1.0 骨架驗證**，不是網路性能測試；不執行 iperf3、SSH、HTTP 測速、公開測試工具，不建立排程，也不修改用戶配置或正式報告。

## 檔案

| 檔案 | 作用 |
|---|---|
| `lib/self_test.py` | Self-test 核心：臨時應用副本、合成 Worker、報告與完整性驗證 |
| `lib/runner.sh` | 新增 `self-test` 路由，沿用 A03 CLI 設計 |
| `tests/test-b11.py` | 新增六組自動化測試 |
| `tests/test-b11-all.sh` | 執行 B01–B11 完整回歸測試 |

## 操作

```bash
./netlab-c.sh self-test
./netlab-s.sh self-test
./netlab-c.sh self-test --non-interactive
./netlab-s.sh self-test --quiet
bash tests/test-b11-all.sh
```

`self-test` 無需有效 `~/.networklab/config/`，也無需實際 VPS。它建立臨時目錄，複製執行所需的最小化程式碼，使用固定的合成配置與 Worker 測試以下九項：

- C/S CLI 說明與版本顯示。
- C/S 配置解析器、VPS 清單格式、Profile。
- 尚未實作模組必須返回 `8`，不得產生假報告。
- 沒有 Runner Context 的內部 Worker 必須被拒絕（`9`）。
- Runner 可以呼叫 **臨時副本內**的合成 Worker。
- Manifest、Summary、Raw、UTC+8、run UUID、SHA-256 一致性。
- `results list` 與 `results show` 正確查找與驗證。
- 更改臨時 Raw 檔後，雜湊驗證及 `results show` 必須拒絕（`5`）。
- 安裝目錄的關鍵檔案未被修改。

合成資料全部必須包含 `synthetic: true`，且僅寫入 Self-test 專屬的臨時路徑，不會進入使用者正式 `~/.networklab/results`。

## 退出碼

| Code | 含義 |
|---|---|
| `0` | 九項 Self-test 檢查通過 |
| `2` | CLI 參數無效（由 A03 處理） |
| `4` | 缺少 Python3 |
| `5` | 測試過程失敗、必要檔案缺失、驗證不一致等 |

## 安全範圍與限制

- 本次使用的是標準函式庫，沒有新增 Python 套件依賴。
- 使用 `python3 -B -S`，不生成現場 Python 快取。
- 執行每個 CLI 子命令時都關閉標準輸入，並設置有限 Timeout。
- 自我測試使用自身定義的合成 Worker，**不是**執行正式測量模組。
- Self-test 成功不代表 VPS 路線品質正常、外部測試工具可用、所有第三方授權合規、或 Linux 發行版兼容性已經驗證。
- 只檢查隔離的配置範本；用戶的真實 `c.conf` / `s.conf` 仍應另行執行 `config validate`。
- 當測試程式本身被修改或環境受損，Self-test 的安全聲明也不構成惡意程式碼防護。

## 本地驗證

B01–B10 原有 237 項檢查與測試，加上 B11 六組，共 243 項離線檢查通過；另外兩端 Self-test 各自有九項內部檢查。本次未在使用者的 Mac 或真實 Alpine、Debian VPS 上執行。

## 合併

只需要複製本階段新增或變更的檔案；**不要**以整合包覆蓋原有的 A01/A02/A09 或個人 `~/.networklab/`。正式安裝與更新仍屬 B12/B13。
