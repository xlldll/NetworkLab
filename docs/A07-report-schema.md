# NetworkLab 統一報告與 JSON Schema 契約

- **規格識別**：A07 / Report & Evidence Contract v1
- **報告 Schema**：`schema_version = "1.0"`
- **目標版本**：NetworkLab v0.1.0 Skeleton
- **狀態**：資料格式與校驗範例完成；並非 Report Writer、測速或匯入功能已實作
- **上游依據**：A03 `commands.md`、A04 `menus.md`、A05 `configuration.md`、A06 `modules.md`
- **下游實作**：B05 Runner、B09 Report Writer、B11 Self-test、C05 故障保存測試

## 一、設計目標與不可混淆的邊界

A07 固定測試報告的 **身分、來源、時間、狀態、檔案索引、統計摘要與證據適用範圍**。每個實際執行的模組只把原生輸出與結構化交付資料送回 Runner；只有 Runner／`lib/report.py` 可以發出正式報告。

1. **原始證據優先**：官方 JSON、NDJSON、CSV、Flent 原生檔案，以及不支援機器格式的 TXT stdout／stderr 原樣保存。`summary` 不取代原始證據。
2. **配置不等於性能**：`target_id`、NAT/direct、IP、BBR 等設定值不等於實測結果；數據需標明來源（`observed`、`configured`、`provider_declared`、`unknown`）。
3. **不偽造結果**：未知用 `null`，不把未知吞吐、丟包或 CPU 限制寫成 `0`；不把成功執行指令等同測試成功。
4. **測量邊界清晰**：`evidence_scope` 必須指定證據適用的是哪條路徑／哪一類操作，不能把公共探測結果解讀成 C↔S 的實測。
5. **身份與報告分離**：一個 Run 可以包含多項測試；同一個 Run 的 manifest、summary、raw 共用 `run_id` 與 `run_uuid`。
6. **安全與可移植性**：報告不能含密碼、Token、私鑰、可使用的認證 URL；不保存依賴某個人的絕對本機路徑。
7. **v0.1.0 不測速**：九個佔位模組回 `NOT_IMPLEMENTED`（退出 `8`），**不得建立虛假的正式測量報告**。Self-test 及本文範例使用獨立的測試路徑、`synthetic: true`。

## 二、角色、路徑與扁平儲存

預設根目錄為 `~/.networklab/results/`，`--output-dir` 覆蓋的仍是這個**結果根目錄**；任何模組不得直接把它解釋成單一檔案的目的地。

```text
~/.networklab/
├── app/                       # GitHub 安裝的程式碼；與結果無關
├── config/                    # 使用者配置；更新不得覆蓋
├── results/
│   ├── c/
│   │   ├── local/             # c-inventory、c-standalone
│   │   ├── proxy/             # c-proxy
│   │   └── <target_id>/       # c-paired
│   ├── s/
│   │   └── <server_id>/       # s-inventory、s-toolbox
│   └── imported/
│       └── <server_id>/       # C 匯入 S 端的原始副本
└── logs/                      # 運作與管理日誌，不等於報告資料
```

- 這裡只建立相應端實際需要的目錄。C-Collect 將來可能另外產生**匯入收據**，但 S 原始報告必須留在 S 主機上。
- **不建立年／月／日多層目錄**。若同一 `target_id` 更換供應商或 IP，仍按穩定 ID 分類，真正的 IP／ASN／介面等寫入測試元資料。
- 整個 Run 所有**可分享檔案**位於同一扁平結果分類資料夾中。正式報告引用相對檔名，不引用 `~/.networklab/tmp` 或 `/Users/...`。
- 操作性日誌可獨立存於 `logs/`。若 stdout／stderr 需要成為證據，Runner 應將其複製成**結果目錄內的獨立原生 TXT 檔案**並索引。

## 三、時間、run_id、run_uuid、檔名

### 時間語義

- 所有**對外報告時間**格式：`YYYY-MM-DDTHH:mm:ss+08:00`；檔名時間：`YYYY-MM-DD-HH-mm-ss`。
- `UTC+08:00` 是固定偏移，不能修改主機時區，也不以主機當前時區直接組成檔名。
- 檔名時間取本次 Run 的**開始時間**；同一 Run 的 manifest／summary／raw 共用這一時間段。
- JSON 記錄 `started_at`、`finished_at` 與 `duration_ms`。實際耗時優先由單調時鐘量測；跨主機時間戳不能假定完全同步。
- 未完成或遭非正常結束時，未知 `finished_at`／`duration_ms` 可以為 `null`，不可假裝測試完整。

### 兩層識別

