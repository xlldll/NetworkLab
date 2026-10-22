# NetworkLab B01 / B02：共用函式與 CLI 解析器

- 版本：v0.1.0 Skeleton
- 規格依據：A03 `docs/commands.md`、A04 `docs/menus.md`、A05 `docs/configuration.md`、A06 `docs/modules.md`、A08 `docs/architecture.md`
- 狀態：**可執行的程式實作與單元測試**。尚未完成正式 C／S 入口、Runner、配置解析、測速與更新器。
- 平台要求：Bash 3.2+（macOS 原生 Bash 3.2；Linux Bash），無需第三方 Bash 模組。

## 本次新增檔案

```text
NetworkLab/
├── lib/
│   ├── common.sh                  # B01 共用基礎函式
│   └── cli.sh                     # B02 CLI 解析器（新增於 A02 的 lib/）
├── tests/
│   ├── cli-harness.sh             # 專用解析測試器，非正式入口
│   ├── test-cli.sh                # CLI 測試
│   ├── test-common.sh             # 共用函式測試
│   └── test-b01-b02.sh            # 一鍵驗證
└── docs/
    └── implementation-b01-b02.md # 本說明
```

**合併原則：** 僅複製本次檔案至已存在的 Repository。不要以本壓縮包取代你已完成的 A01／A02／A09，也不要覆蓋先前六份規格與個人設定。

## B01 `lib/common.sh`

| 函式 | 職責 | 備註 |
|---|---|---|
| `netlab_now_utc8` | 產生 ISO 8601 的 UTC+08:00 時間 | 使用 `TZ=UTC-8`，不改系統時間、無需 tzdata |
| `netlab_filename_time_utc8` | 產生 `YYYY-MM-DD-HH-mm-ss` | 檔名只定義時間段；唯一性由 B09 完成 |
| `netlab_resolve_home` | 取得使用者的 NetworkLab 根目錄 | `NETLAB_HOME` 必須為絕對路徑 |
| `netlab_local_path` | 取得 app/config/results/logs/tmp 路徑 | 不偷偷新增目錄 |
| `netlab_mkdir_private` | 建立私人目錄 | 以 077 umask 執行，不修改已有目錄權限 |
| `netlab_info`／`netlab_warn`／`netlab_error` | 統一訊息樣式 | `--quiet` 只抑制一般訊息 |
| `netlab_log` | 在指定絕對路徑追加帶時間戳記的日誌 | 不主動寫入任何檔案；禁止傳入密碼、Token 或完整 argv |
| `netlab_status_from_exit_code` | 退出碼映射成狀態 | 遵循 A03：0/2/3/4/5/6/7/8/9/10/130 |
| `netlab_check_command` | 檢查二進位工具存在與否 | 不主動安裝依賴 |

載入共用函式本身不讀取使用者配置、不建立目錄、不調用測速工具。

## B02 `lib/cli.sh`

### 函式與產物

- `netlab_cli_parse c|s [ARGS...]`：**只解析 CLI 語法**，成功回傳 `0`；用法錯誤回傳 `2`。
- `netlab_cli_print_help c|s`：顯示 CLI 用法及部分命令示例。
- `netlab_cli_route_valid`：檢查完整的角色／命令／子命令／必要位置參數組合。
- `netlab_cli_allowed_flags`：角色與命令對應的允許參數白名單。
- `netlab_cli_valid_id`、`netlab_cli_valid_port`：語法層的設備 ID 與連接埠驗證。
- 解析結果儲存在 `NETLAB_CLI_*` 全域變數，例如 `NETLAB_CLI_COMMAND`、`NETLAB_CLI_TARGET`、`NETLAB_CLI_PROFILE`、`NETLAB_CLI_NON_INTERACTIVE`、`NETLAB_CLI_DRY_RUN`。

### 解析器可做的事

