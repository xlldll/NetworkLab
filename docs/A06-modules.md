# NetworkLab 模組調用與執行契約

- **規格識別**：A06 / Module Invocation Contract v1
- **目標版本**：NetworkLab v0.1.0 Skeleton
- **狀態**：介面規格定稿；不是模組調度器或測速功能已實作的聲明
- **上游依據**：`docs/commands.md`（A03）、`docs/menus.md`（A04）、`docs/configuration.md`（A05）
- **下游依據**：A07 報告 Schema、B01/B02 共用函式與 CLI、B05 Runner、B06 九個模組佔位入口
- **平台**：C = macOS；S = Linux（優先 Debian、Ubuntu、Alpine）

## 一、目標與邊界

A06 只確定**九個功能模組如何被呼叫、取得已驗證參數、執行、回報狀態及交付輸出**。無論來自互動選單、CLI、未來排程，還是直接執行模組檔案，都必須走同一套共用驗證與執行流程。

基本原則：

1. **唯一公開入口**：一般使用者使用 `netlab-c`、`netlab-s`。`c/*.sh`、`s/*.sh` 保留可直接執行能力，但不是第二套 CLI 規格。
2. **Runner 管流程，Module 管職責**：共用 Runner 管參數、配置、身份、工作目錄、逾時、中斷、進度與最終狀態；模組只負責領域操作與產生原生資料。
3. **配置是資料**：所有參數先依 A05 解析／驗證，不能 `source targets.conf`、`eval` 配置或拼接一整段 Shell 命令。
4. **可用能力逐項判斷**：缺少可選工具只跳過受影響的測試項，不能使全部模組必然失敗。
5. **無副作用的預覽**：`--dry-run` 只驗證與預覽；骨架的佔位模組即使帶 `--dry-run` 仍回報未實作。
6. **可追溯但不捏造**：不得把模組啟動成功當成測量成功；`NOT_IMPLEMENTED`、`skipped`、`partial` 都必須與 `completed` 區分。
7. **安全隔離**：模組不得擅自更新系統、開放公網服務、改寫 Xray／sing-box、刪除其他模組資料或跨越指定輸出目錄。

### A06 不處理的內容

- 不制定各測試的實際 iperf3、NetQuality、MTR 或 Bettbox 命令。
- 不制定最終測試結果 `metrics` 的完整 Schema（交給 A07）。
- 不實作任何聯動服務、定時器、SSH 下載、公開工具適配器。
- 不把第三方公開腳本原始碼複製到 Repository。

## 二、分層調用結構

```text
[互動選單] 或 [使用者 CLI] 或 [排程器（未來）]
                    │
                    ▼
            CLI Router / Parser
                    │
                    ▼
       共用配置解析與參數驗證（A05）
                    │
                    ▼
       Runner（唯一執行／生命週期管理者）
         │           │              │
         │           │              └─ 執行日誌／逾時／中斷
         │           └─ 產生執行 Context 與私有工作區
         ▼
       經白名單映射的 c/*.sh 或 s/*.sh
                    │
                    ▼
       模組自身工作：盤點／測試／服務／收集
                    │
                    ▼
       原生檔案 + 模組回傳狀態 + 結構化摘要
                    │
                    ▼
       Runner／Report Writer（A07）
                    │
                    ▼
       結果檔、manifest／summary、stdout／stderr、退出碼
```

> 直接執行 `./c/c-paired.sh ...` 或 `./s/s-toolbox.sh ...` 時，外層模組入口**先轉交同一個 Runner**。Runner 再以明確的內部工作模式呼叫該模組的實作入口；這個內部工作模式不能跳過安全驗證，避免遞迴呼叫或繞開控制。具體的內部旗標／呼叫方式由 B05 實作，不增加未定義的公開 CLI 旗標。

禁止選單直接執行 `iperf3 ...`、`curl ... | bash`，或繞開 Runner 自行寫正式結果。

## 三、九個模組的穩定 ID 與檔案映射

