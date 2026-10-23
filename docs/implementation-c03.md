# NetworkLab C03：Alpine／BusyBox／OpenRC 隔離驗收

## 目的與版本範圍

C03 延續 C01（macOS）及 C02（Debian／Ubuntu）的**離線驗收**模式，在真正的 Alpine Linux VPS 上驗證 NetworkLab B12 安裝器與 B13 更新預覽的可攜性。它不是正式測速模組，不會測試 REALITY、Xray、iperf3、路由、回程或埠映射。

**重要：只有 `/etc/os-release` 顯示 `ID=alpine` 才能得到 `[C03] ALPINE PASS`。** 在 Debian 等 Linux 環境使用 `--compat-smoke` 可作 BusyBox ash 相容性預檢，輸出會明確標註 `NOT ALPINE`，不能算 Alpine 實機通過。

針對 OpenRC，測試只核對 `/etc/runlevels`、`/etc/crontabs`、`/etc/periodic` 的檔案資訊在驗收前後保持不變；不會執行 `rc-service start`、`rc-update add`、`crontab` 或更動服務狀態。若系統未安裝 `rc-service`、`rc-update`，會明確顯示 **OpenRC not certified**。即使 OpenRC 工具存在，**服務整合與實際啟動能力仍未驗證**，因為 v0.1.x 尚未實作管理服務的正式模組。

## 在 Alpine VPS 執行

先確認有 `git`、`bash`、`python3`、`busybox`。Alpine 常用準備方式（需管理員權限且只在缺少套件時執行）：

```sh
apk add --no-cache git bash python3
```

Alpine 預設提供 BusyBox。可使用一般使用者進行驗收，不必以 root 執行測試。NetworkLab 源碼與 C03 增量檔案需先提交到 GitHub `main`，**不要假設既有 v0.1.1 Release 會自動包含 C03**。

```sh
git clone https://github.com/xlldll/NetworkLab.git
cd NetworkLab
sh tests/test-c03-all.sh
```

如果已 Clone：

```sh
cd ~/NetworkLab
git pull --ff-only
sh tests/test-c03-all.sh
```

成功標誌（版本數字依實際作業系統而定）：

```
[C03] ALPINE PASS: alpine <version>; isolated BusyBox ash Server acceptance.
```

測試期間使用私有臨時 HOME 及 NETLAB_HOME，並自動清除。**不修改**操作人的 `~/.networklab`、`~/.local/bin`、原有 `s.conf`、網路、正式計量或歷史報告；不下載 Release，不執行真實測速，也不新增服務或排程。若失敗需保留診斷目錄：

```sh
sh tests/test-c03-all.sh --keep
```

測試失敗時，先檢查當下的錯誤及退出碼，不應立即在 NAT VPS 上改動 Xray、sing-box、OpenRC 或防火牆。請使用 `--keep` 顯示的臨時路徑調查。

## 驗收檢查

1. Python3 >=3.8、Bash、POSIX sh、BusyBox 與 ash 可用，並以 `busybox ash -n` 靜態解析安裝入口。
2. 真正以 BusyBox `ash` 執行 `install.sh --dry-run`（不建立檔案）與首次安裝，Linux 自動選擇 S 端。
3. 私有模式安裝 `app/`、`config/s.conf`、`results/`、`logs/`、`netlab-s`；不建立 C 端配置。
4. `server_id` 有效、重複安裝穩定；整個安裝不要求公網 IPv4、獨立網卡、固定 IP 或 NAT DNAT 規則。
5. `--version`、`--help`、`config validate`、`config profiles`、9 項 Self-test 正常。
6. 無效命令退出碼 2；未實作模組退出碼 8，沒有偽造報告。
7. 私有路徑群組／其他使用者不可讀寫；拒絕目錄符號連結，不修改連結目標。
8. 二次安裝保留應用、配置、Server ID、報告與日誌。
9. `update apply --version v0.1.1 --dry-run` 不聯網、不覆蓋資料（非真實跨版本更新）。
10. 系統 OpenRC runlevel／cron／periodic 配置及源碼前後一致。

## 開發環境驗證紀錄

- Debian 13 + BusyBox ash，root：**31 項相容性預檢通過**，僅 `COMPAT-SMOKE`。
- Debian 13 + BusyBox ash，非 root（nobody）：**31 項相容性預檢通過**，僅 `COMPAT-SMOKE`。
- Debian 13 正常執行（沒有 `--compat-smoke`）：預期以退出碼 1 拒絕冒充 Alpine。
- **真正 Alpine / OpenRC VPS：尚未執行**，需要使用者在 VPS 實機驗收。

這些 31 項是腳本內單次 `[PASS]` 的數量，不能合併宣稱 62 項 Alpine 測試已通過，也不是 B01–B13 的全套單元測試數量。

## 相容性與安全邊界

- C03 確認的是 Alpine 上執行安裝器的可行性及零服務副作用，不代表 NAT VPS 公網 IPv4、外部 TCP 埠、DNAT 或回程品質已被驗收。
- 測試不會自動安裝依賴。缺少 `bash` 或 `python3` 必須先按照系統策略準備，`openrc` 是否存在會明確回報。
- `lib/installer.py` 的 B12 結尾仍可能顯示過去硬編碼的 `v0.1.0` 提示；正式版本以 `netlab-s --version` 為準。
- 不要重建、強制移動已發布的 v0.1.1 Tag。C03 是後續工作，應提交到 `main`，待下個版本發布再一併納入。
