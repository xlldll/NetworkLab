# NetworkLab CLI 命令契約

- **規格識別**：A03 / CLI Contract v1
- **目標版本**：NetworkLab v0.1.0 Skeleton
- **狀態**：介面規格定稿；非功能實作完成宣告
- **適用系統**：macOS Client（C）；Linux Server（S，優先 Debian／Ubuntu／Alpine）

## 設計原則

1. **CLI 是核心，選單只是前端**：互動選單和手動命令必須調用同一組模組與執行器，不得維護兩套測試邏輯。
2. **入口固定**：只公開 `netlab-c` 與 `netlab-s` 兩個使用者命令；內部 `c/*.sh`、`s/*.sh` 亦須能獨立執行。
3. **預設安全**：未經明確允許，不自動執行高流量／高負載、開放測試服務、安裝或升級程式。
4. **真實狀態**：空模組必須回報 `NOT_IMPLEMENTED`；不可輸出虛假的成功測試報告。
5. **配置與資料持久化**：更新應保留 `~/.networklab/config/`、`results/`、`logs/`。
6. **CLI 字串穩定**：一旦 v0.1.0 發行，命令名稱、公開參數、退出碼改動須考慮向後相容。

## 命令文法

```text
netlab-c [command] [subcommand-or-id] [options]
netlab-s [command] [subcommand-or-id] [options]
netlab-c --help | --version
netlab-s --help | --version
```

- 命令、選項名稱一律 **小寫英文及 kebab-case**，區分大小寫。
- 長選項使用 `--key value`；布林旗標只寫 `--flag`。v0.1.0 **不保證**支援 `--key=value` 或短選項（如 `-p`）。
- 多參數順序可在同一命令內調換，例如 `paired --profile quick --target nat-us`。
- 未知命令、未知參數、重複且衝突的旗標、缺少參數值，一律拒絕，不得靜默忽略。
- `--help` 和 `--version` 不需要外部工具或有效目標配置；即使功能模組尚未實作，亦應成功回傳。
- 進入入口時 **沒有參數且 stdin 為 TTY**：開啟互動主選單；沒有參數且 **非 TTY**：顯示簡要用法並退出 `2`，絕不默默執行全部測試。

## C 端公開命令

| 指令 | 意義 | v0.1.0 狀態 |
|---|---|---|
| `netlab-c` | C 主選單 | 必須可用 |
| `netlab-c inventory` | Mac 本機盤點 | 保留入口 |
| `netlab-c standalone` | 公共網路獨立測試 | 保留入口 |
| `netlab-c paired --target ID` | 與指定 VPS 聯動測試 | 保留入口 |
| `netlab-c proxy` | Bettbox 代理與應用測試 | 保留入口 |
| `netlab-c collect --target ID` | 下載指定 VPS 測試結果 | 保留入口 |
| `netlab-c targets list` | 列出已配置 VPS | 必須可用 |
| `netlab-c targets show ID` | 檢視某台 VPS 的非敏感配置 | 必須可用 |
| `netlab-c targets add [欄位...]` | 互動新增 VPS，或透過完整旗標新增 | 必須可用 |
| `netlab-c targets edit [--editor nano\|vim]` | 以編輯器修改 VPS 清單 | 必須可用 |
| `netlab-c targets validate` | 檢查 VPS 清單格式、重複 ID 與數值 | 必須可用 |
| `netlab-c config edit [--editor nano\|vim]` | 編輯 C 設定 | 必須可用 |
| `netlab-c config validate` | 驗證 C 設定 | 必須可用 |
| `netlab-c results list` | 按時間列出本地測試結果 | 必須可用（可為空） |
| `netlab-c results show RUN_ID` | 檢視某次執行的索引／摘要 | 必須可用（不存在應報錯） |
| `netlab-c logs list` | 列出執行日誌 | 必須可用（可為空） |
| `netlab-c doctor` | 檢查平台與核心相依性 | 必須可用 |
| `netlab-c self-test` | 無網路的骨架自檢 | 必須可用 |
| `netlab-c update check` | 檢查新版本 | 必須可用 |
| `netlab-c update apply --version VERSION` | 從可信 Release/Tag 更新 | 必須可用 |