| 角色 | 公開 CLI 子命令 | 穩定模組 ID | 路徑 | 任務型態 | v0.1.0 |
|---|---|---|---|---|---|
| C | `inventory` | `c-inventory` | `c/c-inventory.sh` | measurement | NOT_IMPLEMENTED |
| C | `standalone` | `c-standalone` | `c/c-standalone.sh` | measurement | NOT_IMPLEMENTED |
| C | `paired` | `c-paired` | `c/c-paired.sh` | measurement | NOT_IMPLEMENTED |
| C | `proxy` | `c-proxy` | `c/c-proxy.sh` | measurement | NOT_IMPLEMENTED |
| C | `collect` | `c-collect` | `c/c-collect.sh` | transfer | NOT_IMPLEMENTED |
| S | `inventory` | `s-inventory` | `s/s-inventory.sh` | measurement | NOT_IMPLEMENTED |
| S | `toolbox` | `s-toolbox` | `s/s-toolbox.sh` | measurement (batch) | NOT_IMPLEMENTED |
| S | `service` | `s-service` | `s/s-service.sh` | management | NOT_IMPLEMENTED |
| S | `schedule` | `s-scheduler` | `s/s-scheduler.sh` | management / dispatch | NOT_IMPLEMENTED |

- 穩定模組 ID 與選單畫面的數字無關。
- `netquality`、`tcpquality`、`hardwarequality`、`ipquality`、`nexttrace`、`mtr`、`flent` 是 **s-toolbox 的工具 ID**，不是另外七個頂層模組。
- `targets`、`config`、`results`、`logs`、`doctor`、`self-test`、`update` 是**管理型 CLI 處理器**，不算進九個測試／管理模組；同樣要遵守 A03 退出碼和配置驗證規則。
- `service status`、`schedule list` 等查詢動作日後成功時不必偽造測量報告；真正有測量／匯入行為才建立相應結果紀錄。
- v0.1.0 的所有九個模組仍為佔位腳本，不建立正式測試報告、公開服務或排程。

### 模組專屬輸入

| 模組 | 必須或可選參數 | 特別規則 |
|---|---|---|
| `c-inventory` | 通用 `--output-dir` 等適用選項 | 無需 VPS；不能因無目標清單而失敗 |
| `c-standalone` | `--profile` | 無需 VPS；公共目標的實際集合日後在模組定義 |
| `c-paired` | **非互動時必須** `--target ID`；`--profile` | ID 必須已存在於 `targets.conf`；依 NAT/direct 與 IP Family 生效 |
| `c-proxy` | `--profile` | 從 `c.conf` 讀本機代理入口；不保證指定代理出口 |
| `c-collect` | **非互動時必須** `--target ID` | SSH alias 可選配置，但實際收集前必須核對可用通道 |
| `s-inventory` | 通用選項 | 使用有效 `server_id`；不能以 `CHANGE_ME` 執行 |
| `s-toolbox` | `--modules ID,ID` / `all`、`--profile` | 工具 ID 白名單；`all` 不自動包含高負載任務 |
| `s-service` | `status` / `start` / `stop` | `start`／`stop` 是受保護的系統變更；不得影響既有代理程序 |
| `s-scheduler` | `list` / `add` / `edit` / `enable` / `disable` / `run` / `logs` | `run JOB_ID` 未來只透過相同 Runner 觸發測試；v0.1.0 不建立 Timer／cron |

通用選項只在 A03 認可的命令上有效。`--target`、`--modules` 不可無條件傳給所有模組；不適用旗標退出 `2`。

## 四、統一呼叫與參數優先序

### 使用者 CLI 範例（v0.1.0 只作接口示範）

```bash
# C：明確指定目標
netlab-c paired --target nat-us --profile standard --non-interactive

# S：指定公共工具 ID
netlab-s toolbox --modules netquality,tcpquality --profile quick --non-interactive

# 直接呼叫模組，必須與入口走同一 Runner 規則
./c/c-paired.sh --target nat-us --profile standard --non-interactive
./s/s-toolbox.sh --modules netquality --profile quick --non-interactive
```

**生效配置順序**（承接 A03/A05）：

