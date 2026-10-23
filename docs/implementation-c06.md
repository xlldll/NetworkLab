# C06：GitHub Actions 持續整合與離線安全測試

## 定位

此階段只新增 GitHub Actions 工作流程、Docker 測試環境及 CI 結構驗證。**不修改 B01–B13 核心，不推送新版 Tag，不部署 VPS、不更新 Release、不執行實際網路探測。** 適用 GitHub `xlldll/NetworkLab` 的 `main` 分支。

## 新增檔案

- `.github/workflows/ci.yml`：Push／PR／手動觸發，預設最小 `contents: read`，取消過時重複執行。
- `tests/ci/Dockerfile.debian12`：Debian 12 測試映像。
- `tests/ci/Dockerfile.alpine321`：Alpine 3.21 + BusyBox + OpenRC 測試映像。
- `tests/ci/run-offline.sh`：在網路停用的 Linux 容器內運行 C02/C03/C04/C05。
- `tests/test-c06-ci.py`、`tests/test-c06-all.sh`：離線 CI 靜態契約檢查，含安全策略負面案例。

## CI 工作矩陣

| Job | 環境 | 測試 |
|---|---|---|
| native | ubuntu-24.04，Python 3.11 | C06 靜態檢查；B01–B11 累積回歸；獨立 B12/B13；C02/C04/C05 |
| native | macos-15，Python 3.11 | C06 靜態檢查；B01–B11 累積回歸；獨立 B12/B13；C01/C04/C05 |
| distributions | Docker Debian 12 | C02、C04、C05 |
| distributions | Docker Alpine 3.21 | C03、C04、C05 |

Linux 發行版容器以 `--network none --cap-drop ALL --security-opt no-new-privileges` 執行測試，Git Checkout 掛載為唯讀。建立容器映像需要聯網下載依賴，**但測試執行階段不允許容器對外連線**。macOS／Ubuntu 原生工作則採用本身不會發起實際網路探測的測試案例，不能宣稱其整個 Runner 被防火牆隔離。

首次使用可在 Mac Repository 根目錄執行：

```sh
unzip -o NetworkLab-C06-incremental.zip -d .
sh tests/test-c06-all.sh

git add .github/workflows/ci.yml tests/ci tests/test-c06-ci.py tests/test-c06-all.sh docs/implementation-c06.md
git commit -m "Add C06 GitHub Actions offline CI"
git push origin main
```

於 GitHub → Actions → **NetworkLab CI** 檢查四個矩陣執行結果。第一次遠端 CI 綠燈後，再考慮設定 `main` Branch protection / Ruleset，要求 `native` 和 `distributions` 必須通過；不要在尚未確認實際 Check Run 名稱前自行猜測必需檢查名稱。

## 安全與已知限制

1. 不能把 C06 的本地靜態測試等同 GitHub 託管的真實執行。Docker build、macOS Runner 和 GitHub workflow YAML 語義只有 Push 後才能完成最後驗收。
2. `actions/checkout@v4` 和 `actions/setup-python@v5` 是官方版本 Tag，尚未釘選到不可變 Commit SHA；正式發佈前可進一步釘選 SHA 以加強供應鏈安全。
3. `debian:12-slim`、`alpine:3.21` 是發行版 Tag，不是不可變 Digest；CI 重現性受上游套件倉庫更新影響。
4. JSON Schema 測試使用 test-only `jsonschema`，CI YAML 檢查使用 test-only `PyYAML`；核心執行仍依賴標準 Python 套件。
5. Docker 上 Alpine 的 OpenRC 工具檢測不等同實際 PID 1 為 OpenRC；你已提供 Alpine VPS 實機 OpenRC 驗收，兩種證據應分開。
6. GitHub 託管 Runner 與 Docker build 需要網路；禁網限制只適用 Docker 測試容器及測試程式本身的預期行為。
7. 本 Workflow 不發布 Release、不上傳日誌 Artifact，也不使用 GitHub Secrets。

## 完成標準

- `sh tests/test-c06-all.sh` 在本地成功。
- Push 到 main 後，GitHub Actions 四個矩陣 Job 全綠。
- CI 運行中無主機真實測速、無使用者配置被改寫、無自動更新或部署。
- 更新或重新執行時不覆蓋已發布的 `v0.1.1` Tag／Release。
