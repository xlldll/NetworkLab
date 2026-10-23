# NetworkLab C04：CLI、配置與非互動執行全面驗收

## 目的

C04 是 Phase C 的**跨平台離線驗收工具**，不是新測速模組；不修改 B01–B13 的 CLI、Runner、配置或報告實作。其目的是把 C、S 兩端的 CLI 路由、退出碼、配置管理、無 TTY 執行及安全邊界，放到同一套可重複執行的測試中。

適用 macOS arm64／Intel、Debian／Ubuntu、Alpine（Python 3.8+、Bash、POSIX `sh` 必須可用）。**通過測試只證明該主機的離線行為，不代表 iperf3、NextTrace、MTR、OpenRC、NAT 或實際 VPS 連通性驗收成功。**

## 如何執行

合併 C04 增量包到既有 Repository 根目錄，執行：

```sh
sh tests/test-c04-all.sh
```

也可以：

```sh
python3 -B tests/test-c04-contract.py
```

為了調查問題而保留測試目錄：

```sh
sh tests/test-c04-all.sh --keep
```

正常輸出尾端：

```text
[C04] PASS: CLI / configuration / non-interactive contract; offline sandbox, no probes, no user-data changes.
[C04] Host=linux; tested C and S in separate isolated homes.
```

Host 會依平台顯示 `darwin` 或 `linux`。若出現 `[C04] FAIL` 代表驗收失敗，退出碼為 `1`；不要將其算為通過。測試環境不會寫入操作者正式 `~/.networklab`。

## 隔離方式與安全界線

C04 在系統臨時目錄建立新 `HOME` 與 `NETLAB_HOME`，分別安裝獨立的 C、S。為防止未來正式模組實作後誤觸測速，C04 **只在私有原始碼副本**中，把五個 C 與四個 S Worker 暫時替換為返回 `8` 的安全佔位腳本。原始 Repository 的 Worker 不會被修改。

另在 PATH 前端注入本地 `curl`／`wget`／`iperf3`／`mtr`／`nexttrace`／`ping`／`ssh`／`traceroute` 等拒絕型測試替身；如果這些命令被呼叫，會寫入沙盒內的標記並返回 `98`，測試不得通過。腳本從不呼叫 `update check` 或真正 `update apply`，不需要 GitHub Access Token，也不執行 OpenRC、Cron 或任何網路探測。

**邊界：** 這是程式層的離線測試，不是 Linux Network Namespace 或 macOS Sandbox 的系統級網路禁止環境。測試會實際啟動 Python、Bash、POSIX `sh`，但不主動聯繫任何遠端主機。

## 覆蓋項目

- CLI：`--help`、`--version`、非 TTY 缺省命令、未知命令／旗標、重複旗標、不相容選項、錯誤位置參數、錯誤 Profile、`--limit` 驗證及更新版本固定。
- 退出碼：`0` 成功、`2` CLI 用法錯誤、`3` 配置錯誤、`8` 尚未實作、`9` 符號連結安全攔截。
- C 端：`config validate`、`targets list/show/validate/add/edit`、乾跑不修改檔案、合法新增、重複與無效資料拒絕、`paired`／`collect` 的目標要求與佔位返回值。
- S 端：`config validate/profiles/edit`、Toolbox 模組白名單與重複值、`service`／`schedule` 尚未實作、未啟動排程。
- 檔案安全：配置保留、無效覆寫、配置檔案符號連結攔截、CLI 模組佔位期間不寫入正式 Report、無 Context、權限保護。
- 安裝：分別在隔離環境建立 C、S，安裝前的 `--dry-run` 不應留下檔案。

## 重要已知行為與限制

1. **C 端 `inventory` 的隱含配置是可選的。** 對 C 端而言，移除預設 `c.conf` 後，`netlab-c config validate` 返回 `3`，而 `netlab-c inventory --non-interactive` 仍可採取 Runner 預設值並返回佔位碼 `8`；這是現有 B05 Runner 契約。S 端 `inventory` 則要求 `s.conf`，缺少時返回 `3`。C04 按現行行為驗收，**未擅自變更設計**。若後續想強制 C 測量必須有配置，需另外修改 Runner 契約與回歸測試。
2. 測試的 `targets add` 是發生在沙盒裡，**不是**向你真實的 `targets.conf` 加入任何 VPS。
3. `results`、`logs` 的唯讀介面已驗證；報告生成與損壞後保留、原子提交、惡意 Raw Data 等深入故障案例屬於 **C05**。
4. 真正跨版本更新／回滾，以及 GitHub Release 與 CI 屬於 B13／C06／C07 專項驗收，不由 C04 冒充完成。
5. **請只把 C04 增量包合併到你已發布 `v0.1.1` 的 Repository。** 用來開發 C04 的舊整合快照，其 `lib/common.sh` 仍標記 `v0.1.0`；增量包完全不包含此檔案，也不替換你的正式程式。正式 v0.1.1 的部分 CLI 幫助或配置狀態訊息仍可能含 `v0.1.0` 靜態標籤，應在後續版本獨立修正，不更動已發布 Tag。

## 開發環境驗證紀錄

以 C03 整合原始碼建立 C04 測試，在本地 Linux 開發環境以 root 跑通 **104 項 `[PASS]`**，以普通使用者（`nobody`）也跑通 **104 項**。另外獨立執行 B12 18 項、B13 19 項回歸，均通過。B12 串接全套測試因執行環境超時而未完成，不能算全套通過。Mac、Alpine、Debian／Ubuntu 實機須各自執行以建立對應驗收紀錄，不可以此開發環境結果代替。C04 不更動 B01–B13 生產程式碼。
