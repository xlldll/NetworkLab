# NetworkLab 配置文件規範

- **規格識別**：A05 / Configuration Contract v1
- **目標版本**：NetworkLab v0.1.0 Skeleton
- **狀態**：配置介面規格已確定；不是配置解析器／編輯器已實作的聲明
- **上游依據**：`docs/commands.md`（A03）、`docs/menus.md`（A04）
- **適用角色**：C = macOS Client；S = Linux Server（Debian、Ubuntu、Alpine 優先）

## 一、範圍與原則

A05 固定三份使用者配置、格式、資料型別、預設值、驗證規則、配置優先序及升級策略：

| 配置 | 角色 | 格式 | 用途 |
|---|---|---|---|
| `c.conf` | C | INI（UTF-8） | 本機 Profile、網路 IP Family、代理入口、VPS 清單路徑 |
| `targets.conf` | C | UTF-8、每行 8 欄、`\|` 分隔 | 一對多 VPS 目標、NAT/direct、IP、Port、SSH alias |
| `s.conf` | S | INI（UTF-8） | VPS 識別、Profile、第三方工具抽象模式、成本預算、排程定義 |

核心原則：

- **GitHub `defaults/` 是範本，本地 `~/.networklab/config/` 是實際配置**。安裝器只在檔案不存在時初始化；後續升級不得用新範本直接覆寫。
- **配置是資料，不能被 Shell 執行**：禁止透過 `source`、`.` 或 `eval` 載入；使用 Python 3 標準函式庫的 `configparser`、`ipaddress` 等解析／驗證。INI 解析應使用 `interpolation=None`、`strict=True`，不執行參數插值。
- **配置提供意圖而非性能事實**：填寫 IPv6、NAT、代理埠或 `full` 不代表相應網路能力已驗證；測量時仍需保存實際觀察結果。
- **骨架不啟用功能**：A05 只確定格式；v0.1.0 不啟動測速、定時器、公開服務、更新或任何高流量測試。
- **精簡常用項、容納未來擴展**：C 端主要設定保持短小；S 端使用分區；未來新欄位需版本與遷移規則。

## 二、本地路徑與解析優先序

```text
~/.networklab/
├── app/                 # GitHub 安裝的程式碼
├── config/
│   ├── c.conf           # C 使用
│   ├── targets.conf     # C 使用
│   └── s.conf           # S 使用
├── results/
└── logs/
```

- 安裝器只建立當前角色需要的配置。S 不依賴 `targets.conf`；C 不依賴 `s.conf`。
- 預設根目錄是執行帳號的 `~/.networklab/`；只允許透過**絕對路徑** `NETLAB_HOME` 暫時覆寫（適用測試、隔離環境）。不可自動切換 root 的家目錄。
- `--config FILE` 指定本次 C `c.conf` 或 S `s.conf`；C 的 `targets.conf` 路徑仍由被讀取的 `c.conf` 的 `[paths].targets_file` 決定。
- `[paths].targets_file`：若為相對路徑，**相對於正在讀取的 c.conf 所在目錄**；亦允許絕對路徑。沒有 shell 展開、萬用字元、`$VAR` 替換。
- `--output-dir DIR` 在適用的執行命令中覆寫本次 `results/` 根目錄，不會改寫任何 INI 設定。
- 優先順序：**本次明確 CLI 參數 > 本次選用的本地配置 > `defaults/` 內建值**；S 單工具 `profile_override` 對該工具高於選定的全域 Profile。
- 互動式 VPS 選單可預選第一筆，但非互動 `paired`／`collect` **必須**有 `--target ID`，即使 `targets.conf` 只有一筆也不能偷偷選它。
- 目錄原則上以私有權限建立（config／results／logs 建議 `0700`，配置檔 `0600`）；禁止在任何報告記錄代理憑證、私鑰或 Token。

## 三、共同格式與版本規則

### INI（`c.conf`、`s.conf`）

