# NetworkLab 互動選單契約

- **規格識別**：A04 / Menu Contract v1
- **目標版本**：NetworkLab v0.1.0 Skeleton
- **狀態**：介面規格定稿；不表示功能已實作
- **上游依據**：`docs/commands.md`（A03 / CLI Contract v1）
- **適用系統**：macOS Client（C）；Linux Server（S，Debian／Ubuntu／Alpine 優先）

## 核心原則

1. **CLI First**：互動選單只是 CLI 的 TTY 前端；全部操作必須轉譯到 A03 已定義的 CLI／共用執行器，不得出現僅選單支援的測速邏輯。
2. **入口只有兩個**：`netlab-c` 和 `netlab-s`，不帶參數且 stdin 為 TTY 才開啟選單；非 TTY 不開啟選單，依 A03 退出 `2`。
3. **淺層導覽**：主選單控制在 8 個項目以內（不含 `0`）；管理與維護功能歸類子選單。數字是畫面位置，不是穩定 API。
4. **明確執行範圍**：選擇目標、測試模組及 Profile 與實際執行分離；高負載／高流量、更新、服務啟動和排程變更必須通過對應的安全檢查。
5. **安全預設**：`Enter` 只使用畫面明示的預設行為；不因空輸入而誤啟動高成本測試，也不自動選擇未授權工具。
6. **可恢復**：配置錯誤／模組尚未完成／工具缺失應回報狀態並返回上一層，不能把整個主選單帶崩。
7. **本地配置與資料不受影響**：退出或返回只變更互動狀態；不刪配置、不刪報告、不殺其他程序。
8. **v0.1.0 不偽裝測速**：9 個功能模組仍為佔位腳本；選單能正確派發後必須顯示 `NOT_IMPLEMENTED` 和 CLI 退出碼 `8`。

## 顯示與輸入的一般規則

### 終端顯示

- 標頭包含 `NetworkLab Client` 或 `NetworkLab Server`、版本 `v0.1.0`、當前頁面。
- 命令或操作顯示清楚的繁體中文名稱及必要的英語工具名稱，如 `NetQuality`、`iperf3`；不依靠 I、II、III 等羅馬數字。
- 主選單固定數字 `1–8` 或 `1–7`，`0` 為退出；子選單 `0` 一律返回上一層。
- 可選顯示簡要狀態：`READY`、`NOT_IMPLEMENTED`、`MISSING_DEPENDENCY`、`DISABLED`；此狀態為實際檢查或已知實作狀態，不能假設測試服務已啟動。
- 不必每次重繪整個終端或強制 `clear`；顏色只是增強，無色終端必須可用。報錯保留可讀文字。
- 待執行命令回顯 CLI 形式；含憑證／Token／私鑰的參數必須遮蔽。

### 單選與多選

| 場景 | 允許輸入 | 空白 Enter | `0` | 無效輸入 |
|---|---|---|---|---|
| 主選單 | 單一數字 | 重新提示（不執行） | 退出 | 顯示錯誤、重新提示 |
| 一般子選單 | 單一數字 | 重新提示（除非有明示預設） | 返回 | 顯示錯誤、重新提示 |
| VPS 選擇器 | `1` 至 `N`（單選） | 第一台已儲存 VPS（若存在且畫面明示） | 返回 | 不使用錯誤的 IP，重新提示 |
| Profile 選擇器 | `1` quick／`2` standard／`3` deep | 有效配置中的預設 Profile，否則 standard | 返回 | 重新提示 |
| 工具／測試模組選擇器 | `1,3,5`、`2-6`、`all`、單一數字 | 等同 `all`，**僅安全且可用的常規模組** | 返回 | 整組拒絕並重新提示 |
| 確認畫面 | `y`／`n`（不分大小寫） | 預設 `n` | 不適用 | 重新提示 |

- `all` 不得與數字混用；`1,1,2` 可去重成 `1,2`；範圍端點必須合法，依畫面順序去重；允許逗號旁空格，但不接受任意 Shell 表達式。
- 多選編號只作用於當前畫面的清單；真正呼叫時轉成固定模組 ID，例如 `netquality,tcpquality`，**不可**把 `1,2` 當成 CLI `--modules` 值。
- 主選單不接受多選；防止 `1,3,5` 造成意外執行三個不相關功能。
- `Ctrl+C`：依 A03 中斷規則退出 `130`，保存已完成的正式任務資料；`Ctrl+D`／EOF：不進入死循環，在未執行任務的提示畫面正常離開。若當前任務正在執行，交由 runner 處理取消與保存。
- 輸入錯誤不更改配置／報告；回到主選單後不得殘留上次未確認的測試選擇。

