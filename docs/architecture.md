# NetworkLab 核心技術架構

- **規格識別**：A08 / Architecture Contract v1.0
- **目標產品版本**：NetworkLab v0.1.0 Skeleton
- **文件狀態**：Phase A 架構整合規格完成；**不代表 CLI、安裝器、Runner 或網路測試已實作**
- **依據**：A03 `docs/commands.md`、A04 `docs/menus.md`、A05 `docs/configuration.md`、A06 `docs/modules.md`、A07 `docs/report-schema.md`
- **適用角色**：C = macOS Client（Apple Silicon／Intel）；S = Linux VPS（優先 Debian／Ubuntu／Alpine）
- **指導原則**：先建立可用的程式骨架，再逐一填入網路測試實作；CLI 與本地資料契約相對穩定，測試內容可持續擴充。

## 一、系統定位與設計邊界

NetworkLab 是以 **Client／Server（C／S）** 為核心的網路測試、採集與結果保存系統，而不是單一測速腳本或 AI 自動評分器。其工作是建立可再現、可追溯、可比較的測量證據。

五項長期能力：

- **Inventory**：C／S 環境、設備、系統與可觀察限制的盤點。
- **Standalone**：不依賴另一端的獨立公共網路測試。
- **Paired**：C ↔ S 真正端到端路徑的聯動測試。
- **Evidence Collection**：保存原生測量資料、工具版本、參數、狀態與上下文。
- **Historical Comparison**：讓其他分析程序按相同證據範圍比較不同 VPS、時間與網路環境。

必須維持三項因果邊界：

1. 配置不等於實際性能：4 vCPU、BBR、虛擬 NIC 1 Gbps 不能證明跨境吞吐。
2. 公共節點測試不等於 Mac ↔ VPS 路徑：S → 公共廣東節點的路由不能代替 S → 特定家庭網路。
3. 原生路徑不等於代理完整應用路徑：iperf3、Bettbox、CDN／YouTube／AI 的證據不得混成同一結論。

**v0.1.0 只交付 Skeleton**：兩個入口、九個佔位模組、配置管理、選單／CLI、日誌與報告基礎、自我測試、安裝及更新。它**不執行任何真正測速**，不建立 systemd Timer／cron，不啟動公開測試服務，不實作 AI 判斷。

## 二、組件視圖與控制流

```text
使用者（Mac）                          使用者（Linux VPS）
  netlab-c [CLI／TTY]                    netlab-s [CLI／TTY]
           │                                      │
           └──────── 公開命令介面（A03）──────────┘
                                                  │
                       TTY Menu（A04）──► CLI Router／Parser
                                                  │
                                      Config Loader／Validator（A05）
                                                  │
                                      Capability／Safety Preflight
                                                  │
                                         Runner（A06）
                            ┌─────────────────────┼────────────────────┐
                            │                     │                    │
                     Execution Context      Lifecycle／Logs     Module Registry
                      唯讀快照（JSON）       timeout／signals       固定 ID→路徑
                            │                     │                    │
                            └─────────────────────┴────────────────────┘
                                                  │
                           ┌──────────────────────┴────────────────────┐
                           │                                           │
                    C Modules（5 個）                              S Modules（4 個）
                 c-inventory／standalone                      s-inventory／toolbox
                 paired／proxy／collect                       service／scheduler
                           │                                           │
                           └──── 原生資料／子項狀態／安全摘要 ──────────┘
                                                  │
                                     Report Writer（A07）
                                                  │
                            manifest + summary + raw + 操作日誌
```

### 公開命令與選單的關係

- 只公開 `netlab-c`、`netlab-s` 兩個一般使用者命令；互動選單是這兩者在 TTY 下的前端。
- 選單編號只為顯示，不是穩定 API。選單選擇轉成 A03 已定義的 CLI 子命令和旗標。
- `c/*.sh`、`s/*.sh` 可以獨立執行，**但必須委派至同一驗證／Runner 流程**，不得繞開配置或安全檢查。
- `targets`、`config`、`results`、`logs`、`doctor`、`self-test`、`update` 是共用管理處理器，不算九個功能模組。
- S Toolbox 的 NetQuality、TcpQuality、HardwareQuality、IPQuality、NextTrace、MTR、Flent 是**工具適配器 ID**，不是七個額外頂層模組。