### C：`targets add` 欄位參數

```text
--name NAME            顯示名稱（可為繁體中文）
--id ID                穩定 target_id；亦為 JSON 名稱前綴
--type nat|direct      VPS 網路類型
--ipv4 IP              IPv4；無時留空欄位
--ipv6 IP              IPv6，可選
--iperf-port PORT      iperf3 的外部 TCP 控制連接埠
--mtr-port PORT        要追蹤的實際 TCP 服務埠
--ssh-alias ALIAS      ~/.ssh/config 內的別名，可選
```

- 目標清單格式固定為：`顯示名稱|target_id|nat/direct|IPv4|IPv6|iperf3外部埠|TCP MTR埠|SSH別名`。
- `--id` 建議只允許小寫字母、數字與連字號，長度 1–63；同一清單不得重複。
- 埠必須為 `1–65535`，IP 必須通過語法驗證；位址缺失應區分空欄位與欄位數量不足。
- `targets add` 在互動 TTY 下可逐項詢問；`--non-interactive` 則必須提供所有必要欄位，否則退出 `2`／`3`。
- CLI 對需要指定 VPS 的非互動測試要求明示 `--target ID`；不能依清單第一項默認對外執行測試。互動模式可以先顯示已存目標以供選擇。
- 變更配置後立即重新載入；SSH 金鑰、帳號和密碼不寫入 targets.conf。

## S 端公開命令

| 指令 | 意義 | v0.1.0 狀態 |
|---|---|---|
| `netlab-s` | S 主選單 | 必須可用 |
| `netlab-s inventory` | VPS 靜態配置／狀態快照 | 保留入口 |
| `netlab-s toolbox` | 公開工具選擇、執行、保存 | 保留入口 |
| `netlab-s service status` | 查詢聯動測試服務狀態 | 保留入口 |
| `netlab-s service start` | 啟動測試服務（安全控制） | 保留入口 |
| `netlab-s service stop` | 停止由本工具管理的測試服務 | 保留入口 |
| `netlab-s schedule list` | 查看定時任務 | 保留入口 |
| `netlab-s schedule add` | 新增定時任務 | 保留入口 |
| `netlab-s schedule edit JOB_ID` | 修改定時任務 | 保留入口 |
| `netlab-s schedule enable JOB_ID` | 啟用排程 | 保留入口 |
| `netlab-s schedule disable JOB_ID` | 停用排程 | 保留入口 |
| `netlab-s schedule run JOB_ID --non-interactive` | 排程器觸發無提示執行 | 保留入口 |
| `netlab-s schedule logs [JOB_ID]` | 查看排程執行日誌 | 保留入口 |
| `netlab-s config edit [--editor nano\|vim]` | 編輯 s.conf | 必須可用 |
| `netlab-s config validate` | 驗證 s.conf 與 Profile | 必須可用 |
| `netlab-s config profiles` | 列出 Quick／Standard／Deep 配置 | 必須可用 |
| `netlab-s results list` | 列出本機執行結果 | 必須可用（可為空） |
| `netlab-s results show RUN_ID` | 檢視執行索引／摘要 | 必須可用 |
| `netlab-s logs list` | 查看一般執行日誌清單 | 必須可用 |
| `netlab-s doctor` | 檢查依賴、權限和平台適配 | 必須可用 |
| `netlab-s self-test` | 無網路骨架自檢 | 必須可用 |
| `netlab-s update check` | 檢查新版本 | 必須可用 |
| `netlab-s update apply --version VERSION` | 更新固定版本 | 必須可用 |

- S 以 `s.conf` 的 `general.server_id` 識別本機，不使用 C 端 `--target`。
- `toolbox --modules netquality,tcpquality` 用**穩定模組 ID**，而不是數字選單編號。
- `--modules all` 僅表示該命令可用、允許的常規模組集合；高負載功能仍需額外授權。
- `schedule`、`service` 在 v0.1.0 **只保留命令入口**，不得建立真正排程或啟動連接埠。