1. 使用者本次明確提供的 CLI 參數。
2. 由 `--config` 選擇的角色配置，否則本地 `~/.networklab/config/`。
3. 程式內建安全預設值。
4. **S 工具例外**：每個工具先套用 `[tool.ID].enabled` 和 `profile_override`，再從生效的 `[profile.X]` 取 `off/lite/normal/full`；不改變其他工具設定。

此清單並非允許單工具覆寫一切安全策略。全域安全限制、權限、預算與實際可用性是後續**獨立檢查**，不因 Profile 或 `--modules all` 被繞過。

### 非互動執行

- `--non-interactive`：禁止 `read`、`select`、nano/vim、任何確認提示；缺必要參數直接報 `2`／`3`。
- 非 TTY 環境不能把第一台 VPS 當作預設目標；C 的 paired／collect 必須明確使用 `--target`。
- 排程器將來提供完整配置和預算，交由相同 CLI／Runner 執行；不能另做一版「排程專用測速」。
- `--quiet` 僅控制人可讀輸出，不改變原生結果、狀態、日誌或錯誤碼。

### Dry-run（預覽）

- 允許讀取本地配置、確認工具是否已安裝、列出安全範圍內的預計操作與有效參數。
- **不允許**：測速網路流量、SSH 登入、外部工具實際執行、配置修改、安裝更新、啟停服務、建立排程、寫正式測試結果。
- 若相應模組在 v0.1.0 尚未實作，明確輸出 `NOT_IMPLEMENTED` 並退出 `8`；不得產生假的測試命令或假的成功結果。
- 完整 `--help`、`--version` 在配置損壞時仍應退出 `0`；其他調用需先通過適用的 CLI／配置驗證。

## 五、Runner 建立的執行 Context（模組輸入契約）

模組**不應重複解析整份 INI／targets.conf**。Runner 負責讀取、驗證、標準化並固定一份當次有效的執行快照；即使用戶在測試期間修改配置，也不能悄悄改變同一 Run 的參數。

### 建議的傳遞方式

- Runner 將本次執行上下文寫入**私有臨時工作目錄**（建議 0700），產生一份 UTF-8 JSON Context；檔案權限 0600。
- 模組透過 `NETLAB_CONTEXT_FILE` 取得該 JSON 的絕對路徑；透過 `NETLAB_WORK_DIR` 取得本次受控工作區。
- Context 包含已驗證的非敏感目標 IP／Port／模式／Profile；不包含 SSH 私鑰、密碼、代理 Token 等秘密值。
- `NETLAB_CONTEXT_FILE`、`NETLAB_WORK_DIR` 是**內部調用協定**，不是新的公開 CLI 參數，也不能當作安全授權的唯一依據。
- Context 在**一次正式執行開始**時固定；程序崩潰後是否保留工作區，由 Runner／A07 的故障留存規則決定。
- 多工具集合執行可共享 `run_id`，每個子項另有穩定 `test_id`，便於比較與校驗。

### Context 最小欄位（A06 固定）

```json
{
  "contract_version": 1,
  "role": "C",
  "module_id": "c-paired",
  "run_id": "2026-10-21-18-31-05-nat-us",
  "task_kind": "measurement",
  "profile": "standard",
  "target_id": "nat-us",
  "server_id": null,
  "selected_modules": [],
  "non_interactive": true,
  "quiet": false,
  "started_at": "2026-10-21T18:31:05+08:00",
  "paths": {
    "result_root": "/home/example/.networklab/results",
    "work_dir": "/home/example/.networklab/tmp/run-example"
  },
  "target": {
    "display_name": "美西NAT",
    "type": "nat",
    "ipv4": "198.51.100.10",
    "ipv6": null,
    "iperf3_external_tcp_port": 48801,
    "tcp_mtr_port": 443,
    "ssh_alias": "nat-us"
  },
  "effective_parameters": {}
}
```

**範例僅示意結構，非測量結果。** `paths` 僅說明當次執行空間；不同角色／系統的路徑不同，不能硬編碼成上述 `/home/example`。`run_id` 精確格式與撞名規則由 A07 定稿；這裡只要求同一 Run 唯一且穩定。`role=S` 時應填入有效 `server_id`，`target` 可為 `null`。

