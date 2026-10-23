# NetworkLab C05：報告完整性、故障注入與中斷恢復驗收

## 定位與交付

C05 是 **Phase C 的隔離驗收套件**，不修改 B09 Report Writer、B10 Result Browser、B05 Runner 或正式九個模組。與已發布的 `v0.1.1` 共存；這不是新的 Release，也不應將原本的 Git Tag 指向其他 Commit。

交付 3 個檔案：

- `tests/test-c05-recovery.py`：Python 3.8+ 標準函式庫，21 組 `unittest`，每組建立自己的臨時 HOME / NETLAB_HOME 和 NetworkLab 原始碼副本；九個 Worker 預先覆蓋成無操作佔位，**僅顯式啟用合成 fixture**。
- `tests/test-c05-all.sh`：POSIX sh 入口，供 macOS、Debian／Ubuntu、Alpine BusyBox ash 執行。
- `docs/implementation-c05.md`：測試契約、已知限制與實機指令。

**完全離線**：不發送封包，不下載網路程式碼，不修改真實 `~/.networklab`，不使用 sudo，不建立 OpenRC、cron 或其他排程。所有新產生的測試紀錄 `synthetic: true`，不能被當作真實網路數據。

## 執行方法

將 C05 增量 ZIP 合併至本地 Git Checkout（勿覆蓋個人 config）：

```sh
unzip -o NetworkLab-C05-incremental.zip -d .
sh tests/test-c05-all.sh
```

可單獨執行：

```sh
python3 -B tests/test-c05-recovery.py
```

若使用者已 push 到 GitHub `main`，VPS 端可 `git pull --ff-only` 後執行 `sh tests/test-c05-all.sh`。Alpine 如缺少依賴，先透過管理員帳號執行 `apk add --no-cache bash python3 git`；Debian/Ubuntu 則依實際套件情況安裝 Bash、Python3。**不要在仍需保留現有結果的環境裡手動執行故障注入**；由測試腳本建立的私有臨時環境才是安全界線。

## 21 組驗收案例

| 分類 | 驗收行為 |
|---|---|
| 正常交付 | C、S 各產生有效的 synthetic Manifest / Summary / Raw，包含 UTC+8、唯一 Run 身分及可驗證的 SHA-256 |
| 無 handoff | Worker 成功退出，但沒有 `worker-report.json` 時不得發布正式報告；保留私有工作區 |
| 錯誤 handoff | 截斷 JSON 應拒絕交付、回傳 5 並保留原件 |
| 原生格式 | 無效 JSON 與 NDJSON 原始資料應拒絕發布 |
| 路徑與連結 | Raw 符號連結、硬連結、輸出根目錄符號連結應拒絕 |
| 非零狀態 | Worker exit=5、有合法 checkpoint 應發布 `failed`，保留 Raw 證據 |
| 非完整狀態 | Worker exit=0，但測試標記 skipped 應降級 `partial (7)` |
| 超時 | 有 checkpoint 發布 `timeout (6)`；無 checkpoint 不發布、工作區仍存在 |
| SIGINT | 有 checkpoint 發布 `interrupted (130)`；無 checkpoint 不發布、工作區仍存在 |
| 篡改 | 原始檔、Summary、Manifest、索引檔符號連結篡改必須被拒絕；`results show` 不應宣稱 VERIFIED |
| 併發近似 | 同一秒連續執行要分配不同 run_id、run_uuid、Manifest 檔名，不覆寫舊結果 |
| 提交途中故障 | 在發布 Manifest 時注入失敗，僅留下未索引的 Raw / Summary；`results list` 不把它們當成有效 Run；新 Run 仍能成功 |
| 原始碼保護 | 測試完成後，Report Writer／Runner／Browser 原始檔位元內容未改變 |

以上 21 組為 `unittest` 計數，包含一組內部對 C / S 各執行一次的子測試；**不應視作 21 次實際網路測速**。

## 安全與故障邊界（必讀）

1. **正式提交點是 Manifest。** 若提交前故障，無 Manifest 的 Raw / Summary 不被 `results list` 視為可信 Run。
2. **目前尚無自動孤兒清理／交易回滾。** 在最後 Manifest 寫入失敗後，資料目錄可能殘留 Raw / Summary。C05 確認它們不會被偽裝成已提交報告，但**未實作**自動修復、將同一 run_id 重新提交或清除孤兒檔。請勿在未審核前手動刪除，避免遺失部分證據。
3. **有 checkpoint 才有可發布的部分結果。** Timeout 或 SIGINT 發生但尚未寫好有效 handoff 時，只保留私有暫存證據，沒有正式報告。
4. **`results list` 的 header 未驗證。** `results show RUN_ID` 才重新校驗所有索引檔案的 SHA-256、長度及 Summary 身分。
5. **SHA-256 是一致性檢查，不是來源認證。** 如果攻擊者能同時修改 Raw / Summary / Manifest 並重算全部雜湊，這套機制不提供獨立的防偽保證；沒有數位簽章。
6. **私人資訊仍須模組端審閱。** 標準 Report Writer 的日誌遮蔽是 best-effort，對任意 Raw 資料不保證完全去識別化。
7. **驗收只覆蓋合成 Worker。** 未驗證真實 TCP MTR、iperf3、NextTrace、Flent、網路吞吐、網路品質、長時間執行或斷電後的檔案系統持久性。

## 本地測試紀錄與跨平台狀態

- Linux 隔離環境 root：C05 **21/21 通過**。
- Linux 隔離環境普通使用者：C05 **21/21 通過**。
- B09 Report Writer 迴歸：**19/19 通過**。
- B10 Result Browser 迴歸：**17/17 通過**。
- macOS／Debian 12／Alpine 3.21.8 實機的 C05：**尚待使用者執行**；不得用前述 Linux 隔離結果冒充。

## 後續工程問題

如需達到真正的可恢復提交（而不僅是可檢出不完整報告），應另列開發工作：孤兒 Raw / Summary 掃描、帶 run_id 的事務日誌、可安全重試的提交、孤兒清理的 dry-run / 審核流程、故障後復原驗收、跨 run 簽章／鏈式索引。這些功能不是 C05 驗收腳本偷偷加到核心裡的內容。