- 認識 A03 的 C／S 全部命令及子命令，不依賴配置和遠端網路。
- 拒絕未知命令、未知參數、重複參數、缺少值、錯誤 Profile、非法 target_id、非法 Port、非法模組 ID、非正整數 Limit。
- 檢查不可互動時 `paired`／`collect` 必須帶 `--target`；`targets add` 必須提供必要欄位。
- 允許 `netlab-c targets --help` 之類命令群組的說明，但不允許缺少子命令就執行群組。
- 區分全域 `netlab-c --version`（顯示程式版本）與 `netlab-c update apply --version v0.1.1`（指定更新版本）。
- 對適用的 `results list`／`logs list` 提供 `--limit 20` 預設值。
- 忽略實際配置是否存在：`--help`／全域 `--version` 應永遠能運作。

### 本次刻意不做的事

- **不**解析 `c.conf`／`s.conf`／`targets.conf`：分別交給 B07／B08；因此只做 CLI 旗標語法，不保證目標已存在、IP 真實有效或 Profile 已生效。
- **不**啟動真實模組：由 B03／B04 入口和 B05 Runner 實作；未實作測試功能最後應回傳 `8`，絕不可把「CLI 合法」回傳 `0` 當成「測量成功」。
- **不**寫 `manifest`／`summary` 或結果檔：交給 B09。
- **不**調用 sudo、Homebrew、SSH、curl、第三方腳本或修改系統。

## 如何運行單元測試

從 NetworkLab Repository 根目錄執行：

```bash
bash -n lib/common.sh lib/cli.sh
bash tests/test-b01-b02.sh
```

單獨觀察解析行為（僅供開發，不是最終 `netlab-c`/`netlab-s`）：

```bash
bash tests/cli-harness.sh c paired --target nat-us --profile quick --dry-run
bash tests/cli-harness.sh s toolbox --modules netquality,tcpquality --profile standard
bash tests/cli-harness.sh c targets --help
bash tests/cli-harness.sh s update apply --version v0.1.1
```

成功案例的前綴為 `PARSE_ONLY`，表明只是語法驗證，不是實際測試。錯誤旗標傳回 `2`，並在 stderr 說明原因。

## B03／B04 入口如何接線（示意，不要當作已完成的入口）

```bash
#!/usr/bin/env bash
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$REPO_ROOT/lib/common.sh"
. "$REPO_ROOT/lib/cli.sh"
netlab_cli_parse c "$@" || exit $?
if [ "$NETLAB_CLI_HELP" -eq 1 ]; then netlab_cli_print_help c; exit 0; fi
if [ "$NETLAB_CLI_SHOW_VERSION" -eq 1 ]; then
  printf 'NetworkLab v%s\n' "$NETLAB_VERSION"
  exit 0
fi
# TODO B03/B05: dispatch to a real handler or return NOT_IMPLEMENTED (8).
# Never report successful measurement just because the parser returned 0.
```

模組直接執行時同樣須走 B05 Runner；不要在 `lib/cli.sh` 內直接 source 第三方測試腳本。

## B03 前要再次核對的整合點

- 程式碼來源可能放在 `~/.networklab/app/`，`NETLAB_HOME` 只是資料根目錄，兩者路徑不應混為一談。
- B07 驗證 `--target` 實際對應的 `targets.conf` 記錄；B08 驗證 `server_id` 及 Profile。
- `--profile` 的配置預設值在 B07／B08 驗證後載入，不能由 CLI 解析器猜測。
- `--dry-run` 的可驗證預覽由 Runner 和各 Handler 提供；本解析器只解析旗標，不承諾預覽功能已完成。
- `update apply` 由專門更新器執行來源校驗與安全確認；parser 只驗證版本字串的**基本語法**。
- 同一秒的檔名衝突、UUID、Context、Report Writer、SIGINT 處理由 B05／B09 處理。

## 安全與相容性

- 沒有使用 `eval`、`bash -c`、動態外部命令字串；任何不可信使用者配置都不能 `source`。
- 不需要 Bash 4 以上的 associative array、nameref 或 `mapfile`；目標是 Bash 3.2+。
- 沒有在測試中使用網路；測試只建立並刪除一個臨時私有目錄。
- 請在真實 macOS Bash 3.2／Debian／Alpine 上再執行測試；目前本地執行環境為 Bash 5，不能假裝已完成跨平台驗收。
