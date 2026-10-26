# NetworkLab

**NetworkLab v0.1.1 Skeleton + Phase D01/D02/D03 development** 是一套可在 macOS（Client，C）與 Linux VPS（Server，S）上運作的網路測試系統骨架。目標是將環境盤點、網路測試、跨端測量、報告保存與結果檢查整合在一套可重複使用的命令介面中。

> **功能邊界**：目前版本是 **Skeleton，不是已完成的網路測速工具**。Phase D01/D02/D03 開發樹中，`s-inventory` 已實作 Linux VPS 唯讀系統盤點，`c-inventory` 已實作 macOS 唯讀網路環境盤點，`c-standalone` 已實作指定 IP／Port 的 TCP Connect；其餘六個正式 Worker 仍返回 `NOT_IMPLEMENTED`（退出碼 `8`）。這不代表 v0.1.1 Tag 已改變。`self-test` 使用合成資料驗證 Runner 與報告管線，**不會對外執行真實 TCP MTR、iperf3、網路品質或代理測試**。請勿把它的 PASS 當作線路品質證據。

## 平台與相依性

- C 端：macOS，包含 Apple Silicon；Bash 3.2+、Python 3.8+。
- S 端：Debian／Ubuntu／Alpine；Bash 與 Python 3.8+。Alpine 的 POSIX 安裝入口可由 BusyBox `ash` 執行；**不會自動安裝 OpenRC 服務或啟動排程**。
- 安裝器不需要 `sudo`，不修改系統網路設定，也不自動下載執行遠端腳本。

## 取得與安裝

```sh
git clone https://github.com/xlldll/NetworkLab.git
cd NetworkLab
sh install.sh --dry-run
sh install.sh
```

macOS 預設安裝 C 端，Linux 預設安裝 S 端。程式位於 `~/.networklab/app/`，配置、日誌及結果分開保存。命令入口為 `~/.local/bin/netlab-c` 和 `~/.local/bin/netlab-s`。如未將 `~/.local/bin` 加入 PATH，請使用完整路徑。

安裝與升級是不同操作：重複執行 `sh install.sh` 不會覆寫已有程式、個人配置或歷史結果。

## 可用的骨架功能

### macOS Client

```sh
~/.local/bin/netlab-c --version
~/.local/bin/netlab-c config validate
~/.local/bin/netlab-c targets list
~/.local/bin/netlab-c self-test
~/.local/bin/netlab-c results list
~/.local/bin/netlab-c logs list
```

### Linux VPS Server

```sh
~/.local/bin/netlab-s --version
~/.local/bin/netlab-s config validate
~/.local/bin/netlab-s config profiles
~/.local/bin/netlab-s self-test
~/.local/bin/netlab-s results list
```

已可使用的基礎設施包括：嚴格 CLI、互動入口、C／S 設定驗證、C 端 VPS 目標清單、Runner 與 Worker Context 契約、隔離的合成 Self-test、Manifest／Summary／Raw Data 報告生成、SHA-256 校驗與結果瀏覽，以及固定 GitHub Release 版本的檢查／更新／回滾流程。

**D01/D02/D03 已實作（僅目前開發樹）**：S 端 `inventory` 可唯讀盤點 Linux VPS 系統與 TCP 參數；C 端 `inventory` 可用 macOS 原生命令唯讀盤點介面、路由、DNS、代理與 TUN 跡象。兩者均產生 `synthetic=false` 的本機盤點報告，**不進行外部網路探測**。未知 ISP、公網 IP、實際代理接管狀態不得推論成已知。**D03 已實作**：`standalone --tcp-ip IP --tcp-port PORT --profile quick|standard|deep`，需明確指定數字 IP 與 TCP 埠，只做建連，不發 HTTP/TLS 資料；路徑是否經透明代理/TUN 仍未驗證。**尚未實作**：C 端 `paired`、`proxy`、`collect`；S 端 `toolbox`、`service`、`scheduler`。舊 Tag／Release 均不修改。

## 配置與資料

```text
~/.networklab/
├── app/                    # 已安裝程式
├── config/                 # c.conf / targets.conf / s.conf / update-source.json
├── results/                # 已提交的報告
├── logs/                   # 日誌
└── tmp/                    # 執行中的私有暫存資料
```

更新程序只替換 `app/`；配置與報告必須保留。`results show` 會使用 SHA-256 驗證已建立報告的檔案一致性；這**不是獨立的資料來源簽章**。故障發生在 Manifest 發布前，可能留下不被結果瀏覽器認可的孤兒檔案，尚不支援自動恢復。

## 更新與版本

建立 `~/.networklab/config/update-source.json`：

```json
{"github_repo":"xlldll/NetworkLab"}
```

```sh
~/.local/bin/netlab-c update check
~/.local/bin/netlab-c update apply --version v0.1.1 --dry-run
```

完整更新需要已安裝的 `app/`、公開且非 Draft／Pre-release 的 GitHub Release，以及 `networklab-vX.Y.Z.zip` 與其 `.sha256` 兩份資產。`--dry-run` 不會下載或切換程式。**Git Tag 應視為不可變**；後續修補應建立新版本，而非移動舊 Tag。

## 品質驗收（D01 手動實機為準）

D01 採用 **實機核心測試** 作為驗收依據，不要求 GitHub CI。
三個平台均可執行同一條命令，會自動辨識 macOS／Alpine／Debian，
輸出摘要，保留完整私有日誌供失敗時檢查：

```sh
sh tests/test-d01.sh
```

Linux 會驗證真實的本機 S Inventory 與非合成報告；macOS 只驗證契約，
Linux 專屬整合測試為預期 SKIP。預設不重跑歷史 B/C 系列完整回歸；
僅在共用架構變更後才選擇 `sh tests/test-d01.sh --full`。
舊平台入口 `test-d01-macos.sh`、`test-d01-alpine.sh`、`test-d01-debian.sh`
仍可使用，預設行為與統一入口一致。

GitHub Actions 工作流程目前仍留在儲存庫作為歷史驗證配置。
**停止自動執行需要在 GitHub Actions 介面停用 NetworkLab CI 工作流程**；
單純修改本機驗收腳本不會關閉遠端 CI。

詳細實作、限制與發布門檻請閱讀 `docs/implementation-c07.md`、`docs/commands.md` 和 `docs/architecture.md`。

專案：<https://github.com/xlldll/NetworkLab>