- **`run_id`（可讀）**：`<YYYY-MM-DD-HH-mm-ss>-<scope_id>[-NN]`。例如 `2026-10-21-18-31-05-nat-us`，同秒同分類已有 Run 時 `...-nat-us-01`。`NN` 從 `01` 遞增，不覆蓋；標準化 Run 內保持不變。
- **`run_uuid`（跨設備唯一）**：符合 UUIDv4 語法的隨機識別碼。兩台 C 或 S 可以碰巧有相同 `run_id`，但 `run_uuid` 仍須不同。**跨主機匯入與去重以 `run_uuid` 為權威識別**；不能只靠時間字串。
- **`correlation_id`（可選）**：C／S 真正聯動執行時可傳入相同的 UUID，以關聯**不同主機各自的 Run**；兩端各保留自己的 `run_uuid`／`run_id`。若沒有可驗證的聯動標記，必須為 `null`，不能僅靠相近時間硬判為同一個測試。
- **`test_id`**：跨 Run 穩定的子測試語義 ID，例如 `iperf3-p1-download-ipv4`；**`attempt`** 為同一 Run 中該子測試的第幾次執行，從 1 開始。`(test_id, attempt)` 在一份 summary 內不可重複。
- `scope_id` 決定分類與可讀檔名：C 的 inventory／standalone = `local`、proxy = `proxy`、paired = 目標 `target_id`；S = `server_id`。S 的 `server_id` 不能是 `CHANGE_ME`。

### 檔名規則

`<role>-<test>-<scope_id>-YYYY-MM-DD-HH-mm-ss[-NN].<ext>`；`role` 使用小寫 `c`／`s`，`test` 使用小寫安全 slug。範例：

```text
c-manifest-nat-us-2026-10-21-18-31-05.json
c-summary-nat-us-2026-10-21-18-31-05.json
c-tcp-connect-ipv4-nat-us-2026-10-21-18-31-05.json
c-iperf3-p1-download-nat-us-2026-10-21-18-31-05.json
s-manifest-nat-us-2026-10-21-18-40-00.json
s-summary-nat-us-2026-10-21-18-40-00.json
s-tcpquality-nat-us-2026-10-21-18-40-00.txt
```

- `manifest`、`summary` **不能直接叫 `manifest.json`／`summary.json`**：會與扁平目錄中其他 Run 衝突。
- **一次 Run 的 `[-NN]` 由 Runner 在建立 Run 時統一分配**；若已分配 `-01`，該 Run 的 manifest、summary、raw 都沿用 `-01`。同一 Run 內不同資料檔若仍有名稱衝突，需使用不同的穩定 test slug／attempt 後綴，不能覆蓋。
- 以有排他建立語義的方式分配 Run 識別（例如 `O_EXCL` 工作鎖或私有預留紀錄）；單純先查檔案是否存在再寫入，無法處理平行程序競爭。
- 檔名只是便於人工尋找，不應依賴從連字號切割檔名來推斷 `test_id` 或目標，因為兩者本來就可能包含 `-`；應讀取 manifest 的結構化欄位。

## 四、每個 Run 的兩個標準 JSON + 原生檔案

| 類型 | 作用 | 位置與責任 |
|---|---|---|
| **Manifest** | 本次執行的身份、時間、退出狀態、有效參數、原生檔案索引與 SHA-256 | Runner／Report Writer 寫入 `*-manifest-*.json` |
| **Summary** | 各子項狀態、測量範圍、工具、參數、核心 metrics、警告與錯誤 | Runner／Report Writer 寫入 `*-summary-*.json` |
| **Raw files** | 工具完整原生輸出，依工具支援 JSON／NDJSON／CSV／TXT／Flent 原生資料 | 模組於工作區產生，Runner 保留並索引 |

### Manifest 必要欄位

- `schema_version = "1.0"`、`report_type = "manifest"`、`synthetic`。
- `run_id`、`run_uuid`、`correlation_id`、`role`、`module_id`、`task_kind`、`scope_id`、`target_id`、`server_id`。
- `profile`、`started_at`、`finished_at`、`duration_ms`、`status`、`exit_code`。
- `requested_tests`（本次明確請求的項目）與 `effective_parameters`（**經遮蔽**、實際生效的安全參數）。
- `networklab_version`、`files[]`、`errors[]`、`warnings[]`。
- `files[]` 每項包含 `path`（**同目錄安全相對檔名**）、`kind`（summary/raw/stdout/stderr/other）、`format`、`size_bytes`、`sha256`，以及可選 `test_id`。