### 模組調度的依賴方向

```text
CLI／Menu → Config → Runner → Module → Report Writer
                           │                 ▲
                           └─ Context／日誌 ──┘
```

**依賴只能朝一個方向**。模組不能回頭修改 CLI Router／主選單，也不能各自實作新版配置規則或最終報告 Schema。Report Writer 可以呼叫獨立、無副作用的 JSON Schema 校驗器。

### 直接呼叫模組不造成 Runner 遞迴

A06 要求「直接呼叫 `.sh`」與「入口命令」使用相同 Runner。B05 必須有**內部工作模式**，例如由受控 Dispatcher 呼叫模組實作函式或獨立的內部執行入口，並驗證 Context 所屬 Run。禁止 `module.sh → netlab-c → module.sh → ...` 的遞迴。內部呼叫協定不得變成未經保護的公共繞過入口。

## 三、Repository 與使用者本地資料分離

### GitHub 原始碼佈局

```text
NetworkLab/
├── install.sh                 # POSIX sh 安裝引導；Alpine 不預設有 Bash
├── netlab-c.sh                # C 公開入口
├── netlab-s.sh                # S 公開入口
├── c/
│   ├── c-inventory.sh
│   ├── c-standalone.sh
│   ├── c-paired.sh
│   ├── c-proxy.sh
│   └── c-collect.sh
├── s/
│   ├── s-inventory.sh
│   ├── s-toolbox.sh
│   ├── s-service.sh
│   └── s-scheduler.sh
├── lib/
│   ├── common.sh
│   ├── config.sh
│   ├── menu.sh
│   ├── runner.sh
│   └── report.py
├── defaults/
│   ├── c.conf
│   ├── targets.conf
│   └── s.conf
├── schemas/                  # A07 新增，Phase A 正式併入骨架
│   ├── manifest.schema.json
│   └── summary.schema.json
├── examples/                 # synthetic=true，僅作文件與測試 fixture
├── docs/
│   ├── architecture.md       # 本文件
│   ├── commands.md
│   ├── menus.md               # A04 新增
│   ├── configuration.md
│   ├── modules.md             # A06 新增
│   └── report-schema.md
├── tests/
│   ├── test-config.sh
│   ├── test-cli.sh
│   └── test-report.py
├── .gitignore
├── LICENSE
├── THIRD_PARTY_LICENSES.md    # A09 規劃：工具來源／授權紀錄
└── README.md
```

此樹狀圖是**目標結構**，不宣稱以上所有腳本已建立或能執行。`schemas/`、`examples/`、`menus.md`、`modules.md` 是 A04／A06／A07 進行時已加入規格的合理擴充，應納入 A02 的實際 Repository 骨架。

### 安裝後各機器的目錄

```text
~/.networklab/
├── app/                        # 版本化 GitHub 程式碼；可更新
├── config/                     # 使用者私有設定；不可被更新覆蓋
│   ├── c.conf                  # 只建立當前角色需要的檔案
│   ├── targets.conf
│   └── s.conf
├── results/                    # 測量／匯入資料；不放入程式發佈版本
│   ├── c/local/
│   ├── c/<target_id>/
│   ├── c/proxy/
│   ├── s/<server_id>/
│   └── imported/<server_id>/
├── logs/                       # 操作日誌與錯誤
└── tmp/                        # Runner 私有工作區；需要時才建立
```

- 實際安裝只建立 C 或 S 所需目錄，不應讓每台 VPS 都出現 Mac 配置。
- 不採用年／月／日深層目錄；結果按角色與目標分類，Run 以檔名及結構化索引管理。
- `NETLAB_HOME` 僅接受絕對路徑，適用隔離測試；`--output-dir` 只覆寫該次結果根目錄。
- Linux 定時器將來必須鎖定執行帳號及 Home；不可在互動時使用一般使用者目錄、排程時卻寫入 `/root`。
- `config`／`results`／`logs`／私有工作區建議 `0700`，設定檔及 Context 建議 `0600`。

## 四、配置層：格式、身份、優先序