Context 禁止包含代表未知資料的假數值；未提供欄位使用 `null` 或明確缺省，不得將未知 CPU、Loss、Bandwidth 寫成 `0`。

## 六、模組回傳契約：狀態、檔案與標準輸出

### 退出碼（沿用 A03，不重新編號）

| Code | 名稱 | 何時使用 |
|---:|---|---|
| 0 | `SUCCESS` | 該命令／測試所有要求的工作確實成功 |
| 2 | `USAGE_ERROR` | CLI 形式、未知選項、缺少值 |
| 3 | `CONFIG_ERROR` | 配置、target_id、server_id 無效 |
| 4 | `DEPENDENCY_MISSING` | 必要依賴缺失，無法完成要求 |
| 5 | `EXECUTION_FAILED` | 執行／IO／網路錯誤 |
| 6 | `TIMEOUT` | 達到允許時限 |
| 7 | `PARTIAL` | 至少一項成功且另有失敗或被跳過 |
| 8 | `NOT_IMPLEMENTED` | 已註冊但尚無實際功能 |
| 9 | `SAFETY_BLOCKED` | 權限／成本／授權等安全條件未過 |
| 10 | `BUSY` | 與現有任務或服務互相衝突 |
| 130 | `INTERRUPTED` | SIGINT／Ctrl+C 中斷 |

- Runner 將退出碼轉成 `completed`、`failed`、`timeout`、`partial`、`not_implemented`、`interrupted` 等 A03 狀態，並保留**原始子程序退出碼**。
- **`skipped` 是單個子測試的結果狀態，不應被當成完整測量成功**。整批部分成功、部分跳過／失敗時退出 `7`。若請求的項目全部無法實際執行，回傳適用的非零原因（例如 4／8／9），不可用 0 表示「已跳過全部」。
- `toolbox --modules all` 先展開為**允許的常規工具集合**；明確配置為 `off`、使用者未選擇的工具不屬於「本次被要求的測試」，不必無謂地把整批標為 partial。
- 如多項全部失敗，Runner 應保留每項的失敗原因；整體返回適用的非零錯誤碼（異質失敗可用 `5`），不得取第一個工具的錯誤就丟失其他證據。

### stdout、stderr 與資料檔分流

| 通道 | 用途 | 約束 |
|---|---|---|
| `stdout` | 人類可讀的進度、摘要、結果位置 | 不作正式 JSON 傳輸通道 |
| `stderr` | 錯誤、警告、缺少依賴 | `--quiet` 仍保留致命錯誤 |
| 私有工作區 | 原始 JSON／TXT／NDJSON、應用測試輸出 | 禁止任意寫入其他 Run 目錄 |
| 模組結構化交付 | 原始檔索引、局部指標、錯誤與警告 | 不直接取代最終 `manifest`／`summary` |
| Runner 日誌 | 起迄時間、退出碼、狀態、工具及參數摘要 | 不記錄憑證、私鑰與 Token |

為避免模組與 Runner 重複決定報告格式，**正式 manifest、summary、報告檔名及原子寫入只由 Runner／`lib/report.py` 負責**（詳細結構由 A07 確定）。模組可交付原生檔案及暫存的結構化摘要，但不能單獨宣稱其為標準報告。

### 模組交付的最小語義（A07 將定義格式）

- `module_id`、當次 `run_id` 與 `test_id`（有子測試時）一致。
- 每個子測試都要能說明 `status`、實際測量條件、使用的工具與版本（若可取得）、原生檔案所在位置。
- 可以提供 `metrics`、`warnings`、`errors`；尚未量測或不可得的指標使用 `null`／空集合，不能以 0 代替。
- 路徑必須在 Runner 指定的工作區內，不能將絕對主機機密路徑硬塞進可分享報告。
- 支援 `evidence_scope`：`local`／`public_path`／`c_s_direct`／`proxy_path`／`third_party_service`（由 A07 確定最終 Schema）。

## 七、生命週期、Timeout 與 Ctrl+C

### 生命週期