**Manifest 不索引自己的 sha256**，避免自我參照造成無窮更新。其他可分享檔案（包括 summary）應由 manifest 記錄 SHA-256。完整性檢查不等於作者身份驗證；來源可信性依 SSH 身分、固定工具版本及授權來源另行判斷。

### Summary 必要欄位

- 相同 Run 的身份與時間：`schema_version`、`report_type = "summary"`、`synthetic`、`run_id`、`run_uuid`、`correlation_id`、`role`、`module_id`、`scope_id`、`target_id`、`server_id`、`profile`、`started_at`、`finished_at`、`duration_ms`、`status`、`exit_code`。
- `tests[]`：每項包括 `test_id`、`attempt`、`status`、`evidence_scope`、`data_provenance`、`tool`、`network`、`parameters`、`metrics`、`raw_files`、`errors`、`warnings`。
- Summary 僅存**標準化核心指標**，不把公開腳本幾千行的資料全部展開／改寫；原始資料由 manifest 索引。
- `raw_files` 必須指向 manifest 中 `kind=raw` 的相對路徑；不可指向未成功保存的臨時檔。

## 五、證據、資料來源和網路測量方向

### `evidence_scope`（A06 預留，A07 正式固定）

| 值 | 證據範圍 | 不能直接推導 |
|---|---|---|
| `local` | 單端本機配置／資源／低負載快照 | 跨境網路質量 |
| `public_path` | C 或 S 到指定公共探測服務的路徑 | C↔S 真正業務路徑 |
| `c_s_direct` | Mac ↔ 指定 VPS 的原生連線 | Bettbox 代理完整體驗 |
| `proxy_path` | 經指定代理路徑到某測試目標 | 所有目標都走相同代理出口 |
| `third_party_service` | YouTube／Emby／AI 等服務側觀察 | ISP 某個節點一定擁塞 |

`data_provenance` 用 `observed`／`configured`／`provider_declared`／`unknown` 表示**資料是實測、設定、商家宣告還是不明**；這與 `evidence_scope` 是正交維度（例如本機觀察到 qdisc：`local + observed`）。同一子測試若包含不同來源，應將來源差異放入 `metrics` 的欄位 Metadata 或拆分測試，不得以單一 `observed` 包裝整包供應商宣稱。

### `network` 結構

- `ip_family`：4、6 或 `null`（未知／不適用）。
- `transport`：`TCP`、`UDP`、`ICMP`、`TLS`、`HTTP`、`QUIC` 或 `null`；當傳輸層與應用層同時需要時可放入 `parameters` 補充。
- `direction`：`C_TO_S`、`S_TO_C`、`C_TO_PUBLIC`、`S_TO_PUBLIC`、`PROXY_TO_TARGET`、`LOCAL` 或 `null`。
- `proxy_mode`：`direct`、`proxy`、`unknown` 或 `null`。配置顯示不走代理並不能保證沒有 TUN 接管；實際是否驗證可記在 `parameters`。

### 核心數據與單位

建議固定語義清楚的鍵名，避免只有 `speed: 50` 這種無法比較的數據：

| 指標 | 建議欄位 | 單位及注意 |
|---|---|---|
| TCP RTT P50／P95／P99 | `tcp_connect_p50_ms` 等 | 毫秒；同時記樣本數 `sample_count` |
| 吞吐 | `throughput_mbps` | Mbit/s（不是 MB/s）；記方向、P1/P4/P8 |
| Bytes | `transferred_bytes` | bytes（不是 MB）；需要時寫明測量方向 |
| 丟包 | `loss_pct` | 0–100%；注明 ICMP／UDP／真實傳輸類型 |
| 重傳 | `tcp_retransmits_count` | 整數次數；避免無分母就判定品質 |
| 成功率 | `success_pct` | 0–100%；與 `sample_count` 一併提供 |
| CPU | `cpu_usage_pct` | 定義進程／核心／整機、採樣窗口與統計口徑 |
| 延遲標準差 | `rtt_stddev_ms` | 毫秒；注明樣本範圍 |

`metrics` 可按工具擴充，但**不得把沒有資料當成零**。當 P99 樣本不足以穩定估計時，應保留 `sample_count` 和 `warnings`，而不是輸出看似精確的可靠性結論。A07 不定義性能合格／不合格閾值，也不做 AI 因果歸因。

## 六、狀態、退出碼與子項彙總

沿用 A03 的公開退出碼與 A06 的狀態對應：