| 配置 | 角色 | 格式 | 關鍵內容 |
|---|---|---|---|
| `c.conf` | C | UTF-8 INI | 預設 Profile、IP Family 偏好、本機代理入口、targets 路徑 |
| `targets.conf` | C | UTF-8、固定八欄 `\|` | `display_name\|target_id\|nat/direct\|IPv4\|IPv6\|iperf3 TCP port\|TCP MTR port\|SSH alias` |
| `s.conf` | S | UTF-8 INI | `server_id`、三種 Profile、工具覆寫、流量預算、排程定義 |

執行配置優先序：**明示 CLI 值 > 使用者配置 > 安全內建預設**。S 每個工具先套用 `enabled`、`profile_override`，再從對應 Profile 得到 `off/lite/normal/full`，最後才由未來 Adapter 映射成實際外部命令；成本與安全檢查不能被覆寫繞過。

- 使用 `configparser(interpolation=None, strict=True)` 及 `ipaddress` 等資料解析器；**禁止 `source`／`eval` 讀配置**。
- `targets.conf` 的八欄順序固定，最後 SSH alias 可以空，但分隔符不可少。`target_id` 是本機長期穩定的識別碼，不能用動態 IP 作唯一身份。
- `s.conf` 範本的 `server_id = CHANGE_ME` **不是有效部署狀態**；B12 安裝器必須建立並要求確認合法且不與其他機器混淆的 ID。
- A05 的 `config_version = 1`、A06 的 `contract_version = 1`、A07 的 `schema_version = "1.0"`、產品 `v0.1.0` 是不同維度。
- 配置錯誤回傳 `3`；`--help`／`--version` 不應因配置損壞而失效。
- 編輯器退出後要驗證並重新載入；失敗時不套用無效配置。安裝與升級永不以預設檔覆蓋本地有效設定。

## 五、模組與工具適配器邊界

| 角色 | 公開子命令 | Module ID | 類型 | Skeleton v0.1.0 |
|---|---|---|---|---|
| C | `inventory` | `c-inventory` | measurement | 保留入口，8 |
| C | `standalone` | `c-standalone` | measurement | 保留入口，8 |
| C | `paired` | `c-paired` | measurement | 保留入口，8 |
| C | `proxy` | `c-proxy` | measurement | 保留入口，8 |
| C | `collect` | `c-collect` | transfer | 保留入口，8 |
| S | `inventory` | `s-inventory` | measurement | 保留入口，8 |
| S | `toolbox` | `s-toolbox` | measurement batch | 保留入口，8 |
| S | `service` | `s-service` | management | 保留入口，8 |
| S | `schedule` | `s-scheduler` | management/dispatch | 保留入口，8 |

- 公開 CLI 命令合法且配置通過時，尚未實作的功能退出 `8`（`NOT_IMPLEMENTED`），**不寫正式測量結果**。
- `--help`／`--version` 返回 `0`，即使模組未實作。`--dry-run` 對尚未實作的模組仍返回 `8`，不能展示虛構測試命令。
- 已有其他可用模組時，缺少非必要工具只能影響相關子測試；完全未執行不可回報成功。
- `s-toolbox` 日後使用 Adapter 管理外部工具：偵測版本 → 固定合法參數 → 執行獨立程序 → 保留原生格式 → 回傳退出碼。不可直接將第三方程式碼合併進主腳本，也不預設浮動 `curl | bash`。
- 適配器在 v0.1.0 **尚未實作**，也沒有替 NetQuality 等工具捏造任何 CLI 參數。

## 六、Runner 與 Execution Context

### 責任分工

| 元件 | 負責 | 不負責 |
|---|---|---|
| CLI Router | 公開子命令、參數語法、命令與模組 ID 映射 | 真正測試、寫最終報告 |
| Menu | TTY 輸入、編號／多選／確認、顯示 | 自己生成第二套測速指令 |
| Config Validator | 讀取、驗證、合併預設、產生有效設定快照 | 推論網路性能 |
| Runner | 預檢、建立 Run、工作區、流程控制、timeout、signal、資源清理 | 直接硬編碼所有測量方法 |
| Module | 單一領域測試／管理功能，交付 raw 與子項狀態 | 解析完整配置或寫最終 manifest |
| Report Writer | 路徑、JSON、SHA-256、原子提交與跨檔一致性 | 替測量工具編造指標或主觀評分 |
| Tool Adapter（未來） | 外部工具的版本、參數、安全呼叫、原生格式 | 成為新的對外 CLI 入口 |