- UTF-8 純文字；`[section]`、`key = value`，屬性鍵一律小寫 `snake_case`；分區名稱一律小寫，工具 ID 用 kebab-free 小寫字母。
- `#` 或 `;` 在行首可作整行註解；行內 `#` 不視為通用註解語法，避免值被截斷。
- 相同分區或鍵重複時報配置錯誤 `3`。未知鍵、未知分區或未知枚舉值也報 `3`（避免拼寫錯誤被默默忽略）。
- `config_version`：整數 `1`。此配置版本**不同於**報告的 `schema_version = "1.0"`，也不同於程式版本 `v0.1.0`。
- 必填欄位不存在或格式無效時列出檔名、分區、鍵、實際值及預期範圍（訊息不得外洩憑證），返回 `CONFIG_ERROR`（3）。
- 布林值在範本中只使用 `true` / `false`；解析器應將大小寫標準化。INI 不應執行 `%` 插值。

### `targets.conf`

- UTF-8 純文字，每行一筆記錄；空行與行首 `#` 註解忽略。**資料行必須恰好 8 欄（7 個 `|`）**。
- 不使用 Shell 跳脫或 CSV 引號語法；`|`、換行不能存在於欄位值。每欄頭尾空白會被裁掉，但顯示名稱中間可有空格。
- 第 8 欄雖可空白，**尾端 `|` 仍必須存在**。不要默默把舊式 7 欄記錄視為合法 8 欄。
- 正規化後的 `target_id` 不可重複，大小寫必須小寫；保留順序就是互動選單順序。
- 本版本沒有修改型的 `targets delete`／`rename` CLI；可用 nano/vim 修改，修改後立即驗證並刷新。

## 四、`c.conf` 契約（C 端）

### 官方範本

```ini
[general]
config_version = 1
default_profile = standard

[network]
preferred_ip_family = auto

[proxy]
protocol = http
host = 127.0.0.1
port = 7890

[paths]
targets_file = targets.conf
```

### 欄位定義

| 分區／鍵 | 型別／允許值 | 預設 | 驗證及作用 |
|---|---|---|---|
| `general.config_version` | 整數 `1` | 必填 | 不接受未知版本；需先升級或遷移 |
| `general.default_profile` | `quick` / `standard` / `deep` | `standard` | 用於適用的測試命令及選單預設 |
| `network.preferred_ip_family` | `auto` / `4` / `6` | `auto` | 僅為**偏好**；不可當作 IPv4／IPv6 已連通的證據 |
| `proxy.protocol` | `http` / `socks5` | `http` | 指定本機代理入口協定，**不是**上游代理出站類型 |
| `proxy.host` | IPv4 / IPv6 位址（預設 loopback） | `127.0.0.1` | 不允許 URL、Shell 片段或附帶埠的字串 |
| `proxy.port` | 整數 1–65535 | `7890` | 僅為待檢測的本地入口；不表示 Bettbox 一定在此埠監聽 |
| `paths.targets_file` | 有效檔案路徑 | `targets.conf` | 相對於 c.conf 所在目錄；不可為空 |

**C 端決策**：不在 v0.1.0 的 c.conf 設定使用者的 SSH 帳號、密碼、私鑰路徑、固定外部 IP、ASN、地理位置或動態落地節點名稱。代理測試日後需要以每個目標實際觀察的出口 IP 作為證據，而不是僅相信配置。

`default_profile`、`preferred_ip_family` 只供未來模組讀取。`paired --target` 的目標配置不應被這些欄位取代。

## 五、`targets.conf` 契約（C 端多 VPS）

### 精確欄位順序

```text
顯示名稱|target_id|nat/direct|IPv4|IPv6|iperf3外部TCP埠|TCP MTR埠|SSH別名
```

| # | 欄位 | 必填 | 格式與驗證 |
|---:|---|---|---|
| 1 | `display_name` | 是 | 1–80 個 Unicode 字元，允許繁體中文及空格；不可為空 |
| 2 | `target_id` | 是 | 1–63 字元，`^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$`；不可重複 |
| 3 | `type` | 是 | 僅 `nat`、`direct`；不要用布林值取代 |
| 4 | `ipv4` | 條件式 | 正確 IPv4 字面位址；與 IPv6 至少填一個 |
| 5 | `ipv6` | 條件式 | 正確 IPv6 字面位址，不帶 `[ ]` 或 `%interface`；與 IPv4 至少填一個 |
| 6 | `iperf3_external_tcp_port` | 是 | 1–65535；**外部 TCP 控制連線埠**，不是內部 NAT 埠 |
| 7 | `tcp_mtr_port` | 是 | 1–65535；追蹤實際服務所使用的 TCP 埠，可以不同於 iperf3 埠 |
| 8 | `ssh_alias` | 否 | 對應 `~/.ssh/config` 的 Host 別名；限字母數字、`.`、`_`、`-`，不得以 `-` 開頭 |