## 共用參數契約

| 參數 | 值 | 行為 |
|---|---|---|
| `--help` | 無 | 顯示命令、參數、範例；退出 0 |
| `--version` | 無 | 顯示 NetworkLab 與 CLI 版本；退出 0 |
| `--profile` | `quick\|standard\|deep` | 測試程度；預設讀取角色配置，無配置時為 `standard` |
| `--config` | 絕對／相對檔案路徑 | 覆蓋本次角色主配置（C 的 c.conf 或 S 的 s.conf），不覆蓋原始檔 |
| `--output-dir` | 目錄路徑 | 覆蓋本次結果**根目錄**，內部仍按角色／目標分類 |
| `--non-interactive` | 無 | 不讀取 stdin、不開啟編輯器、不提示選擇；缺參數立即失敗 |
| `--quiet` | 無 | 減少普通進度輸出；保留錯誤、退出碼、日誌與結果檔 |
| `--dry-run` | 無 | 驗證與展示實際生效參數和預計操作，不執行測試或改變系統 |
| `--target` | `target_id` | C 端 `paired`、`collect` 的必要目標識別 |
| `--modules` | `ID,ID` 或 `all` | 只適用有多項測試的命令（如 S `toolbox`） |
| `--editor` | `nano\|vim` | 只適用 `config edit`／`targets edit` |
| `--limit` | 正整數 | 用於 `results list` 等列表命令；預設 20 |

- **適用性判定**：`--profile` 等僅對有意義的命令有效。對無關命令使用不適用旗標應顯示用法錯誤 `2`，而非靜默忽略。
- **優先序**：本次 CLI 顯式參數 > `~/.networklab/config/` 的使用者設定 > 程式內建預設；S 個別工具覆寫高於該工具的 Profile 預設。
- **乾跑定義**：不進行網路測速、不安裝軟體、不啟動或停止服務、不新增排程、不覆蓋檔案；可以讀取本地設定。尚未實作的模組即使帶 `--dry-run`，也必須顯示 `NOT_IMPLEMENTED` 並退出 `8`，不得假裝已有測試執行計畫。
- **執行器**：選單選項應轉譯成同一組命令參數後交給 runner，不可繞過驗證器直接執行測試程式。
- **高負載保護**：`deep` 不等於自動授權高流量。高負載功能需要 s.conf 明確允許、可追溯的交互確認；非互動排程必須使用預先配置的明確流量與資源預算，否則拒絕並退出 `9`。v0.1.0 不實作高負載執行。

## 執行輸出與退出碼

### 人可讀輸出

- `stdout`：選單、進度、結果路徑、成功訊息；`stderr`：參數錯誤、異常與安全拒絕。
- `--quiet` 不隱藏不可恢復錯誤，也不改變狀態碼。
- 每次正式測試的報告包含 `role`、`module`、`run_id`、`started_at`、`finished_at`、`status`、`profile`（適用時）、`target_id`（適用時）、有效參數與原生檔案索引。
- 報告中的時間及檔名一律輸出 UTC+08:00，精確到秒，不修改系統時區。
- 報告狀態值固定：`completed`、`failed`、`timeout`、`skipped`、`interrupted`、`partial`、`not_implemented`。

### CLI 退出碼（公開穩定介面）

| Code | 名稱 | 定義 |
|---:|---|---|
| `0` | `SUCCESS` | 命令完成；測試命令只有實際完成才可回傳 |
| `2` | `USAGE_ERROR` | 命令、參數、缺少參數值或語法錯誤 |
| `3` | `CONFIG_ERROR` | 設定檔格式／必需欄位／無效目標 |
| `4` | `DEPENDENCY_MISSING` | 必須的外部程式或環境缺失 |
| `5` | `EXECUTION_FAILED` | 執行失敗、IO／網路操作失敗 |
| `6` | `TIMEOUT` | 命令逾時（由執行器映射） |
| `7` | `PARTIAL` | 批次／集合任務只有部分成功，或有部分項目被跳過 |
| `8` | `NOT_IMPLEMENTED` | 存在正式入口，但尚無功能實作 |
| `9` | `SAFETY_BLOCKED` | 權限不足、未授權高成本或不安全操作 |
| `10` | `BUSY` | 相同服務或衝突排程正在執行 |
| `130` | `INTERRUPTED` | 由 SIGINT／Ctrl+C 中斷；保留已有結果 |