### Context 傳遞

Runner 建立私有工作區及已驗證 JSON Context；模組由環境變數接收絕對路徑：

```text
NETLAB_CONTEXT_FILE = <絕對路徑>/context.json
NETLAB_WORK_DIR     = <絕對路徑>/work
```

Context 必須包含 A06 固定的 `contract_version`、`role`、`module_id`、`run_id`、`task_kind`、`profile`、`target_id`／`server_id`、`selected_modules`、`non_interactive`、`quiet`、`started_at`、`paths`、`target` 和 `effective_parameters`。

**A08 的整合提醒**：A07 已引入 `run_uuid` 和 `correlation_id`。B05 生成 Context 時，應在 A06 最小欄位之外，將這兩個識別符作為**非破壞性新增欄位**交給模組（若模組需要），但不可改變 A06 既有欄位語義。Report Writer 仍為二者的權威建立者／校驗者；C／S 端分別有自己的 `run_uuid`，聯動時共用 `correlation_id`。

Context 不存秘密資訊；SSH 使用本機 `~/.ssh/config`，代理機密也不輸出到可分享 JSON。`--non-interactive` 禁止任何提示，`--quiet` 只減少可見進度，不減少證據資料。

### 正式執行生命週期

```text
解析 CLI → 驗證配置 → 安全／依賴預檢
       → 固定有效配置 → 建立 Run 身份與工作區
       → 子模組或 Adapter 執行 → 捕獲 raw/stdout/stderr/exit code
       → 校驗與整理 → 原子寫 Summary → 最後寫 Manifest
       → 清理本次擁有的暫存資源 → 回傳 CLI 退出碼
```

未實作的模組在預檢後立即返回 8，**不應先建立一份正式測量 Run**。管理查詢操作（例如 `config profiles`、`service status`）也不應當成測量 Run。

Runner 必須處理：單項和整批 timeout、Ctrl+C、工作區權限、同秒 Run 碰撞、子程序擁有權；不可 `kill 0` 或對非本次擁有的程序使用廣泛 `pkill`。macOS 沒有保證提供 GNU `timeout`，因此 B05 需要可攜方案。

## 七、報告資料架構與證據契約

每個**正式完成封存的 Run** 由 **Manifest + Summary + Raw files** 組成；Runner／`lib/report.py` 統一負責最終輸出，Module 保留原生測量證據。

### 識別與時間

- `run_id`：`YYYY-MM-DD-HH-mm-ss-scope_id[-NN]`，提供人類可讀的本機 Run 名稱。
- `run_uuid`：UUIDv4，跨設備匯入、去重的權威識別。
- `correlation_id`：可選；只有 C／S 實際有可驗證的聯動時才共用，否則 `null`。
- `test_id`：單項測試語義 ID；同一 Run 內以 `attempt` 區分重試。
- 檔名：`<role>-<test>-<scope_id>-YYYY-MM-DD-HH-mm-ss[-NN].<ext>`。
- 報告時間一律固定 **UTC+08:00**；檔名時間取 Run 開始時刻，不修改 macOS／Linux 系統時區。

### 扁平目錄的安全檔名

```text
results/c/nat-us/
  c-manifest-nat-us-2026-10-21-18-31-05.json
  c-summary-nat-us-2026-10-21-18-31-05.json
  c-tcp-connect-ipv4-nat-us-2026-10-21-18-31-05.json
  c-iperf3-p1-download-nat-us-2026-10-21-18-31-05.json
```

上列僅為**檔名範例**，不是實測輸出。不可使用不帶時間的單一 `manifest.json`／`summary.json`。同秒多次執行時，整個 Run 共用 `[-NN]` 衝突尾碼；若同一 Run 多份 raw slug 相同，應使用不同 `test_id`／`attempt` 衍生名稱。

### 資料模型

| 類型 | 保存內容 | 最終編寫權限 |
|---|---|---|
| Manifest | 身份、有效參數（已遮蔽）、run／module 狀態、SHA-256、size、原生檔案索引 | Report Writer |
| Summary | tests[]、metrics、工具／網路條件、`evidence_scope`、`data_provenance`、errors/warnings | Report Writer |
| Raw | 原生 JSON／NDJSON／CSV／TXT／Flent 檔、stdout／stderr | Module 產生；Runner 保存 |

