# NetworkLab B08：Server 配置管理（增量實作）

- **版本**：B08 / NetworkLab Skeleton v0.1.0
- **前置依賴**：B01–B07 已安裝。沿用 A03–A08 CLI、S INI 與模組契約。
- **範圍**：只負責 `s.conf` 解析、驗證、顯示及安全編輯，不安裝、不下載、不啟動網路測試或定時器。

## 交付檔案

| 檔案 | 用途 |
|---|---|
| `lib/server_config.py` | 新增：S 端 INI 驗證、三組 Profile、工具覆寫、成本限制、排程檢查、安全編輯 |
| `lib/runner.sh` | 修改：`netlab-s config` 交由 S 配置管理器，不建立測試 Run |
| `lib/runner_host.py` | 修改：S 模組啟動前使用 B08 完整驗證器；向 Context 傳遞有效的 Profile／預算 |
| `tests/test-b08.py` | 新增：13 組離線測試 |
| `tests/test-b08-all.sh` | 新增：B01–B08 整合測試入口 |
| `tests/test-b05.py`, `tests/test-b06.py`, `tests/test-b03-b04.py` | 修訂：S 測試 fixture 補上 A05 必填 config_version／timezone |
| `docs/implementation-b08.md` | 本說明 |

本增量**不覆蓋** `~/.networklab/config/s.conf`，也不應覆蓋使用者現有的 `defaults/`、A01／A02／A09 文件。

## 實際使用

1. 在 VPS 的 NetworkLab Repository 根目錄，先檢查 `~/.networklab/config/s.conf` 是否已存在。B12 安裝器尚未開發，若未初始化，可使用：

   ```sh
   mkdir -p "$HOME/.networklab/config"
   cp -n defaults/s.conf "$HOME/.networklab/config/s.conf"
   chmod 700 "$HOME/.networklab" "$HOME/.networklab/config"
   chmod 600 "$HOME/.networklab/config/s.conf"
   ```

2. `defaults/s.conf` 中的 `server_id = CHANGE_ME` **必須手動改成該 VPS 唯一的小寫 ID**，例如 `nat-us`。`CHANGE_ME` 不允許通過驗證。

3. 執行：

   ```sh
   bash netlab-s.sh config validate
   bash netlab-s.sh config profiles
   bash netlab-s.sh config edit --editor nano
   bash netlab-s.sh toolbox --modules netquality --profile standard --dry-run
   ```

   最後一項目前仍返回 `NOT_IMPLEMENTED (8)`，表示尚未整合第三方工具，**不是已成功測速**。

4. 執行完整離線測試：

   ```sh
   bash tests/test-b08-all.sh
   ```

## 配置解析規則

- 不執行 `source`、`eval` 或任何任意 Shell 指令；使用 Python 3 stdlib `configparser(interpolation=None, strict=True)`。
- 檢查 `config_version=1`、合法 `server_id`、`timezone=UTC+08:00`、布林值、Profile 選項、已知工具欄位、非負預算及有效排程規則。
- 工具 Profile 模式（`off/lite/normal/full`）是抽象配置，不是公開腳本參數。未實作 Adapter 時不得執行。
- 未指定工具鍵時按 A05 內建預設補足，可在 `config validate` 顯示提醒。
- `max_metered_mb_per_run/day=0` 代表**沒有高流量測試配額**，不是無限流量。
- `[schedule.*].enabled=true` 只作為資料驗證及提醒；B08 **不建立 systemd timer 或 cron**，未來執行仍要通過安全確認。
- `--config FILE` 僅覆寫本次讀取路徑，不改寫預設配置。
- `config edit` 只允許 nano／vim，且必須在 TTY 中操作；先修改候選副本，驗證通過才在鎖定狀態下原子替換，並建立私有備份。修改無效則保持正式配置不變。即使正式配置已無效，也允許透過編輯器修復。
- S 的 Runner 執行 `inventory`／`toolbox` 等模組前會先使用同一套 S 配置驗證，避免驗證功能與實際模組採用不同規則。

## 測試範圍與限制

- **本地已驗證**：B01–B07 回歸測試、13 組 B08 測試、Bash 語法和 Python 語法。
- **尚未驗證**：真實 macOS Bash 3.2、Debian／Ubuntu／Alpine 實機、B12 正式安裝流程。
- **未實作**：第三方測速工具的參數 Adapter、流量實際記帳、排程啟停、正式 Report Writer（B09）。
