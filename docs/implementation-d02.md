# D02：macOS C Inventory 唯讀網路環境盤點

## 範圍及執行方式

- 基線：`phase-d/d01-s-inventory` commit `6ea076bdf1c02195e941a125a2d1454af7967ba4`。D02 為開發增量，**不是 v0.1.1 Release**。
- 正式 Worker：`c/c-inventory.sh` → `lib/c_inventory.py`；D01 S Inventory 不變。
- 操作系統：macOS，Python >=3.8 + Bash，無 root、無第三方下載、無 sudo。
- 一次操作：`bash netlab-c.sh inventory --non-interactive`。單次 Mac 驗收：`sh tests/test-d02.sh`。
- 本機指令：`ifconfig -a`、`networksetup -listallhardwareports`、`route -n get default`、`route -n get -inet6 default`、`scutil --dns`、`scutil --proxy`、`sw_vers -productVersion`。
- 以上命令只查詢系統配置與核心路由表，**不發送主動外部探測資料包**；未整合 goecs，因為它是 Linux VPS 綜合盤點工具，並不適合這一個 macOS 模組。

## 輸出內容與限制

- `c-local-environment.json` 是由工具輸出解析後的有限欄位，不保存原始命令行輸出。只擷取介面名、網卡類別標籤、UP 狀態、MTU、IPv4/IPv6 位址、預設路由介面及閘道、DNS nameserver、系統代理啟用布林值、utun 名稱。
- **不查詢也不保留** Wi-Fi SSID、MAC 位址、代理伺服器主機／埠、PAC URL、搜索域、Token、憑證、電腦名稱；完整外部工具 stdout／stderr 不落盤。
- 有 `utun*` 介面不代表 VPN/TUN 一定已接管流量。`ipv4_default_uses_utun` 只能描述預設路由，不排除策略路由或其他流量攔截。
- 系統代理開關僅表示 SystemConfiguration 的設定，不證明特定應用一定採用該代理。
- 「iPhone USB」標籤、`172.20.10.1` 閘道為**啟發式線索**，不可作為熱點已確認證據；Wi-Fi SSID 不檢測，所以不能可靠區分 Wi-Fi 接入一般路由器還是 iPhone 熱點。
- 公網 IP／ISP／ASN 均記 `null`，不呼叫外部 API，不推定無 TUN 或無代理。
- DNS 是目前已配置的 resolver 集合，並非實際某域名最終使用哪台 DNS 的證據。
- 非核心命令缺失，欄位記 `null` 與 `available=false`，**不將未知誤寫成 0/false**；核心 `ifconfig -a` 不可讀／不可解析則 fail-closed。
- Private Raw 可含本機 IP 與閘道，在分享報告前應由使用者審查，不應直接公開。

## B09 契約及安全

- 私有工作區：`raw/c-local-environment.json`、`worker-report.json`，模式由 OS 及既有 Runner 保護。Report Writer 才可發佈 `Manifest`、`Summary` 和 `Raw` 並校驗 SHA-256。
- 一個 `c-local-environment` 測項；`evidence_scope=local`、`data_provenance=observed`、`synthetic=false`。
- 成功退出 `0`，非 macOS `4`，核心採集失敗 `5`，偽造／缺失 Context `9`，`--dry-run` 由既有 Runner 處理為 `8`，不生成正式報告。
- 無 Shell 插值執行、無網路探測、無系統寫入、無安裝動作；子命令 6 秒 timeout，執行結果大小有限，JSON 有 256 KiB 上限。

## 手動驗收（預設核心）

Mac 開發分支提交後只需執行：

```sh
sh tests/test-d02.sh
```

此入口會在暫存 HOME 上用正式 CLI → Runner → Worker → B09 Report Writer 執行一次本機盤點，並執行不發包的解析 fixture／守衛測試。退出 0 才是 D02 完成的必要條件；Linux 不必測 D02（Linux 上 C Worker 應退出 4）。

此次修改同時更新 C07 worker roster（兩個已實作、七個佔位），以及 B03/B05/B06/B09 歷史測試的隔離樣本，以防止它們因新 Worker 錯誤地執行真實盤點。**本次不重啟 GitHub CI**；歷史測試仍保留供手動執行。