Schema 位置：`schemas/manifest.schema.json`、`schemas/summary.schema.json`（JSON Schema Draft 2020-12）。`schema_version = "1.0"` 不等於產品版本。

- `evidence_scope`：`local`、`public_path`、`c_s_direct`、`proxy_path`、`third_party_service`。
- `data_provenance`：`observed`、`configured`、`provider_declared`、`unknown`。
- 核心單位：RTT = ms、吞吐 = Mbps、傳輸量 = bytes、成功率／丟包率 = %，未知值應為 `null` 而不是 `0`。
- 以 `test_id`、attempt、Profile、IP Family、方向、工具版本及實際參數確保可比較性；Schema 合法不等於測量有效。

### 提交與故障保存

- 先建立帶排他佔用保證的 Run 身份／工作區（不能先 `exists()` 再無鎖寫入）。
- 原生檔案完成後落地，寫 Summary、計算 SHA-256 和檔案長度，**最後原子提交 Manifest** 作為可索引的 Run 封存標記。
- Manifest 不保存自己的 SHA-256 以免循環引用；其餘分享檔由 `files[]` 索引且雜湊驗證。
- 中斷、timeout、partial 盡可能封存已有資料；遇到 SIGKILL、斷電或檔案系統故障不保證完整，可能留下**不可作為有效 Run 的孤立檔案**。
- Self-test 只在隔離目錄產生 `synthetic: true` 的測試資料，禁止混入 `results list` 的真實測量。

## 八、三種執行場景與資料流

### 場景 C：Mac 本機獨立工作

```text
Mac → netlab-c inventory/standalone/proxy
    → Config／Runner → 對應 C Module → Report Writer
    → results/c/local 或 results/c/proxy
```

- `inventory` 採集本地狀態；`standalone` 使用固定公共端點；`proxy` 使用設定的本機代理入口。
- `proxy` 不可僅因使用者選擇某節點就認定所有目標都經過同一出口；日後需逐目標收集實際出口證據。
- v0.1.0 只顯示佔位模組狀態，沒有任何實際 C 測試。

### 場景 S：VPS 獨立工作

```text
VPS → netlab-s inventory/toolbox
    → s.conf／Runner → S Module／第三方 Adapter
    → Report Writer → results/s/<server_id>
```

- `toolbox` 未來負責獨立調用第三方工具並保留完整原始格式，不從外部工具結論直接推斷 C ↔ S 品質。
- `schedule` 將來觸發**同一 Runner**，不是另做一套定時版測速腳本；Debian／Ubuntu 可優先 systemd Timer，Alpine 可用 cron／crond，皆不屬 v0.1.0 實作。

### 場景 C ↔ S：聯動測量與收集

```text
       Mac (C)                               VPS (S)
 netlab-c paired --target ID              netlab-s service（未來）
       │                                         │
       ├─ TCP Connect／iperf3 → 測試端口 ───────►│
       │                                         ├─ 低負載資源觀察（未來）
       │                                         │
       └─ C Run manifest/summary                └─ S Run manifest/summary
                  │                              │
                  └──── correlation_id（可選，同一聯動） ─────┘

 netlab-c collect --target ID ──已授權 SSH/SFTP──► S 報告檔案
       │
       └─ 驗證檔案 SHA-256 與 run_uuid，另存 results/imported/<server_id>
```

- C 端目標由 `targets.conf` `target_id` 選擇；S 端使用自己的 `server_id`，**不可假定兩者必然相同**。真正的聯動匹配依實際連線資訊及 `correlation_id`，必要時保留識別對照 Metadata。
- iperf3 的 `-R`（未來）能量測 VPS → Mac 的應用吞吐，不意味家庭 Mac 需開放入站埠，也不能代替逐跳回程路由測量。
- NAT VPS 的 iperf3 UDP 測試仍依賴 TCP 控制連接，必須分別驗證 TCP 控制映射與 UDP 資料映射；`targets.conf` 的埠只有外部 TCP 控制埠。
- `c-collect` 保存 S 原始檔案位元組及身分，不刪除遠端資料；沒有 SSH 通道時回報不可用，不另行公開不受控 HTTP 檔案服務。
- **同名不同 run_uuid** 的匯入不能覆蓋；S 報告中的來源檔名和雜湊不應被悄悄修改。具體安全命名、隔離及匯入收據實作留待 `c-collect`。

