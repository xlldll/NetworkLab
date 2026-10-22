# B06：九個模組佔位入口與內部 Context 驗證（實作交付）

- 版本：NetworkLab v0.1.0 Skeleton，Phase B / B06
- 先決條件：B01–B05 已合併；macOS Bash 3.2+ 或 Linux Bash，Python 3.8+
- 性質：**模組入口及執行契約已實作；尚未完成任何真實測量、服務啟停、排程或正式報告。**
- 授權邊界：沒有複製 NetQuality、TcpQuality 等第三方工具的實作。

## 本次交付檔案

| 路徑 | 用途 |
|---|---|
| `lib/module_entry.py` | 共用內部 Worker Context 驗證器；獨立模組的 B06 佔位行為 |
| `c/c-inventory.sh` | C 端本機盤點佔位入口 |
| `c/c-standalone.sh` | C 端公共網路測試佔位入口 |
| `c/c-paired.sh` | C ↔ S 聯動測試佔位入口 |
| `c/c-proxy.sh` | C 端代理測試佔位入口 |
| `c/c-collect.sh` | C 端結果收集佔位入口 |
| `s/s-inventory.sh` | S 端系統盤點佔位入口 |
| `s/s-toolbox.sh` | S 端第三方工具管理佔位入口 |
| `s/s-service.sh` | S 端測試服務佔位入口 |
| `s/s-scheduler.sh` | S 端排程佔位入口；公開命令名稱仍為 `schedule` |
| `tests/test-b06.py` | 無網路、隔離工作區的 Context 與九模組入口測試 |
| `tests/test-b06-all.sh` | 完整 B01–B06 回歸測試 |

本次**不修改** `lib/runner.sh`、`lib/runner_host.py`、公開 CLI 及主選單。B05 的既有 Runner 能直接識別這九個 `NETLAB_PLACEHOLDER_V1` 模組，並返回 `8`。

## 雙入口合約

模組檔案既可直接執行，也可由主入口選單及 CLI 調用：

```bash
bash c/c-inventory.sh --help
bash c/c-paired.sh --target nat-us --profile quick --non-interactive
bash s/s-toolbox.sh --modules netquality --dry-run
```

在**公開調用**下，模組腳本把參數原樣轉交 `netlab-c.sh`／`netlab-s.sh`，由 B02 CLI、B05 Runner 驗證。其行為及退出碼必須一致。正常佔位模組返回 `NOT_IMPLEMENTED (8)`，而非「測速完成」。`--help` 及 `--version` 不需要配置即可顯示。

在**內部 Worker 調用**下，Runner 傳入：

```text
NETLAB_INTERNAL_WORKER=1
NETLAB_CONTEXT_FILE=/absolute/path/to/run-.../context.json
NETLAB_WORK_DIR=/absolute/path/to/run-...
```

B06 的 `module_entry.py` 驗證 Context，通過後佔位模組仍然返回 `8`。若有人自行設定內部變數但沒有合法 Context，返回 `SAFETY_BLOCKED (9)`。

## Context 驗證範圍

- 僅接受 A06 註冊的九個模組 ID；Role (`C`／`S`) 及 `task_kind` 必須一致。
- 只接受 `contract_version = 1`、合法 Profile、正確布林型別、UTC+08:00 起始時間與 UUIDv4。
- `run_id` 必須與私有目錄 `run-<run_id>` 對應。
- Context 必須是 `NETLAB_WORK_DIR/context.json`，且位置不得逃離工作區。
- 工作區必須是由目前使用者擁有的真實目錄，禁止 group/other 存取；Context 必須是目前使用者的正常檔案，不接受符號連結、過寬權限與超過 256 KiB 的內容。
- JSON 重複鍵、身份衝突、缺失目標、C／S 身份混用與錯誤資料型別均拒絕。
- `paired`、`collect` 的 C 端 Context 必須有 `target_id` 和目標資料；S 端必須有有效 `server_id`。
- 驗證失敗返回 `9`；通過驗證只是證明資料結構一致，**不是**測速成功，也不是作業系統的授權批准。

> **安全界限：** `NETLAB_INTERNAL_WORKER`、本地 Context 或 `NETLAB_IMPLEMENTED_V1` 標記並非不可偽造的安全憑證。未來涉及 `sudo`、NAT、防火牆、排程、服務啟停、外部腳本下載等操作，必須重新進行獨立授權、參數與資源安全檢查。這個 Context Validator 不能替代它們。

## 未來模組的接入約定

現在的佔位檔案**沒有** `NETLAB_IMPLEMENTED_V1` 標記。當模組真正完成開發及通過驗收時，才將它標記為實作完成，並把內部佔位分支換成具體的測量／管理邏輯。

Python 模組可以重用：

```python
from module_entry import validate_context
context = validate_context('c-inventory')
# 後續只處理本模組的實際工作，並寫入 Runner 私有工作區。
```

Shell 模組可先調用：

```bash
python3 -S "$NETLAB_MODULE_ROOT/lib/module_entry.py" \
  --module-id c-inventory --validate-only || exit $?
# 驗證通過不等於具備 sudo 或系統變更權限。
```

**注意：** 這些只是未來模組開發示例，不表示 B06 已有真實採集功能。模組不得自行生成正式 `manifest`、`summary`；那是 B09 Report Writer 的職責。

## 如何合併

- **增量 ZIP：** 只包含本次 12 個新增／修改檔案及本說明。若你已自行改寫 C／S 模組，請先做 Diff，避免覆寫。
- **整合 ZIP：** 包含 B01–B06 已交付的程式與測試，便於從頭驗證；**不包含你的 A01／A02／A09 專案檔案或私人配置**。
- 兩個壓縮包均保留 Repository 內的相對路徑；不應直接解壓到 `~/.networklab/`，先合併到 Git 工作目錄。

```bash
# 在 NetworkLab Repository 根目錄
bash tests/test-b06-all.sh
bash netlab-c.sh inventory --non-interactive  # 預期退出 8
bash c/c-inventory.sh --help               # 預期退出 0
bash netlab-s.sh --help                     # 預期退出 0
```

上述測試全程使用合成資料，無需聯絡 VPS。S 端欲執行 `inventory`／`toolbox` 的 CLI 預檢，需在 `s.conf` 設定合法 `server_id`，不能使用 `CHANGE_ME`。

## 測試結果與限制

- B01/B02：20 + 103 項通過。
- B03/B04：34 項通過。
- B05：9 個 `unittest` 測試案例通過。
- B06：10 個 `unittest` 測試案例通過，涵蓋九個公開模組、九個合成內部 Context、Runner→Worker 實際交接、拒絕偽造或損壞 Context、權限檢查及 `--validate-only`。
- 合計 176 項測試／檢查案例；此數字不是 176 個獨立平台或端到端測速驗證。
- 本次在隔離容器環境測試，**未**在你的 Mac、Debian／Ubuntu 或 Alpine 實機上驗收。
- 尚未提供正式結果寫入器，Runner 仍只保留其臨時工作區和日誌。

## 下一階段

**B07：C 端 VPS 清單與 `c.conf` 配置管理**；**B08：S 端 `s.conf`、Profile 與工具覆寫規則**。完成後再進行 B09 報告寫入器。
