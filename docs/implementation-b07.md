# NetworkLab B07：Client 配置管理實作

- 版本：v0.1.0 Skeleton / B07
- 範圍：C 端 `targets` 及 `config` 命令；只處理設定檔，不執行測速、不連線 VPS
- 前置：B01–B06 + A05 範本 `~/.networklab/config/c.conf` 和 `targets.conf`
- 相容：Bash 3.2 介面語法；Python 3（stdlib：`configparser`、`ipaddress`、`fcntl` 等）

## 增量檔案

| 相對路徑 | 用途 |
|---|---|
| `lib/config_manager.py` | 新增，C 端配置讀取、驗證、列印、原子新增及編輯 |
| `lib/runner.sh` | 更新，將 `c:targets`／`c:config` 派發至獨立配置管理器 |
| `lib/menu.sh` | 更新，移除已實作項目的 B07 待實作提示 |
| `tests/test-b07.py` | 新增，隔離式配置管理測試 |
| `tests/test-b07-all.sh` | 新增，運行 B01–B07 全部測試 |
| `docs/implementation-b07.md` | 本文件 |

**重要**：增量 ZIP 不包含也不改寫使用者的 `~/.networklab/config/`、歷史報告、任何 VPS 私密設定。合併之前請自行檢查 `lib/runner.sh` 與 `lib/menu.sh` 是否有你的個人修改。

## CLI 範例

```bash
netlab-c targets list
netlab-c targets show nat-us
netlab-c targets validate
netlab-c config validate
netlab-c targets add --name '美西 NAT' --id nat-us --type nat \
  --ipv4 198.51.100.12 --iperf-port 48801 --mtr-port 443 --non-interactive
netlab-c targets add              # 真正終端內逐項詢問
netlab-c targets edit --editor nano
netlab-c config edit --editor vim
netlab-c targets add --name Demo --id demo --type direct \
  --ipv6 2001:db8::10 --iperf-port 5202 --mtr-port 443 \
  --non-interactive --dry-run
```

說明：上述 IP 是文件示例，**不是**要用於真實測量的公開目標。`--dry-run` 只驗證並預覽，不寫配置，不建立鎖檔。

## 確定行為

- 格式：8 欄 `display_name|target_id|nat/direct|ipv4|ipv6|iperf3外部TCP埠|TCP MTR埠|ssh_alias`。
- 空行、開頭 `#` 註解保留；不接受七欄或九欄。
- `target_id` 唯一；IPv4／IPv6 至少一個；埠範圍 1–65535；SSH alias 可空白。
- 非全球可路由 IP 只警告，不在配置層直接拒絕；真正的聯網能力另測。
- 驗證會指出錯誤的行數，並報告多處問題。
- 所有讀寫為 UTF-8 資料處理；不 `source`、不 `eval` 使用者設定。
- `targets add` 同步鎖定，重新讀取原配置後再新增，防止重複 ID；成功後以相同目錄中的暫存檔原子替換。
- `targets edit` 與 `config edit` 只打開候選副本；編輯完成且驗證通過後，才覆寫正式檔案。
- 原檔會建立隱藏的 UTC 時戳 `.backup-*` 備份，保留完整原始 bytes；正式檔案預設 0600。
- 若檔案是 symlink，拒絕讀取／寫入（`SAFETY_BLOCKED 9`）。
- 若終端不存在，`edit` 回傳 `USAGE_ERROR 2`；`--dry-run` 可在非互動環境預覽。
- 本版**不增加** `targets remove`、`targets rename` 命令。需要刪除 VPS 時，在 `targets edit` 中移除一行並存檔（依 A03 契約）。
- B07 不寫測量結果、manifest 或 summary；正式報告保存留待 B09。

## 退出碼

| 代碼 | 意義 |
|---|---|
| `0` | 成功、驗證通過或 Dry Run 通過 |
| `2` | 指令用法錯誤／非 TTY 編輯 |
| `3` | 配置格式無效、IP/埠錯誤、ID 重複、目標不存在 |
| `4` | 編輯器或 Python3 缺失 |
| `5` | 寫入或編輯器執行失敗 |
| `9` | 安全邊界拒絕（例如 symlink） |
| `130` | Ctrl+C 中斷 |

## 驗收

```bash
bash tests/test-b07-all.sh
netlab-c targets validate
netlab-c targets list
netlab-c config validate
```

本地 Linux/Python 測試結果：B01/B02 = 123、B03/B04 = 34、B05 = 9、B06 = 10、B07 = 12，合計 188 項通過。仍未在 macOS Bash 3.2 與 Alpine 系統實機驗收；測試中的 TTY 編輯器是隔離的模擬 `nano`，不是人工操作體驗測試。

## 繼續開發

- B08：S 端配置解析、Profile / Tool / Schedule 驗證、編輯及查詢。
- B09：統一報告寫入器與 JSON Schema；不要讓 B07 配置操作產生測速報告。
