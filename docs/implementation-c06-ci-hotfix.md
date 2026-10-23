# C06 GitHub Actions 首輪失敗修復

上游 CI： https://github.com/xlldll/NetworkLab/actions/runs/39934068698

## 已確認的故障

- Ubuntu 24.04 原生 Job 的 `test-b03-b04.py` 固定比對 `0.1.0`，但正式 `main` 使用 `0.1.1`，造成兩個版本檢查失敗。
- macOS 15 原生 Job 內，CLI 單元測試有 27 個執行結果異常；失敗集中在沒有參數旗標的命令。`lib/cli.sh` 曾在 `set -u` 下無條件展開空陣列 `"${option_tokens[@]}"`。Bash 3.2 對這個情形的行為與新版 Bash 不一致。修正為只有陣列非空才展開。
- Debian 12／Alpine 3.21 的 GitHub CI Job 在首輪已成功；不修改這些容器的工作流程。
- 額外的版本回歸問題：B13 模擬 Release 測試原先以固定 `v0.1.0` 字串修改原始碼。當安裝來源更新為 `v0.1.1` 時，測試沒有真正執行版本切換而可能錯誤通過，已改為以正規表示式讀寫模擬版本並強制 `v0.1.0 -> v0.1.1` 升級。

## 修補檔案

- `lib/cli.sh`：避免 Bash 3.2 展開空旗標陣列；`--help` 的版本顯示改讀 `NETLAB_VERSION`。
- `tests/test-b03-b04.py`：版本測試從 `lib/common.sh` 讀取預期版本。
- `tests/test-b13.py`：固定測試基線的已安裝版本為 `v0.1.0`，模擬 Release ZIP 的版本宣告一律明確重寫，排除 `.git`。
- `install.sh`／`lib/installer.py`：移除錯誤固定在 `v0.1.0` 的提示文字，不改變安裝流程。

## 合併與驗證

從專案根目錄合併增量檔後執行：

```sh
unzip -o NetworkLab-C06-CI-hotfix.zip -d .
bash tests/test-b11-all.sh
python3 -B tests/test-b13.py
sh tests/test-c04-all.sh
sh tests/test-c05-all.sh
sh tests/test-c06-all.sh
```

預期每項返回 0。以上仍屬本地測試；**macOS Bash 3.2 的最終修復效果，需要將 Commit 推送後，以 GitHub Actions 原生 macOS Runner 的新一輪結果確認**。

建議先 Commit 到 `main`，不要移動現有 `v0.1.1` Tag。CI 綠燈後再依照版本管理流程發布新的修補版本（例如 `v0.1.2`）。

## 本地已執行

- B01–B11：全部通過。
- B13：19／19 通過，成功驗證真實模擬版本切換和回滾。
- C04：104／104 通過。
- C05：21／21 通過。
- C06：29／29 通過（安裝 PyYAML 的環境）。
- B12：三個關聯案例單獨通過；完整 B12 回歸因本地執行環境超時而未完成，不計為通過。