示例使用文件保留 IP，**不是實際可連線的 VPS**：

```text
美西NAT|nat-us|nat|198.51.100.10||48801|443|nat-us
東京AWS|aws-tokyo|direct|203.0.113.20|2001:db8::20|5202|443|aws-tokyo
香港KVM|hk-kvm|direct|192.0.2.30||5202|443|
```

重要規則：

- `display_name` 可以修改；`target_id` 是報告與歷史資料的**穩定識別碼**，一旦已有報告，修改 ID 應視為新目標或經明確資料遷移。
- `nat`／`direct` 只是部署類別，不代表可實際入站；NAT VPS 的 UDP 映射**不在這 8 欄**，日後另加可選進階配置，不把外部與內部埠混淆。
- 缺 IPv4 或缺 IPv6 表示未配置，**不等於**該協定不受支援；實際可達性待測試確認。
- `ssh_alias` 可留空，沒有 alias 不阻止 inventory／paired 等功能；collect 需在執行前確認可用連線方式。驗證配置**不**依賴實際 SSH 登入。
- IP 使用標準 `ipaddress` 解析；非公開 IP（如私網、文件範例、loopback）在配置驗證階段顯示警告／提示，但不因此一概拒絕，以容納內網實驗與測試 fixture。執行時另按目標安全策略處理。
- 不透過 IP 作主識別，因為 NAT 共享 IP、動態 IPv4 與換機都會變化；跨台重複的 ID 無法單憑本機驗證，匯入時需要檢查碰撞。
- 配置寫入用臨時檔、驗證、原子取代與必要備份；編輯器造成的壞配置不得進入當前生效狀態。

### `targets add`／`targets validate` 行為

- `targets add`（TTY）逐欄位詢問；CLI 提供 8 欄對應的 A03 旗標。對於可選 IPv6／SSH alias，使用空值表示未配置，保存時仍寫滿 8 欄。
- `targets add --non-interactive` 缺必需的旗標屬用法錯誤 `2`；提供了但值不合法屬配置錯誤 `3`。
- `targets validate` 必須逐行報錯並指出行數：欄位不足、多一欄、無效 IP、埠超限、缺少 IP、重複 ID 等；**不**嘗試 ping、SSH 或 iperf3。
- 新增／編輯成功後即時重新載入，無需重啟 `netlab-c`。

## 六、`s.conf` 契約（S 端）

### 官方範本

```ini
[general]
config_version = 1
server_id = CHANGE_ME
timezone = UTC+08:00
default_profile = standard
enable_heavy_tests = false

[profile.quick]
netquality = lite
tcpquality = lite
hardwarequality = off
ipquality = lite
nexttrace = lite
mtr = lite
flent = off

[profile.standard]
netquality = normal
tcpquality = normal
hardwarequality = lite
ipquality = normal
nexttrace = normal
mtr = normal
flent = off

[profile.deep]
netquality = full
tcpquality = full
hardwarequality = full
ipquality = full
nexttrace = full
mtr = full
flent = full

[tool.hardwarequality]
enabled = true
profile_override = inherit

[tool.flent]
enabled = true
profile_override = inherit

[limits]
max_metered_mb_per_run = 0
max_metered_mb_per_day = 0

[schedule.peak]
enabled = false
time = 20:30
days = daily
profile = standard
modules = inventory,netquality,tcpquality
```

### `[general]`