- 子模組由 runner 呼叫時，其退出碼必須映射為相同的 `status` 字串，寫進執行日誌。
- 批次中若至少一項成功且另有失敗／跳過，退出 `7`；全部失敗時傳回相應的錯誤碼並保留各項狀態；全部真正成功才退出 `0`。
- 命令不適用、不支援或缺少配置時不應通過 `0` 假裝已經完成測量。

## 本地路徑與資料規則

```text
~/.networklab/
├── app/                 # GitHub 安裝程式碼，可升級
├── config/              # c.conf、targets.conf、s.conf；升級不得覆蓋
├── results/
│   ├── c/local/         # C 本機結果
│   ├── c/<target_id>/   # C↔S 結果
│   ├── c/proxy/         # 代理測試
│   ├── s/<server_id>/   # S 本機結果
│   └── imported/<id>/   # C 從 S 下載的副本
└── logs/
```

- 只建立當前角色需要的目錄。`--output-dir` 指向新的 **results 根目錄**，不直接替換某一份報告檔名。
- 檔名遵守 `<role>-<test>[-<id>]-YYYY-MM-DD-HH-mm-ss.<ext>`；同秒衝突加 `-01`、`-02`，不覆蓋。
- 每次執行有唯一 `run_id`；在扁平目錄中 `manifest`、`summary` 亦要帶角色／目標／時間（必要時衝突尾碼），避免覆蓋。
- S 結果原本保留在 S，C 匯入時另建副本；C 的 SSH 別名由 `~/.ssh/config` 管理。
- 所有 JSON 使用原子寫入；結果保留第三方工具原生資料、stderr、stdout、實際退出碼、工具版本與檔案雜湊。
- `NETLAB_HOME` 可作為**測試環境的可選覆寫**，若使用必須為絕對路徑；Linux 排程必須以固定帳號及路徑執行，不能在一般使用者與 root 之間意外分叉資料目錄。

## v0.1.0 最小驗收案例

```bash
# 應回傳 0
netlab-c --help
netlab-c --version
netlab-c targets list
netlab-c targets validate
netlab-c config validate
netlab-c self-test
netlab-s --help
netlab-s config validate
netlab-s config profiles
netlab-s self-test

# 在骨架階段應回傳 8 (NOT_IMPLEMENTED)，絕非成功
netlab-c paired --target nat-us --profile standard
netlab-s toolbox --profile quick --modules netquality
netlab-s schedule list

# 應回傳 2 或 3，且不執行真實測試
netlab-c paired --target unknown-vps --non-interactive
netlab-c standalone --profile invalid
netlab-s toolbox --unknown-flag

# 正確命令形式，待對應功能實作後生效
netlab-c paired --target nat-us --profile standard --non-interactive --quiet
netlab-c collect --target nat-us
netlab-s toolbox --modules netquality,tcpquality --profile standard --non-interactive --quiet
netlab-s update check
```

> 注意：`nat-us` 必須已存在於本機 `targets.conf`；否則即使 `paired` 尚未實作，命令仍可先依規則回報配置錯誤 `3`。測試時應先設定好 fixture（測試用配置）。

## 此契約不包含的實作

- 不實作任何實際網路測量、第三方工具執行、IP 探測、SSH 抓取或代理測試。
- 不在 v0.1.0 啟動 `iperf3` 伺服器、systemd Timer 或 cron。
- 不允許以擅自啟動外部服務的方式驗證骨架。
- 不把其他人的公開腳本原始碼複製進 NetworkLab；後續以獨立依賴／適配器調用並記錄相應授權。

**A03 完成定義**：雙入口命令表、參數語法與適用性、行為與優先序、退出碼、錯誤與未實作狀態、非互動契約及測試案例已固定，後續 A04／A06／B02／B05／B11 均以本文件為依據。