## 九、平台部署與版本更新

### 安裝責任

- `install.sh` 以 **POSIX sh** 編寫，先辨認 macOS 或 Linux／CPU 架構，再檢查 Bash 和 Python3，按平台提供相依安裝方案；Alpine 預設可能沒有 Bash。
- 只使用使用者核准的下載來源及固定 Release／Tag；預設不從浮動 `main` 執行 `curl | bash`。
- 為 `netlab-c`／`netlab-s` 建立可重複使用的命令入口，不能重複追加 PATH 或破壞既有 Shell 配置。
- 首次初始化才從 `defaults/` 複製本地配置；第二次安裝和後續更新不得覆蓋 `config`、`results`、`logs`。
- 安裝、更新和版本查詢應分離；使用者可以單純查看新版本，不意味自動套用。

### 更新責任

- `update check` 查詢可信的版本資訊；`update apply --version VERSION` 需由使用者指定版本並確認更新來源。
- B13 要提供更新失敗時的程式回復策略；在切換新的 app 版本之前校驗檔案完整性與最低執行環境。
- 配置 schema 升級只補缺失預設、驗證後備份及遷移，不靜默覆寫使用者改動；歷史測量檔原則上唯讀。
- 離線 `--help`、`--version`、`config validate`、`self-test` 不應依賴 GitHub 連線。`update check/apply` 才需要必要的網路連線。

## 十、安全邊界與第三方授權

- **最小權限**：普通 Inventory 不要求 root；真正需要權限時必須明示原因，不能把全套工具都置於 sudo 下執行。
- **外部服務**：未來 `s-service` 只能啟停由 NetworkLab 建立並記錄所有權的測試程序，不得影響 Xray／sing-box 或使用者既有監聽埠。
- **成本控制**：Profile `deep` 或 `--modules all` 不代表授權高流量／高負載；S 的配額 `0` 表示未給予高流量預算，未知估算需拒絕或明確授權。
- **資料隱私**：Context、manifest、summary、stdout/stderr 中敏感 Token、Cookie、Authorization、代理憑證、SSH 私鑰等必須遮蔽；可分享檔案不能存取任意工作區外路徑。
- **外部工具供應鏈**：只調用有審查來源、可記錄版本與雜湊的獨立工具；記錄其授權條款，避免直接拷貝 AGPL／GPL 工具程式碼造成不必要的衍生授權問題。對不同工具須逐一履行授權義務，不可認為「GitHub 公開」就是任意使用。
- **權限邊界**：Context 檔路徑不是授權憑證；只有固定模組註冊表、可信的 Runner 與受控工作區能啟動正式操作。
- **無隱藏網路行為**：`--dry-run` 只驗證與預覽；Self-test 不連網、不啟動服務、只產生 synthetic 資料。

## 十一、版本與可擴充性

| 公共契約／接口 | 已定版本／規則 | 變更策略 |
|---|---|---|
| 公開入口、子命令、退出碼 | A03 CLI Contract v1 | 變更需確認對舊 CLI 的影響 |
| 選單導航和轉譯 | A04 Menu Contract v1 | 編號可變，映射到 CLI 不可變 |
| 本地配置 | `config_version = 1`（A05） | 新欄位需預設值／遷移；不覆寫使用者檔 |
| Runner Context | `contract_version = 1`（A06） | 可非破壞性擴充；必填語義更改需新版本 |
| 報告 JSON | `schema_version = "1.0"`（A07） | 破壞性欄位或單位更動需新 Schema |
| 產品版本 | `v0.1.0 Skeleton` | 可用的非測速系統骨架 |

新增測試功能時，優先新增 Module 內的子項或 Adapter，而不是增加第三個公開入口。若新增 CLI 選項，先更新 A03、A04 對應顯示、A06 模組輸入、A07 必要結果欄位和測試案例。

## 十二、實作責任表：從 Phase A 到 B／C

