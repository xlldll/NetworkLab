# NetworkLab

**NetworkLab v0.1.1 Skeleton + Phase D01 development** 是一套可在 macOS（Client，C）與 Linux VPS（Server，S）上運作的網路測試系統骨架。目標是將環境盤點、網路測試、跨端測量、報告保存與結果檢查整合在一套可重複使用的命令介面中。

> **功能邊界**：目前版本是 **Skeleton，不是已完成的網路測速工具**。Phase D01 開發樹中，`s-inventory` 已實作 Linux VPS 唯讀系統盤點；其餘八個正式 Worker 仍返回 `NOT_IMPLEMENTED`（退出碼 `8`）。這不代表 v0.1.1 Tag 已改變。`self-test` 使用合成資料驗證 Runner 與報告管線，**不會對外執行真實 TCP MTR、iperf3、網路品質或代理測試**。請勿把它的 PASS 當作線路品質證據。

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

**D01 已實作（僅目前開發樹）**：S 端 `inventory` 可離線讀取 VPS 的系統、網卡、TCP 核心參數並產生 `synthetic=false` 真實本機盤點報告，不執行主動網路測量。**尚未實作**：C 端五個 Worker；S 端 `toolbox`、`service`、`scheduler`。舊 Tag／Release 均不修改。

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

## 品質驗收

NetworkLab 採用雙層驗收：

1. **GitHub CI**：驗證程式碼、測試契約、模擬故障與相容性，不執行真實 VPS 測速。
2. **Mac／VPS 實機**：驗證安裝、權限、實際系統服務、未來測量 Worker 與真實網路表現。

CI 全綠只能證明程式碼驗收符合當前測試範圍，不代表實際線路品質通過。

```sh
sh tests/test-c06-all.sh
sh tests/test-c07-all.sh
```

詳細實作、限制與發布門檻請閱讀 `docs/implementation-c07.md`、`docs/commands.md` 和 `docs/architecture.md`。

專案：<https://github.com/xlldll/NetworkLab>