```text
request
  → CLI 解析
  → 配置驗證
  → 能力／安全預檢
  → module mapping
  → 建立 session／私有工作區（只對正式執行）
  → 啟動子程序
  → 蒐集 stdout、stderr、狀態與原生資料
  → Finalize（成功／失敗／部分完成／中斷）
  → 返回 A03 CLI 退出碼
```

- 主入口只使用**固定白名單**解析模組 ID 對應路徑；不能把未驗證的使用者字串拼成任意腳本路徑。
- 每次正式**測量**建立一個 `run_id`；同一批子測試共享 ID，個別子項記錄自身狀態。
- 對於 `service status`、`schedule list` 等**查詢**操作，不建立假的 measurement session；管理變更由管理型日誌記錄。
- `c-collect` 屬資料傳輸，完整保存匯入檔案、來源及校驗；不將「下載成功」視為「測量數據正確」。
- 缺少非必要工具時，只跳過其相依子測試，其他測試依可用性繼續；實際成功、跳過、失敗的統計必須可追溯。

### Timeout

- Runner 控制**單項 timeout** 和**整批執行總 timeout**；哪個先到就終止該範圍。
- Timeout 數值與預算依 Profile／模組定義；本階段**不捏造**各測量工具的秒數。
- macOS 不保證內建 GNU `timeout`，Alpine／Debian 服務環境亦不同；B05 必須用可攜方式實作或明確驗證依賴，不能硬寫 `timeout` 指令。
- 超時時保留已有原生結果與錯誤日誌，退出碼 `6`。不應粗暴殺掉非 NetworkLab 建立的服務。

### SIGINT／SIGTERM

- `Ctrl+C`／SIGINT：停止啟動後續子項，將中斷傳達給**本次 Runner 管理的子程序**，完成資料封存，退出 `130`。
- SIGTERM：同樣嘗試保留已完成資料；由 Runner 按信號與場景對外傳回適用的非零退出碼（慣例可用 `143`，但 A03 未將其列為公開穩定狀態）；不得誤報成功。
- 應有安全清理機制，清理**只由本次執行建立**的暫存程序／檔案；不刪除其他 Run 或既有 Xray／sing-box 程序。
- 避免直接 `kill 0` 或廣泛按程序名稱 `pkill iperf3`；透過本次程序 PID／受控程序群辨識擁有權。
- 任何故障封存都不保證在 `SIGKILL`、斷電或檔案系統故障時完成；A07 應透過原子寫入降低損壞風險。

## 八、權限、網路與第三方工具邊界

1. **最小權限**：Inventory 等唯讀功能預設以一般使用者執行；確實需要權限的操作才提示，絕不隱藏執行 `sudo`。
2. **服務啟停**：`s-service` 只能控制由 NetworkLab 建立及登記的測試程序；不得改寫既有 Xray／sing-box 或任意開放公網端口。
3. **測量與流量預算**：高負載／按流量計費操作必須通過 A03/A05 安全策略；`deep` 不代表已授權。
4. **敏感資訊**：SSH 身分、金鑰、代理認證不放在 Context 或可分享報告；不能在 `set -x` 輸出中曝光。
5. **第三方腳本**：外部工具由適配器以固定 ID、可信來源及受審查參數調用；記錄版本、授權和檔案雜湊。不默認 `curl | bash` 執行浮動最新版本。
6. **輸出路徑**：模組只能使用 Runner 給出的私有工作區，檔案名與目標 ID 已驗證，不接受 `../../` 路徑穿越。
7. **多台 VPS**：C 的 `target_id` 在整個 Run 期間固定；不能在一次測試中因配置被編輯就切換 IP 或 Port。

## 九、v0.1.0 佔位模組的精確行為

選單、CLI 和直接呼叫模組時，結果一致。例如：

```text
[NetworkLab] C Paired
Module: c-paired
Version: 0.1.0
Status: NOT_IMPLEMENTED

This module is not available yet.
Exit code: 8
```

要求：

