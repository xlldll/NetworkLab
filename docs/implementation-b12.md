# NetworkLab B12：跨平台首次安裝器

- **交付版本**：B12 / v0.1.0 Skeleton
- **程式**：`install.sh`（POSIX sh）、`lib/installer.py`（Python 3.8+ 標準函式庫）
- **測試**：`tests/test-b12.py`、`tests/test-b12-all.sh`
- **安裝來源**：使用者已下載／已 clone 的本地 Repository。**不**自動下載 GitHub `main`、第三方測速工具或套件。

## 1. 目的和邊界

由 macOS 的 C 端與 Linux 的 S 端共用單一安裝器。自動識別作業系統、CPU 架構，驗證 `bash` 與 `python3`，安裝程式的獨立副本，建立個人配置與命令入口，然後執行離線配置驗證與 Self-test。

預設角色：macOS → `c`；Linux → `s`。可用 `--role c|s` 手動指定，主要供開發與交叉測試；真正受支援的環境仍以 macOS C、Linux S 為準。Ubuntu、Debian、Alpine 會透過 `/etc/os-release` 辨認，Alpine 缺少 Bash 時會回傳 `4` 並顯示 `apk add bash` 的安裝建議。

安裝器**不**執行 `sudo`，也不修改系統套件、Shell 啟動檔、PATH、cron／systemd、網路規則或 VPS 測速程序。缺少 Bash／Python3 時會明確停止，由使用者自行授權安裝依賴。B13 才負責更新和回滾。

## 2. 首次執行

從你現有的 `NetworkLab/` Repository 根目錄執行：

```bash
sh install.sh --dry-run
sh install.sh
```

Mac 首次安裝建立：

```text
~/.networklab/
├── app/                 # 此次本地 Repository 的獨立程式副本
├── config/
│   ├── c.conf
│   └── targets.conf
├── results/
└── logs/
~/.local/bin/netlab-c   # 可執行啟動器
```

Linux VPS 則初始化 `config/s.conf`，產生 `s-` 加 16 位十六進位亂數的 `server_id`，建立 `~/.local/bin/netlab-s`。此識別碼透過 64 位隨機值降低不同機器的碰撞機率，**不**是跨所有設備的數學絕對唯一性保證。

若 `~/.local/bin` 尚未位於 `PATH`，安裝器只印出提示，**不**直接改 `~/.zshrc` 或 `.bashrc`。可立即以完整路徑執行：

```bash
~/.local/bin/netlab-c --version
~/.local/bin/netlab-c self-test
```

或在使用者的 Shell 啟動檔中自行加入（不是安裝器自動執行）：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## 3. 可選參數

```text
sh install.sh [--role auto|c|s] [--bin-dir /absolute/path]
              [--dry-run] [--skip-self-test] [--help]
```

- `--role auto`：自動偵測 C／S（預設）。
- `--bin-dir ABS`：放置啟動器的目錄；不變更系統 PATH。
- `--dry-run`：僅檢查、列出安裝路徑，不建立任何檔案。
- `--skip-self-test`：跳過安裝後的離線 Self-test；配置驗證仍會執行。
- `NETLAB_HOME`：**絕對路徑**的測試或自訂使用者資料根目錄，若設置而未指定 `--bin-dir`，啟動器位於 `$NETLAB_HOME/bin/`。

## 4. 重複安裝和資料保護

- 已存在的 `config/c.conf`、`config/targets.conf`、`config/s.conf` 不改寫，並維持原 `server_id`；故意寫錯的舊配置也不會被偷偷替換。
- `results/` 和 `logs/` 不刪除、不清理、不搬移。
- 已安裝的 `app/` 不會被安裝器覆寫，即使本地 Repository 原始碼比安裝版本更新。**真正升級屬於 B13。**
- 建立檔案使用私有目錄、排它檔案建立或原子改名；採用安裝鎖避免安裝器互相干擾。
- 遇到重名但內容不同的命令入口、危險符號連結、無效配置時，停止並提供退出碼，不假裝成功。
- 本版本使用最小權限執行，不需要 Root。採用 `~/.networklab/app` + `config/results/logs` 分離結構。

## 5. 安裝後驗收

```bash
~/.local/bin/netlab-c config validate
~/.local/bin/netlab-c targets validate
~/.local/bin/netlab-c self-test
```

Linux：

```bash
~/.local/bin/netlab-s config validate
~/.local/bin/netlab-s config profiles
~/.local/bin/netlab-s self-test
```

全部項目都能離線執行。Self-test 使用獨立的合成資料，不接觸真實 VPS，也不產生真正的網路性能報告。

## 6. 安全與限制

- 安裝器讀取的 Repository 應由使用者信任／自行審核，**不提供任意來源程式碼安全擔保**。
- 安裝器不修改使用者已有的配置；如果既有配置不合法，最後的 `config validate` 會失敗，需要使用者自行修復。
- 允許 macOS Root 管理的 `/var`、`/tmp` 符號連結；使用者資料與安裝目錄中的符號連結將被拒絕。
- Python `fcntl`、`os.link`、`os.rename` 及 Bash 是此版本的執行環境要求；Windows 不支援。
- 已在 Linux 環境測試，**macOS、Debian、Ubuntu、Alpine 實機驗收仍需逐一進行**。
- 目前 `netlab-c doctor`、`netlab-s doctor` 的公開入口如果尚未實作，B12 並不假稱已完成 Doctor 診斷命令。

## 7. 測試

```bash
python3 -B tests/test-b12.py
bash tests/test-b12-all.sh
```

新增 18 個 B12 測試，包含：首次安裝、預設角色、私人檔案權限、C／S 共存、隨機 `server_id`、重複安裝保留資料、`--dry-run`、啟動器含特殊字元路徑、符號連結拒絕、命令衝突與真正離線 Self-test。所有測試使用臨時 Home，不連線外部服務。

## 8. 交付與整合

只需把增量包以下四個檔案按相對路徑放回現有 Repo：

```text
install.sh
lib/installer.py
tests/test-b12.py
tests/test-b12-all.sh
docs/implementation-b12.md
```

對你現有 Repository 的 A01、A02、A09 文件、LICENSE、個人配置和測試結果都不作覆蓋。增量包比全量整合包更適合合併使用。