| 鍵 | 型別／預設 | 語義 |
|---|---|---|
| `config_version` | 必填，`1` | 配置 Schema 版本 |
| `server_id` | 必填，有效 target_id 格式 | S 本機穩定識別碼；**安裝器必須將 `CHANGE_ME` 換成唯一 ID**，原範本不能直接作為已驗證的實例配置 |
| `timezone` | 必填，固定 `UTC+08:00` | 檔名、報告與排程解讀均採固定 UTC+8；不修改 Linux 系統時區 |
| `default_profile` | `quick`／`standard`／`deep`；預設 `standard` | 互動／非互動模式的設定預設 |
| `enable_heavy_tests` | 布林值；預設 `false` | 是否容許**進一步確認**高負載任務；`true` 本身不構成無條件執行授權 |

`server_id` 建議由安裝器根據本機 hostname 建立初始建議值，提示使用者確認、寫入本地 `s.conf`；不能每次啟動重新生成，更不可把 `CHANGE_ME` 帶入報告。多台具有相同 hostname 的 VPS 必須使用不同 ID。

### `[profile.quick]`、`[profile.standard]`、`[profile.deep]`

三個分區各可為工具 `netquality`、`tcpquality`、`hardwarequality`、`ipquality`、`nexttrace`、`mtr`、`flent` 設定：

- `off`：在這個 Profile 中不執行該工具；
- `lite`：工具適配器定義的低流量／低負載模式；
- `normal`：工具適配器定義的一般測試模式；
- `full`：工具適配器定義的深入模式。

**這四個值是 NetworkLab 自訂抽象狀態，不是 NetQuality／TcpQuality 等工具的真實 CLI 參數。** 轉換實際旗標須由未來的工具 Adapter 根據官方版本逐項實作，v0.1.0 不執行外部工具。即使配置為 `lite`，若沒有對應的已驗證適配器，也應顯示 `NOT_IMPLEMENTED` 而非自行猜測命令。

單個 Profile 中缺少可選工具鍵時使用內建預設值並於驗證結果說明；不允許未知工具 ID、無效模式或重複鍵。

### `[tool.<tool_id>]`：單工具覆寫

可選分區，例如：

```ini
[tool.hardwarequality]
enabled = true
profile_override = quick
```

- `enabled = false`：無論全域 Profile 如何，都不執行該工具。
- `profile_override = inherit|quick|standard|deep`：`inherit` 使用命令／排程選定的全域 Profile；其他值只為此工具查找對應 `[profile.NAME]` 中的模式。
- 例：全域使用 `standard`，HardwareQuality 設 `profile_override = quick`，便使用 `[profile.quick].hardwarequality = off`，不影響其他工具。
- 生效順序：`enabled` 過濾 → 決定各工具實際 Profile → 取得模式 `off/lite/normal/full` → Adapter 將模式映射為真正參數 → 成本與授權檢查。
- 不允許在此直接寫入未經審查的遠端 `curl | bash` 命令、任意 Shell 片段或未知工具參數。

### `[limits]`：保守成本預算

| 鍵 | 型別／預設 | 意義 |
|---|---|---|
| `max_metered_mb_per_run` | 非負整數；預設 `0` | 單次明確列為高流量／按量計費測試的資料量上限（MB） |
| `max_metered_mb_per_day` | 非負整數；預設 `0` | 同類測試的 UTC+8 每日累積上限（MB） |

此處 `0` **表示不提供高流量測試配額，而非無限制**。預算未設定、估算未知或超過配額時，未來非互動高流量任務必須阻止，退出 `9`；互動也必須通過明確的安全確認。這些欄位不代表所有一般網路診斷能「零流量」運作。v0.1.0 僅驗證值，不扣量、不執行測試。記帳規則及精度待正式工具適配器實作時細化。

### `[schedule.<job_id>]`：未來排程格式

範例：

```ini
[schedule.peak]
enabled = false
time = 20:30
days = daily
profile = standard
modules = inventory,netquality,tcpquality
```

| 鍵 | 格式 | 語義 |
|---|---|---|
| `enabled` | `true`／`false` | v0.1.0 **永不**啟用實際 cron／systemd Timer；排程功能模組尚未實作 |
| `time` | 24 小時 `HH:MM`（00:00–23:59） | 按 `UTC+08:00` 解讀 |
| `days` | `daily`／`weekdays`／`weekends` 或 `mon,tue,wed,thu,fri,sat,sun` 子集 | 執行日期，不依賴系統時區 |
| `profile` | `quick`／`standard`／`deep` | 對該排程適用的 Profile |
| `modules` | `inventory,netquality,tcpquality,...` | 使用穩定模組 ID，去重；至少一項 |