| 外部退出碼 | `status` | 規則 |
|---:|---|---|
| 0 | `completed` | **全部被要求項目真正完成** |
| 2／3／4／5／9／10 | `failed` | 分別保留具體錯誤代碼／原因 |
| 6 | `timeout` | 已完成子項與原始資料仍應保留 |
| 7 | `partial` | 有成功且另有失敗／跳過的子項 |
| 8 | `not_implemented` | 已註冊但尚未實作；**骨架階段不建立正式測量報告** |
| 130 | `interrupted` | Ctrl+C；盡可能封存已取得證據 |

- `skipped` 是**子測試**狀態，可因工具不存在、明確安全排除等原因出現；整批全 skipped 不得回 completed。
- 多工具集合的未選項目／Profile 明確 `off` 項目，不屬於 `requested_tests`，不應使整批無端變 partial。
- 模組原始退出碼如與 Runner 的對外退出碼不同，Runner 的操作日誌必須保留兩者；在 summary 的 `parameters`／測試 errors 可保留子工具原始退出碼。
- JSON 格式有效只能證明**格式正確**，不能證明測試成功或資料真實。`status`、退出碼、子測試個數、檔案雜湊必須做額外跨檔一致性檢查。

## 七、原生資料格式與產生順序

### 保存優先序

1. 工具提供原生 JSON：直接保存，不先縮減；驗證 JSON 結構是否可解析，並保留工具版本。
2. 工具提供 NDJSON／CSV／Flent 原生檔：保留原樣，`format` 指定確切類型；不能將 NDJSON 誤當單份 JSON。
3. 只有文字輸出：保留 UTF-8 stdout／stderr，記錄原生工具退出碼。
4. 缺資料時記錄 error／warning，不製作假 raw 檔案填空。

### 正式生成順序

```text
Runner 預檢 → 建立唯一 run_id/run_uuid → 建立 0700 私有工作區
    ↓
模組輸出 raw 與安全的結構化結果 → Runner 核驗路徑與狀態
    ↓
原子保存原生檔案／stdout／stderr → 寫 summary（fsync/replace）
    ↓
計算檔案長度與 SHA-256 → 最後原子寫 manifest
    ↓
驗證 manifest／summary 的身份一致與索引可讀 → 返回 CLI 退出碼
```

- 原子保存：相同目錄中以排他方式寫入臨時檔，完成後依平台可攜的安全提交方式替換**本次自己預留**的輸出檔，不改寫其他 Run；重要資料應 flush／fsync。僅靠 `os.replace()` 不能防止不同 Runner 間的覆蓋競爭，必須先確立本次檔案擁有權。
- **Manifest 最後提交**作為這次 Run 完成封存的信號；若在保存中崩潰，可能留有孤立 raw／summary，未來 `doctor`／recovery 可檢出，不能當成完整有效報告。
- 中斷／超時的報告可為 `partial`、`timeout`、`interrupted` 等；不可憑已寫下 summary 就推論所有工具結束。
- 任何 JSON 格式有效性測試、索引檔存在性、SHA-256 對照可在**無網路環境**完成；這是 B11 Self-test 的核心。

## 八、C／S 聯動、SSH 匯入與比較基準

- C-20 的 C 端 Run 與 S 端資源監控 Run 可以透過 `correlation_id` 關聯，不要求不同設備使用同一 `run_id` 或互相信任時鐘。
- C-Collect 在遠端授權下載時保留 S 的 **manifest、summary、raw 的原始位元組、`run_uuid` 與原檔名**。不會在下載後刪除 S 端原件。
- 匯入後校驗 SHA-256 與 Summary 內部身份。若同名但不同 `run_uuid`，必須拒絕無聲覆蓋；採用不覆蓋的安全衝突策略，必要時把多份來源保存在可驗證的隔離空間，並產生**獨立的匯入收據**。不可以偷偷改掉來源 manifest 的路徑或散列值。
- C 無 SSH 通道時標明 unavailable，不額外暴露未受控 HTTP 檔案服務。
- 歷史比較至少應檢查：設備／路徑身分、IP Family、方向、transport、Profile、測試參數、工具版本、實測時段，以及 `evidence_scope`。缺條件時只能標示「不可直接比較」，不能算出虛假的因果推論。

## 九、安全、隱私、Schema 演化