## C 端主選單：`netlab-c`

```text
NetworkLab Client  v0.1.0
────────────────────────────────────────
1. 本機設備與網路環境盤點
2. 公共網路獨立測試
3. Mac ↔ VPS 聯動測試
4. Bettbox 代理與應用測試
5. 從 VPS 下載測試結果
6. 管理 VPS 配置
7. 查看測試結果與執行日誌
8. 系統設定、診斷與更新

0. 退出
────────────────────────────────────────
請選擇 [0-8]:
```

| 項目 | 轉譯到 CLI | v0.1.0 行為 |
|---|---|---|
| C1 本機盤點 | `netlab-c inventory` | 保留入口，顯示 `NOT_IMPLEMENTED`（8） |
| C2 公共網路測試 | `netlab-c standalone --profile PROFILE` | Profile 選擇；模組未完成則退出 8 |
| C3 Mac ↔ VPS | `netlab-c paired --target ID --profile PROFILE` | 先選 VPS，再 Profile；模組未完成則退出 8 |
| C4 代理與應用測試 | `netlab-c proxy --profile PROFILE` | Profile 選擇；模組未完成則退出 8 |
| C5 下載 S 報告 | `netlab-c collect --target ID` | 先選 VPS；模組未完成則退出 8 |
| C6 VPS 配置 | `netlab-c targets ...` | 可用；詳見子選單 |
| C7 結果／日誌 | `netlab-c results ...`／`netlab-c logs list` | 可用，即使清單為空 |
| C8 系統維護 | `netlab-c config ...`／`doctor`／`self-test`／`update ...` | 可用 |

### C3／C5 共用：VPS 目標選擇器

C3 和 C5 必須共用**同一個**目標選擇元件，並讀取 `~/.networklab/config/targets.conf`。畫面範例如下：

```text
選擇 VPS  [僅單選]
1. 美西 NAT       nat-us       NAT     IPv4
2. 東京 AWS       aws-tokyo    Direct  IPv4+IPv6
3. 香港 KVM       hk-kvm       Direct  IPv4

4. 新增 VPS
5. 使用 nano 編輯 VPS 清單
6. 使用 vim 編輯 VPS 清單
7. 臨時輸入 VPS（僅本次使用）

0. 返回
請選擇 [預設 1]:
```

**編號規則**：存量 VPS 使用 `1–N`；新增、nano、vim、臨時目標依序為 `N+1` 到 `N+4`，`0` 返回。不能固定假設永遠只有三台；畫面必須依實際數量產生。若 `N=0`，提示尚無 VPS，Enter 不選擇不存在的目標。

**配置即時刷新**：選擇新增／nano／vim 完成後，先調用既有驗證器，再重新讀取目標清單並重繪；不可重啟 NetworkLab。配置驗證失敗應顯示具體行數與原因，回到目標選擇器，不得把錯誤值交給 runner。

**臨時 VPS 的契約邊界**：A03 尚未定義完整的臨時目標 CLI 旗標組。v0.1.0 將此項顯示為 `NOT_IMPLEMENTED`，不臨時寫入 `targets.conf`、不暗中把臨時目標持久化；未來若確定啟用，需先修訂 A03 CLI 契約，再開發選單行為。

**目標選中後**：確認畫面回顯名稱、`target_id`、NAT/direct、IPv4/IPv6、iperf3/MTR 埠及 SSH alias（若存在），以 `target_id` 傳遞給 CLI；不可用畫面索引作為永久識別。

### C6：管理 VPS 配置

```text
管理 VPS 配置
1. 列出 VPS 清單
2. 查看指定 VPS 配置
3. 互動新增 VPS
4. 使用 nano 編輯清單
5. 使用 vim 編輯清單
6. 驗證 VPS 清單

0. 返回主選單
```

| 選項 | CLI |
|---|---|
| 1 | `netlab-c targets list` |
| 2 | 選定 ID 後 `netlab-c targets show ID` |
| 3 | `netlab-c targets add`（TTY 逐欄位提示） |
| 4 | `netlab-c targets edit --editor nano` |
| 5 | `netlab-c targets edit --editor vim` |
| 6 | `netlab-c targets validate` |

