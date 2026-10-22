# B05 — 共用 Runner 與模組調度（實作交付）

- 開發版本：NetworkLab v0.1.0 Skeleton / B05
- 上游規格：A03（CLI）、A04（Menu）、A05（Config）、A06（Modules）、A07（Reports）、A08（Architecture）
- 平台：macOS Bash 3.2+、Linux Bash，Python3 3.8+
- 性質：**可執行基礎框架；尚未實作任何真實網路測試、服務、排程或正式測量報告。**

## 新增／修改的檔案

| 路徑 | 功能 |
|---|---|
| `lib/runner.sh` | 唯一 CLI→Runner 的 Shell Bridge；固定九個模組映射與參數交付 |
| `lib/runner_host.py` | 只用 Python 標準函式庫；唯讀預檢、工作區、Context、子程序生命週期、信號、超時 |
| `netlab-c.sh`, `netlab-s.sh` | 將舊版直接輸出 `NOT_IMPLEMENTED` 的分派，改為呼叫 `netlab_runner_dispatch` |
| `lib/menu.sh` | 使用 `python3 -S` 載入唯讀選單資料，減少與第三方 Python 套件的意外耦合 |
| `c/*.sh`, `s/*.sh` | 9 個 **B06 相容佔位模組**；直接調用先回到相同的公開 CLI，內部返回 8 |
| `tests/test-b05.py` | 無網路 Runner 測試：9 個行為場景與模擬 worker |
| `tests/test-b03-b04.py` | 保留先前 `stdin=subprocess.DEVNULL` 修正，並為 S 端測試配置增加有效 `server_id` |
| `tests/test-b05-all.sh` | 一次執行 B01–B05 測試 |

本增量包不包含或覆蓋使用者已完成的 A01／A02／A09 GitHub 文件。若 A02 的九個空模組檔案已經自行擴充，**先比對備份，再合併**，不要直接蓋掉私人程式修改。通用入口、`menu.sh` 則應採用此次版本，否則 Runner 不會接入。

## 主要設計

1. **白名單**：`c-inventory`、`c-standalone`、`c-paired`、`c-proxy`、`c-collect`；`s-inventory`、`s-toolbox`、`s-service`、`s-scheduler`。不使用使用者文字直接拼成可執行路徑；符號連結不能逃逸程式目錄。
2. **單一路徑**：`netlab-c`、`netlab-s`、Menu 和直接執行模組，全部進同一 CLI Parser／Runner。直接執行 `c/c-paired.sh --target nat-us` 會轉交 `netlab-c paired --target nat-us`。
3. **安全閘門**：只有註冊且含有 `NETLAB_IMPLEMENTED_V1` 內部標記的模組檔案能進 worker。A02 的空白檔、B05 的佔位模組都會返回 `NOT_IMPLEMENTED (8)`，**不會把空白模組 exit 0 誤判為測試成功**。這不是安全授權機制，後續 B06 需要對實際有權限的操作再驗證。
4. **唯讀預檢**：C 配對或收集必須能在 8 欄 `targets.conf` 找到已驗證 ID；S 正式模組呼叫要求有效的 `s.conf [general].server_id`。本階段是精簡版驗證，完整配置解析／遷移仍留 B07／B08。
5. **工作區**：模組通過預檢且確實可執行時，才建立 `~/.networklab/tmp/run-<run_id>/`（0700）以及 `context.json`（0600）。同秒衝突採用原子 mkdir 與 `-01` 後綴。Context 由 Runner 固定，包含 profile、target、身份、UTC+8 時間及路徑；不存密碼與 Token。
6. **執行管理**：子程序在新 session 啟動，Runner 用受控 PID 的 process group 傳遞 SIGTERM，必要時 SIGKILL，不使用 `kill 0` 或 `pkill`；Ctrl+C 返回 130、內部 Timeout 返回 6，保留當次工作區及 stdout/stderr 日誌以便 B09 接管。
7. **無假的結果**：佔位模組不寫入 `results/`，也不產生假的 manifest、summary。B05 的模擬 worker 即使返回 0，也只代表其**程序**結束，不代表已存在驗收合格的測速報告。
8. **預覽**：佔位模組的 `--dry-run` 依 A06 仍回傳 8，不啟用外部工具、SSH、服務或排程。

## 開發階段使用

```bash
# 由 Repository 根目錄執行
bash tests/test-b05-all.sh

# 不會進行任何測速：
bash netlab-c.sh --help
bash netlab-c.sh inventory --non-interactive
bash netlab-s.sh toolbox --modules netquality --dry-run
bash c/c-inventory.sh --help
```

由於 A05 要求 S 端具備合法身份，使用 `netlab-s.sh inventory`／`toolbox` 前，必須在 `~/.networklab/config/s.conf` 設定：

```ini
[general]
server_id = test-vps
```

這只是本地示例 ID；實際部署應按每台 VPS 選擇唯一 ID。

## 尚未實作（不算 B05 缺陷）

- **B06**：正式模組入口、內部 worker 合約及更完整的安全檢查。
- **B07／B08**：完整 C／S 配置解析器、目標編輯與 Profile 生效參數、工具安全預算。
- **B09**：Schema 驗證、manifest／summary、Raw 原子封存、可共享報告與錯誤恢復。
- 單項與整批 Profile Timeout 尚無正式安全預算。B05 目前僅設 60 秒**開發看門狗**，不是日後 iperf3 等工具的建議執行時長。
- 不具備跨設備的實際連線、定時任務、服務變更或第三方工具執行能力。

## 測試界限

在隔離 `NETLAB_HOME` 的臨時目錄執行，不訪問公共網路。已對照既有 B01／B02 和 B03／B04 腳本進行回歸測試。是否兼容 **你的 Mac Bash 3.2、Debian／Ubuntu、Alpine**，仍需在對應實機上跑同一套測試。