- 寫報告前對有效參數與工具命令行做**認證資訊遮蔽**，不記錄 `Authorization`、Cookie、SSH 私鑰、代理憑證、Token、帶秘密查詢字串的 URL；必要時只記匿名化目標／端口。
- C 的公網 IP、S 的服務地址屬於可能敏感的網路資訊，預設報告只保留為診斷需要的最小資料；公開分享前仍須由使用者審核。
- JSON 統一採 UTF-8；整數及浮點需為有限值（不允許 NaN／Infinity）。欄位未知使用 `null`，不省略 Schema 規定的必要欄位。
- `schema_version = "1.0"` 與 A05 的 `config_version = 1`、產品 `v0.1.0` 是**三種不同版本**，不應混用。
- 新增非破壞性 `metrics` 鍵可以維持 1.0；更改必填欄位、既有鍵的單位／語義、`evidence_scope` 值、識別規則，需發佈新版 Schema 和轉換／兼容策略，不默默覆蓋舊檔。
- 目前正式 JSON Schema（Draft 2020-12）置於 `schemas/manifest.schema.json`、`schemas/summary.schema.json`。兩份 example 置於 `examples/`，**只驗證格式，不代表任何真實網路性能結果**。

## 十、v0.1.0 骨架與測試資料

- 若呼叫 `netlab-c paired --target nat-us`，配置有效但模組未完成：顯示 `NOT_IMPLEMENTED`，退出 `8`，**不產生正式測量 manifest、summary、raw**。
- `netlab-c self-test`、`netlab-s self-test`：可在隔離的臨時結果根目錄寫入 `synthetic: true` 的示例，驗證 Schema／時間／hash／IO；Self-test 資料不得混入正式歷史測量清單。
- `results list` 在尚無正式結果時顯示空集合，不能把 README 中的範例誤作真實歷史報告。

### A07 驗收案例（規格；實作在 B09／B11／C05）

| ID | 驗收事項 | 預期 |
|---|---|---|
| R01 | 同一 Run 寫多項 raw | `run_id`／`run_uuid` 相同，`test_id` 不混淆 |
| R02 | 同秒連續執行 | 使用 `-01`／`-02`，不覆蓋舊檔 |
| R03 | 多個 Runner 平行啟動 | Run 識別排他分配，沒有競態覆蓋 |
| R04 | 同名 Run 從兩台機器匯入 | 按 `run_uuid` 區分，不覆蓋 |
| R05 | 時區為 UTC 或美西 | 仍以 `+08:00` 輸出，不修改主機時區 |
| R06 | Raw JSON 與 NDJSON | 分別標識，保留完整原生資料 |
| R07 | summary 指向 raw | raw 確實存在於 manifest.files 且 `kind=raw` |
| R08 | 任一 raw 被改動 | SHA-256 校驗失敗，報告標記損壞 |
| R09 | 所有子項 skipped | 絕不可回報 `completed`／退出 0 |
| R10 | 模組退出 8 | 不寫假的正式測量檔案 |
| R11 | 模組執行中 Ctrl+C | 保存已完成結果，退出 130 |
| R12 | 產生報告時被 SIGKILL | 不產生半份看似有效的 manifest；允許 orphan 暫存資料 |
| R13 | 已知 loss=0、未知 loss=null | 兩者可區分 |
| R14 | 含機密 Token 的配置 | 分享報告與日誌無 Token |
| R15 | C／S 真正聯動 | 相同 `correlation_id`，各自 Run 身分不變 |
| R16 | JSON Schema 驗證範例 | manifest、summary 均通過，範例標記 `synthetic=true` |

## 十一、跨檔一致性驗證（JSON Schema 以外）

JSON Schema 無法自行驗證跨檔 hash、時間順序、檔名擁有權或多個 item 的語義關聯。B09/B11 必須另外驗證：

1. manifest 與 summary 的 `run_uuid`、`run_id`、`role`、`module_id`、`scope_id`、`started_at`、`status`、`exit_code` 完全一致。
2. manifest.files 中的 summary 檔案只有一份且校驗碼正確；每個 `raw_files[]` 都索引到存在的 `kind=raw` 文件。
3. `test_id + attempt` 不重複、`requested_tests` 與 tests 覆蓋範圍一致；只有在所有必需項目完成時允許 `status=completed`。
4. 檔名遵守 `role-test-scope-time[-NN]`，實際檔名／內容的時間段及本 Run 佔有權對應。
5. 所有 `files` 均在這次 Run 的受控分類目錄中，不能包含相對路徑穿越、符號連結跳出、任意絕對路徑。
6. `finished_at` 不得早於 `started_at`（注意主機時間校正可能造成牆鐘異常，此時必須保留 warning，不要負 duration）；`duration_ms` 為非負或 `null`。
7. 若 `synthetic=true`，只允許在 Self-test／範例上下文，不可偽裝成正式網路量測。

**A07 完成定義**：固定兩份標準 JSON、原生檔案、時間／身分、證據範圍、狀態、完整性、匯入關聯和驗收條件。A08 可將這些規則整合進總體架構文件，B09 才開始實作 Report Writer。