- `targets add` 收集 A03 的八欄：顯示名稱、ID、nat/direct、IPv4、IPv6、iperf3 TCP 外部埠、TCP MTR 埠、SSH alias。選項值必須驗證；檢測到重複 ID 要求重填或取消。
- 選單不能提供 A03 未定義的 `targets delete`、`targets rename` 等直接 CLI 功能；使用者需要更改或刪除記錄時，可透過 nano/vim 編輯與驗證。
- 未安裝 nano/vim 時顯示缺少依賴，不能自動安裝套件；保留其他配置管理選項。

### C7：結果與日誌

```text
結果與執行日誌
1. 列出測試結果（最新優先）
2. 查看指定 Run ID 的摘要
3. 列出執行日誌

0. 返回主選單
```

對應 `results list`、`results show RUN_ID`、`logs list`。空目錄顯示「尚無記錄」，屬於正常成功狀態；不存在的 Run ID 則不得偽造結果。

### C8：系統設定、診斷與更新

```text
系統設定、診斷與更新
1. 用 nano 編輯 C 端設定
2. 用 vim 編輯 C 端設定
3. 驗證 C 端設定
4. 檢查系統環境與依賴（doctor）
5. 執行無網路骨架自檢（self-test）
6. 檢查有無新版本
7. 升級到指定版本

0. 返回主選單
```

對應 `config edit --editor nano|vim`、`config validate`、`doctor`、`self-test`、`update check`、`update apply --version VERSION`。升級必須輸入明確版本，展示版本差異與來源，取得明確確認；Enter 不執行更新。

## S 端主選單：`netlab-s`

```text
NetworkLab Server  v0.1.0
────────────────────────────────────────
1. VPS 設備與系統盤點
2. 公開網路測試工具
3. 管理聯動測試服務
4. 定時任務與靜默採集
5. 管理測試參數與 Profile
6. 查看測試結果與執行日誌
7. 系統診斷與更新

0. 退出
────────────────────────────────────────
請選擇 [0-7]:
```

| 項目 | 轉譯到 CLI | v0.1.0 行為 |
|---|---|---|
| S1 VPS 盤點 | `netlab-s inventory` | 保留入口，回傳 8 |
| S2 公開工具 | `netlab-s toolbox --modules IDS --profile PROFILE` | 選工具與 Profile；保留入口，回傳 8 |
| S3 測試服務 | `netlab-s service ...` | 保留入口，不啟動任何公網服務 |
| S4 定時採集 | `netlab-s schedule ...` | 保留入口，不建立 systemd Timer／cron |
| S5 配置／Profile | `netlab-s config ...` | 可用 |
| S6 結果／日誌 | `netlab-s results ...`／`netlab-s logs list` | 可用 |
| S7 診斷／更新 | `netlab-s doctor`／`self-test`／`update ...` | 可用 |

### S2：公開工具選擇流程

```text
公開網路測試工具（狀態依實際環境呈現）
1. NetQuality       網路互聯與回程       [未整合]
2. TcpQuality       TCP 品質與單流      [未整合]
3. HardwareQuality  硬體與資源性能       [未整合] [高負載可選]
4. IPQuality        IP 身分與相容性      [未整合]
5. NextTrace        指定目的地路由       [未整合]
6. MTR              TCP／ICMP 路由      [未整合]
7. Flent            負載延遲           [未整合] [高負載可選]

0. 返回主選單
輸入編號、1,3,5、2-6 或 all [預設 all（安全常規項）]:
```

- **固定的工具 ID**：`netquality`、`tcpquality`、`hardwarequality`、`ipquality`、`nexttrace`、`mtr`、`flent`。這些是預定的 `--modules` 穩定 ID；顯示編號可依介面調整。
- `all`／空白 Enter 的意義是選取**當前允許且可用的常規測試項目**，不自動包含 HardwareQuality 完整跑分、Flent RRUL／長時間壓測等高負載操作。特定工具若有輕量模式，只有在適配器明確標記「允許、可用、在預算內」才可納入。
- 缺少外部工具需顯示缺少依賴；可跳過個別工具，不導致選單整體崩潰。v0.1.0 所有工具未整合，選定後仍返回 `NOT_IMPLEMENTED`（8），不可冒充測量成功。
- 工具模組需要目標參數（如 NextTrace 指定目的地）時，後續版本由工具適配器提出提示；v0.1.0 不新增未定義的 `--destination` 等 CLI 選項。