- `job_id` 與 `server_id` 使用同一種安全 ID 語法；同一份 s.conf 不可重複。
- `modules` 允許：`inventory`、`netquality`、`tcpquality`、`hardwarequality`、`ipquality`、`nexttrace`、`mtr`、`flent`；真正運行時仍須檢查適配器、工具依賴及負載預算。
- v0.1.0 對 schedule 分區**只負責解析與驗證**。不論 `enabled` 寫成什麼，都不會自動啟動排程；建議範本一律 `false`。日後版本啟用前需有明確的 CLI 操作與安全確認。

## 七、統一驗證與錯誤規則

### 驗證層級

| 層級 | 驗證內容 | 是否需要網路 |
|---|---|---|
| 1. Syntax | UTF-8、INI／8 欄語法、重複鍵／ID、數字範圍 | 否 |
| 2. Semantic | 對應 Profile、有效 server_id／target_id、端口、IP Family、排程欄位 | 否 |
| 3. Platform | 編輯器、Python3、路徑寫入權限等（`doctor`） | 否 |
| 4. Runtime | SSH 可連、代理有監聽、iperf3 TCP／UDP 映射、網路可達 | **是；不屬於 A05 配置驗證** |

- `targets validate` 只讀 targets 清單；`config validate` 先驗角色主配置，C 還應根據 `[paths].targets_file` 驗證其清單。
- 配置**本身正確**與服務**可實際連線**為不同概念；不用檢查配置來冒充測速。
- 錯誤須含檔案、行數（適用時）、欄位、錯誤原因與修復提示；不正確的欄位應列出允許值。
- 即使驗證失敗，也不得部分套用無效配置，更不可覆蓋原來可用的資料。
- `--help`／`--version` 應能在配置損壞時照樣執行；符合 A03 契約。

### 錯誤示例（僅示意）

```text
CONFIG_ERROR (3): ~/.networklab/config/targets.conf:8
  target_id=nat-us: iperf3_external_tcp_port=70000 無效；必須為 1–65535

CONFIG_ERROR (3): ~/.networklab/config/s.conf [general].server_id
  CHANGE_ME 只是安裝範本佔位符；請指定唯一 ID

CONFIG_ERROR (3): ~/.networklab/config/c.conf [proxy].protocol
  未知值 "https"；目前僅支援 http、socks5
```

## 八、修改、升級、相容與安全

**編輯與寫入**

- `config edit`／`targets edit` 以使用者指定 nano/vim 編輯本地配置，退出編輯器後重新讀取及驗證。驗證失敗不改變目前記憶體內的生效配置；應提供檔案與行數以便修復。
- `targets add` 等程式化修改須先建立同目錄臨時檔、驗證候選內容，再原子替換；必要時先建立 timestamp 備份，不能直接覆蓋半個檔案。
- `defaults/` 不存真實 IP、SSH 帳號、密碼、Token 或個人的代理認證資訊；`.gitignore` 必須排除本地配置、結果與日誌的意外提交。
- 解析器不得把配置字串拼接成可執行的 Shell 命令；所有網路目標、檔案路徑及參數需以引號或陣列方式安全傳遞。

**版本升級與資料遷移**

- 原始使用者配置不可被安裝器或更新器重置。若新版本新增「可選」鍵，先以內建預設補足讀取；必要時提供顯式遷移及備份，不自動改寫。
- 升級遇到 `config_version > 程式支援版本` 時退出 `3`，不得猜測新版本格式；舊版格式若需遷移，須先備份、驗證新檔，成功後才原子替換。
- 舊 7 欄 VPS 清單不應靜默當作 8 欄解析；日後可以提供受控匯入命令，遷移時補上空白 SSH 欄位及最後的 `|`。
- 若使用者變更 `target_id` 或 `server_id`，不得自動把既有歷史檔案重新歸到新 ID；應明確警告歷史關聯的影響。
- `update apply` 不更改私人 `~/.networklab/config/`、`results/`、`logs/`；GitHub `defaults/` 的更新可作差異參考。