| 已有設計規格 | 主要落地工作 | 驗收證據 |
|---|---|---|
| A03／A04 | B02 CLI Parser、B03／B04 C／S Menu | 相同功能由 CLI／TTY 都能調用；錯誤碼一致 |
| A05 | B07 C 目標配置、B08 S 配置 | 配置修改後刷新、非法值阻止執行、舊配置保留 |
| A06 | B01 基礎工具、B05 Runner、B06 佔位模組 | 直接啟動與總入口一致；未實作回 8 |
| A07 | B09 Report Writer、B10 Result Browser、B11 Self-test | schema、hash、run ID、同秒碰撞、中斷保留 |
| 部署／更新 | B12 install.sh、B13 update | Mac／Debian／Ubuntu／Alpine 安裝與重裝不毀資料 |
| 品質與發布 | C01–C07 | 靜態檢查、單元／整合測試、CI、Release Tag |

### v0.1.0 最低系統驗收

- 全新受支援 Mac／Linux 可安裝正確角色並開啟選單。
- 兩端 `--help`／`--version` 不需有效配置亦可正常返回。
- 配置清單可以新增、編輯、驗證及在選單中重新載入。
- 九個功能入口存在，合法但未實作的要求統一返回 `NOT_IMPLEMENTED`（8），不產生正式測量報告。
- CLI 與選單轉譯為同一個 Runner，獨立模組入口不繞過安全驗證。
- Report Writer 在隔離 Self-test 能建立並驗證帶 `synthetic: true` 的 manifest／summary／raw；不混入真實結果列表。
- 同秒 Run、錯誤配置、缺少依賴、Ctrl+C 和安裝更新的故障場景有可驗證行為。
- 安裝／升級不覆蓋用戶配置／歷史結果；更新失敗能回復到可用的 app。
- 所有關鍵環節的自動化測試在 CI 中通過。

## 十三、規格交叉檢查：需在 Phase B 精確落地的細節

以下不是擅自推翻 A03–A07，而是整合時發現的**實作決策點**，在編寫程序前應納入測試規格：

| 關鍵點 | 目前約束 | Phase B 處理方式 |
|---|---|---|
| Module 直接執行 | 直接執行須走 Runner | B05 使用內部 Dispatcher 或實作函式，防止委派遞迴 |
| Context 欄位 | A06 固定最小 Context；A07 新增 UUID | B05 對 Context 非破壞性加入 `run_uuid`／`correlation_id` |
| 扁平檔名併發 | 同秒不能覆蓋；同 Run 多 raw 不重名 | B09 排他預留、同一 Run 尾碼、test/attempt 區分 |
| 平台 timeout | macOS／Linux 提供的工具不一致 | B05 使用已測試的可攜實作，不假設 GNU timeout |
| 預設 `all` | 只包含安全可用工具 | B05／Adapter 將 Profile、enabled、重負載預算合併後才展開 |
| C/S 身份對照 | C target_id 不保證等於 S server_id | C-Paired／C-Collect 使用明確身份映射與 correlation_id |
| S 範本 `CHANGE_ME` | 只是佔位符，不能作合法 server_id | B12 初始化，B08 拒絕未替換範本 |
| `update` 的網路與回滾 | CLI 已有 check/apply，測試模組未實作 | B13 實作獨立更新管理，不讓它觸發測速 |
| 外部工具授權 | 沒有因為 GitHub 公開就可任意複製 | A09 登記來源、License、呼叫／散布方式 |
| Schema vs 跨檔校驗 | JSON Schema 只驗單檔結構 | B09／B11 額外驗證雜湊、關聯、實際有效狀態 |

### Phase A 收尾檢查

- A03 `commands.md`、A04 `menus.md`、A05 `configuration.md`、A06 `modules.md`、A07 `report-schema.md` 與本文件均已形成可追溯介面規格。
- A08 只完成**架構整合文件**，不等於 A01/A02 Repository 已經初始化，也不等於 B01–B13 程式碼已實作。
- A09 第三方授權與工具來源審查建議列為進入公開發布前的必要任務；依工具實際散布形式判定授權義務。

**A08 完成定義**：明確整體系統定位、分層組件、依賴方向、Repository 與本地部署、C/S 資料流、配置／Runner／Module／Report 的責任、平台與安全邊界、版本演進、骨架驗收及下游工作映射。