### S2：Profile 選擇器

```text
選擇測試程度
1. Quick     低流量基礎檢查
2. Standard  常規完整測試
3. Deep      深度測試（可能消耗更多流量或資源）

0. 返回上一層
請選擇 [預設 Standard，來自 s.conf]:
```

1. 讀取 `s.conf` 的有效 `general.default_profile`；不存在時按 A03 使用 `standard`。畫面需顯示實際預設值，不能固定寫死 `Standard`。
2. 使用者可改選其他 Profile，選定後在**執行前摘要**顯示已選模組、有效 Profile、適配器生效設定、缺少依賴、流量與負載風險。
3. 預計時間、流量、資源成本只有在有可靠估算時才顯示；沒有資料時標示「未知」，不得編造數字。
4. 正式高負載項目必須經明確允許及安全確認；`deep` 本身不能代替授權。
5. 使用者確認後由 runner 調用 A03 CLI，不調用外部程式碼旁路。骨架版本不得執行任何真正的測速工具。

### S3：聯動測試服務

```text
管理聯動測試服務
1. 查看測試服務狀態
2. 啟動測試服務
3. 停止由 NetworkLab 管理的測試服務

0. 返回主選單
```

對應 `netlab-s service status|start|stop`。v0.1.0 全部回報 `NOT_IMPLEMENTED`，不代替真正服務狀態檢查。未來版本啟動前必須檢查端口衝突、外部映射、安全存取及是否會影響 Xray／sing-box；停止操作只能影響 NetworkLab 自行管理的程序。

### S4：定時任務管理

```text
定時任務與靜默採集
1. 列出定時任務
2. 新增定時任務
3. 修改定時任務
4. 啟用定時任務
5. 停用定時任務
6. 執行指定任務（非互動）
7. 查看排程執行日誌

0. 返回主選單
```

對應 `schedule list|add|edit JOB_ID|enable JOB_ID|disable JOB_ID|run JOB_ID --non-interactive|logs [JOB_ID]`。v0.1.0 均為保留入口、退出 `8`。不得實際安裝 Timer、修改 crontab，或在退出選單後暗中排程。

### S5：測試參數與 Profile

```text
管理測試參數與 Profile
1. 查看 Quick／Standard／Deep 設定
2. 使用 nano 編輯 S 端設定
3. 使用 vim 編輯 S 端設定
4. 驗證 S 端設定

0. 返回主選單
```

對應 `config profiles`、`config edit --editor nano|vim`、`config validate`。編輯後即時驗證與重新載入；Profile 顯示**配置值**，不把抽象 quick/standard/deep 直接當成外部工具已支援的命令列參數。

### S6：結果與執行日誌

```text
結果與執行日誌
1. 列出測試結果（最新優先）
2. 查看指定 Run ID 的摘要
3. 列出執行日誌

0. 返回主選單
```

對應 `results list`、`results show RUN_ID`、`logs list`。排程專屬日誌由 S4 的 `schedule logs` 提供（v0.1.0 尚未實作）。

### S7：系統診斷與更新

```text
系統診斷與更新
1. 檢查系統環境與依賴（doctor）
2. 執行無網路骨架自檢（self-test）
3. 檢查有無新版本
4. 升級到指定版本

0. 返回主選單
```

對應 `doctor`、`self-test`、`update check`、`update apply --version VERSION`。未輸入版本與未確認不得升級。

## 共用互動流程與狀態轉換

```text
TTY 啟動 netlab-c / netlab-s
          |
          v
       主選單 -------- 0 / EOF -------> 退出 (0)
          |
          v
       子選單 -------- 0 ------------> 上一層
          |
          v
  解析選擇 / 讀取配置
          |
          +-- 格式錯誤 -------------> 保留本頁、重新提示
          |
          +-- 需要目標 / Profile ---> 對應單選器
          |
          v
  回顯執行計畫／風險／實際 CLI
          |
          +-- 拒絕或返回 -----------> 上一層
          |
          v
    CLI 參數驗證與 runner
          |
          +-- completed/failed/timeout/partial
          |       -> 顯示退出碼／輸出位置
          |
          +-- not_implemented ------> 顯示代碼 8
          |
          v
      返回功能頁 / 主選單
```