**外部公開工具與 License**

- 第三方工具適配器日後只管理依賴、選擇參數、調用、退出碼及原生資料保存；配置不含任意遠端執行片段。
- 工具來源／授權／版本後續放 `third-party-tools.md` 和 `THIRD_PARTY_LICENSES.md`，不把第三方腳本複製進目前的 A05 範本。

## 九、v0.1.0 最小驗收案例（供 B07／B08／C04）

```bash
# 預期：0（安裝已完成且本地配置有效）
netlab-c config validate
netlab-c targets validate
netlab-c targets list
netlab-s config validate
netlab-s config profiles

# 修改本地配置並返回選單，無需重啟
netlab-c targets edit --editor nano
netlab-s config edit --editor vim

# 預期：3；不執行任何實際測試
# - targets 記錄少一欄 / 重複 target_id / 70000 埠 / 非法 IPv6
# - s.conf 仍是 CHANGE_ME / unknown Profile / 非法 schedule.time
# - c.conf unknown 鍵 / 錯誤 config_version / targets_file 不存在

# 預期：2；參數使用方式錯誤
# netlab-c targets add --non-interactive 缺必要的 --id 或 --type

# 預期：8；骨架模組尚未實作
# netlab-c paired --target nat-us --profile standard
# netlab-s toolbox --modules netquality --profile quick
```

### 最小自動化測試集

- [ ] `c.conf`、`s.conf` 的標準範本與安裝器產物可被嚴格解析；安裝器必須替換 S 的 `CHANGE_ME`。
- [ ] `targets.conf` 正確處理空 IPv6、空 SSH alias、尾端 `|`、UTF-8 中文、空行及行首註解。
- [ ] 重複 ID、超範圍埠、非法 IP、非法選項、重複 INI 鍵及未知設定一律退出 `3`。
- [ ] 配置讀取沒有 `source`、`eval`、INI 插值或 Shell 片段執行。
- [ ] VPS 清單更動後重讀，不需重新啟動入口；改壞配置時不把錯誤目標交給 runner。
- [ ] `--config` 和 `NETLAB_HOME` 解析正確，普通帳號與 root 不互相污染。
- [ ] Profile override 只影響指定工具，`off` / disabled / 高負載預算為獨立安全檢查。
- [ ] schedule 在 v0.1.0 **只被解析／驗證**，不建立 systemd Timer 或 cron。
- [ ] `--help`、`--version` 在配置無效時仍正常返回 0。
- [ ] 安裝／升級不覆蓋已存在的配置、測試結果和日誌。

## 十、與 A03／A04 的接口對照及後續

| 已固定的 CLI／UI | 使用的配置 |
|---|---|
| `netlab-c targets list/show/add/edit/validate` | `c.conf:[paths].targets_file` → `targets.conf` |
| `netlab-c paired --target ID` | `targets.conf` 指定的 `target_id`；沒有 ID 不自動連線 |
| `netlab-c proxy --profile ...` | `c.conf:[proxy]`；實際出口要日後驗證 |
| `netlab-c config validate` | `c.conf` 及其 targets 路徑 |
| `netlab-s config profiles` | `s.conf:[profile.*]` + `[tool.*]`；顯示生效的抽象模式 |
| `netlab-s toolbox --modules ...` | `s.conf` Profile、工具覆寫、安全／成本欄位 |
| `netlab-s schedule ...` | `s.conf:[schedule.*]`；v0.1.0 一律 NOT_IMPLEMENTED |
| `netlab-c`／`netlab-s` 互動選單 | 使用同一配置解析器／驗證器／CLI，而非自行讀 Shell 變數 |

**A05 完成定義**：三份預設範本、欄位型別與預設、嚴格驗證、C 多 VPS、S Profile／工具覆寫／排程、根目錄與優先序、安全和版本遷移均已固定。後續 A06 定義模組執行／傳參；B07、B08 再正式實作解析器與管理命令。