- `--help`／`--version` 應可顯示已定義的介面並退出 `0`，不需要有效配置。
- 一般調用先做必要的**CLI 語法和配置檢查**；若指定不存在的 `target_id`，應先報 A03 的 `CONFIG_ERROR`（3），而不是掩蓋為未實作。
- 通過預檢後的實際執行請求回傳 `NOT_IMPLEMENTED`（8），不啟動外部工具，不開放任何測試服務。
- `--dry-run` 在尚未實作的模組亦回傳 `8`，可以顯示「未提供可驗證的執行計畫」，不得印出虛構命令。
- 不建立假的成功 manifest／summary 或測量結果；可留下必要的**入口錯誤日誌**，但 `results list` 應仍為空（self-test 測試資料另存隔離目錄）。
- 選單接住退出 `8`，顯示清楚提示，返回上一層供下一次操作，不使整個入口退出。

## 十、驗收測試矩陣（供 B05／B06／C04）

| 案例 | 操作 | 預期 |
|---|---|---|
| M01 | `netlab-c inventory --help` | 退出 0；不要求有效 c.conf |
| M02 | `./c/c-inventory.sh --help` | 與 M01 一致 |
| M03 | `netlab-s toolbox --version` | 退出 0；顯示版本 |
| M04 | `netlab-c paired --target nat-us`（已配置有效 ID） | 退出 8，NOT_IMPLEMENTED |
| M05 | `./c/c-paired.sh --target nat-us`（相同配置） | 與 M04 一致 |
| M06 | `netlab-c paired --target missing-id --non-interactive` | 退出 3；不執行測試 |
| M07 | `netlab-c standalone --profile invalid` | 退出 2；不執行測試 |
| M08 | `netlab-s toolbox --modules netquality --dry-run` | 退出 8；不輸出虛假測試計畫 |
| M09 | `netlab-s service start` | 退出 8；端口不變、服務不啟動 |
| M10 | `netlab-s schedule enable peak` | 退出 8；不建立 cron／Timer |
| M11 | `netlab-s toolbox --unknown-flag` | 退出 2 |
| M12 | `netlab-c self-test` | 退出 0；僅在隔離目錄生成模擬資料 |
| M13 | 菜單選取 C3，再選有效 VPS | 正確派發 `c-paired`、退出 8、返回選單 |
| M14 | 使用不同本地配置並測試 `--config` | 使用本次選定的配置，不修改預設配置 |
| M15 | 用 `NETLAB_HOME` 指到臨時絕對路徑 | 使用隔離目錄，不碰真實 `~/.networklab` |
| M16 | `--quiet` 呼叫佔位模組 | 可減少進度，但退出碼仍為 8，錯誤可見 |
| M17 | 非 TTY 無參數呼叫 `netlab-c` | 退出 2，顯示用法，不開選單 |
| M18 | `netlab-s config validate`（有效 s.conf） | 退出 0；不執行 S 模組 |

以上測試描述的是**驗收標準**，不是宣稱目前已通過。

## 十一、A06 與 A07／Phase B 的責任劃分

| 範圍 | A06 現在固定 | 留待後續 |
|---|---|---|
| 公開命令 | 沿用 A03，模組 ID／白名單映射固定 | B02 編寫 Parser |
| 選單派發 | 沿用 A04，轉交 CLI／Runner | B03／B04 實作 |
| 配置 | 沿用 A05，先解析後快照 | B07／B08 實作驗證器 |
| Runner | 統一 Context、工作區、逾時、信號、退出碼 | B05 實作 |
| 模組 | 九個檔案／輸入輸出／狀態固定 | B06 建立佔位腳本，v0.2+ 補上測量 |
| 報告 | Runner 主導，不由模組各自寫最終 Schema | **A07** 訂定 manifest、summary、raw 結構 |
| 版本與安全 | 外部依賴不直接內嵌；不跳過確認 | B12／B13 安裝更新，A09 授權盤點 |

**A06 完成定義**：九個模組 ID 與職責、直接執行和入口調用一致性、參數傳遞、Runner Context、返回狀態、輸出責任、Timeout／中斷、模組邊界及 v0.1.0 佔位行為均已固定。下一項 A07 應將 `run_id`、`manifest`、`summary`、原生檔案、UTC+8 檔名和 evidence_scope 轉化為正式報告 Schema。