- 選單調用必須共用 A03 CLI 的驗證、runner 和退出碼。CLI 解析不得被 UI 跳過。
- 選單可保留本次頁面的暫時選項以便返回，但不應擅自持久化最近選擇作為 `targets.conf` 的修改。
- `--non-interactive` 禁止所有 `read`、編輯器、Profile/VPS 選擇器及確認提示；其缺失資料必須由配置或旗標滿足，否則回傳對應錯誤碼。
- UI 的「預設 VPS 第一台」**只適用明示的 TTY VPS 選擇器**。CLI `paired`／`collect` 非互動仍必須明示 `--target`；不得把畫面預設延伸為無參數自動連線。
- 外部工具的依賴狀態須區分「未安裝」和「尚未整合」，不能把兩者都表述成測試失敗。
- `--dry-run` 屬於 CLI 預覽；對未實作的模組按 A03 回傳 `8`，不得做出已具體生成外部工具命令的假象。

## 配置／退出／安全細節

- 配置檔案讀取不使用 `source`／`.` 直接執行未受信任內容；`targets.conf` 的分隔格式為八欄、必須驗證欄位與數值。
- 配置編輯時使用使用者所選 nano／vim；離開後驗證並重新載入，失敗時不啟動測試，且提示修復方式。
- 可預期錯誤（格式無效、找不到指定 target、空報告、外部工具缺失、`NOT_IMPLEMENTED`）以明確資訊呈現，待使用者確認或按 Enter 後返回選單；不直接把 CLI stderr 洗掉。
- 每個需要改變系統狀態的操作（更新、啟用排程、啟動監聽服務）都使用預設拒絕的確認流程；`self-test` 僅寫入隔離的臨時／測試資料，絕不覆蓋正式結果。
- 終端為非互動環境（無 TTY）時禁止切換到選單；任何組件不能在 CI、cron、ssh 無 TTY 會話中意外卡住。

## v0.1.0 驗收清單（A04）

- [ ] C 主選單 8 項、S 主選單 7 項及所有子選單完整顯示；`0` 正確退出／返回。
- [ ] 沒有 TTY 的 `netlab-c`／`netlab-s` 顯示用法，退出 `2`，不阻塞。
- [ ] 非法輸入或重複多選不造成崩潰或意外執行；`1,3,5`、`2-6`、`all` 正確解析。
- [ ] VPS 選擇清單依 targets.conf 動態生成，使用 `target_id` 而非畫面序號。
- [ ] 編輯或新增 VPS 後即時驗證、重新載入；沒有 VPS 時 Enter 不選擇假目標。
- [ ] S 端 Profile 預設依 s.conf 呈現，選擇的模組 ID 與 CLI 一致。
- [ ] 選單行為與 `netlab-c`／`netlab-s` 同等 CLI 呼叫具有一致錯誤碼與結果。
- [ ] 9 個佔位模組正確顯示 `NOT_IMPLEMENTED` 並回傳 `8`；不實際進行測速、啟動服務或排程。
- [ ] 升級與高負載操作不因 Enter 自動執行；實際參數及風險先回顯。
- [ ] Ctrl+C／EOF 能正確退出，並不破壞既有配置及報告。
- [ ] `doctor`、`self-test`、`results`、`logs` 等骨架已完成命令可透過選單調用。

## 與 A03 的一致性及保留事項

1. **不新增公開 CLI 子命令**。C 端的「臨時 VPS」是原始架構保留的 UI 位置，但 A03 沒有足夠的對應 CLI 介面；因此 v0.1.0 僅展示佔位，不實際接入。
2. **僅確定 UI 與調度契約**。第三方測試的真實參數、依賴檢測、成本估算、NAT 埠映射、S 排程均屬後續模組實作。
3. **主選單呈現穩定，內部項目可依擴充調整**。外部自動化應使用 CLI 子命令／工具 ID／target_id，不應依賴 UI 編號。
4. **下一個工作單元**：A05 配置規範；B03／B04 實作入口前，A06 模組調用契約須同步確認共同的 runner 介面。

**A04 完成定義**：C／S 主選單與子選單、VPS 與 Profile 選擇器、工具多選、Enter／返回／EOF／Ctrl+C、CLI 映射、安全確認、佔位模組與驗收情境全部固定。
