#!/usr/bin/env bash
# B03/B04: terminal-only front end for A03 CLI. Bash >=3.2.
# Must be sourced after common.sh and cli.sh. Does NOT run any network tools.

NETLAB_MENU_EOF=0
NETLAB_MENU_REPLY=''
NETLAB_MENU_PROFILE=''
NETLAB_MENU_SELECTED_ID=''
NETLAB_MENU_MODULES=''
NETLAB_MENU_HEAVY=0
NETLAB_MENU_TARGET_ROWS=()
NETLAB_MENU_TARGET_IDS=()

netlab_menu_header() {
  printf '\nNetworkLab %s  v%s | %s\n' "$1" "$NETLAB_VERSION" "$2"
  printf '%s\n' '----------------------------------------'
}

netlab_menu_prompt() {
  local prompt="$1"
  NETLAB_MENU_REPLY=''
  printf '%s' "$prompt"
  if ! IFS= read -r NETLAB_MENU_REPLY; then
    NETLAB_MENU_EOF=1
    printf '\n'
    return 1
  fi
  NETLAB_MENU_REPLY="${NETLAB_MENU_REPLY#"${NETLAB_MENU_REPLY%%[![:space:]]*}"}"
  NETLAB_MENU_REPLY="${NETLAB_MENU_REPLY%"${NETLAB_MENU_REPLY##*[![:space:]]}"}"
  return 0
}

netlab_menu_invalid() { printf '[NetworkLab] 無效輸入，請重新選擇。\n' >&2; }

netlab_menu_invoke() {
  local role="$1" code=0
  shift
  printf '[NetworkLab] CLI: netlab-%s' "$role"
  printf ' %q' "$@"
  printf '\n'
  netlab_entry_dispatch "$role" "$@" || code=$?
  if [ "$code" -ne 0 ]; then
    printf '[NetworkLab] 狀態: %s (exit %s)\n' "$(netlab_status_from_exit_code "$code")" "$code"
  fi
  return 0  # Menu continues even when a called command is not implemented.
}

netlab_menu_confirm() {
  local response
  while :; do
    netlab_menu_prompt '確認繼續？[y/N]: ' || return 1
    response="$NETLAB_MENU_REPLY"
    case "$response" in
      y|Y) return 0 ;;
      ''|n|N|0) return 1 ;;
      *) netlab_menu_invalid ;;
    esac
  done
}

netlab_menu_profile() {
  local role="$1" home fallback val
  home="$(netlab_resolve_home)" || return $?
  if ! netlab_check_command python3; then
    netlab_error 'Python3 required to read default_profile (B07/B08 pending)'
    return "$NETLAB_EXIT_DEPENDENCY"
  fi
  fallback="$(python3 -S "$NETLAB_APP_ROOT/lib/menu_data.py" profile "$role" "$home")" || return "$NETLAB_EXIT_CONFIG"
  while :; do
    netlab_menu_header 'Profile' '選擇測試程度'
    printf '1. Quick     低流量基礎檢查\n2. Standard  常規測試\n3. Deep      深度測試（可能消耗更多資源）\n\n0. 返回\n'
    netlab_menu_prompt "請選擇 [預設 $fallback]: " || return 1
    case "$NETLAB_MENU_REPLY" in
      '') NETLAB_MENU_PROFILE="$fallback"; return 0 ;;
      1) NETLAB_MENU_PROFILE=quick; return 0 ;;
      2) NETLAB_MENU_PROFILE=standard; return 0 ;;
      3) NETLAB_MENU_PROFILE=deep; return 0 ;;
      0) return 1 ;;
      *) netlab_menu_invalid ;;
    esac
  done
}

netlab_menu_load_targets() {
  local home out line identity name kind family rest
  NETLAB_MENU_TARGET_ROWS=()
  NETLAB_MENU_TARGET_IDS=()
  home="$(netlab_resolve_home)" || return $?
  if ! netlab_check_command python3; then
    netlab_error 'Python3 required for validated VPS list preview'
    return "$NETLAB_EXIT_DEPENDENCY"
  fi
  out="$(python3 -S "$NETLAB_APP_ROOT/lib/menu_data.py" targets c "$home")" || return "$NETLAB_EXIT_CONFIG"
  [ -n "$out" ] || return 0
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    identity="${line%%|*}"
    netlab_cli_valid_id "$identity" || return "$NETLAB_EXIT_CONFIG"
    NETLAB_MENU_TARGET_IDS+=("$identity")
    NETLAB_MENU_TARGET_ROWS+=("$line")
  done <<< "$out"
  return 0
}

netlab_menu_show_target_details() {
  local line="$1" id name kind family v4 v6 iperf mtr alias
  IFS='|' read -r id name kind family v4 v6 iperf mtr alias <<< "$line"
  printf '\n名稱：%s\nTarget ID：%s\n類型：%s\nIPv4：%s\nIPv6：%s\niperf3 外部 TCP 埠：%s\nTCP MTR 埠：%s\nSSH Alias：%s\n' \
    "$name" "$id" "$kind" "${v4:-(未配置)}" "${v6:-(未配置)}" "$iperf" "$mtr" "${alias:-(未配置)}"
}

netlab_menu_target() {
  local n choice index line id name kind family v4 v6 iperf mtr alias
  while :; do
    netlab_menu_load_targets || return $?
    n=${#NETLAB_MENU_TARGET_IDS[@]}
    netlab_menu_header 'Client' '選擇 VPS（僅單選）'
    if [ "$n" -eq 0 ]; then printf '%s\n' '目前沒有已配置的 VPS。'; fi
    for ((index=0; index<n; index++)); do
      line="${NETLAB_MENU_TARGET_ROWS[$index]}"
      IFS='|' read -r id name kind family v4 v6 iperf mtr alias <<< "$line"
      printf '%s. %s  [%s]  %s  %s\n' "$((index+1))" "$name" "$id" "$kind" "$family"
    done
    printf '\n%s. 新增 VPS\n' "$((n+1))"
    printf '%s. 使用 nano 編輯\n' "$((n+2))"
    printf '%s. 使用 vim 編輯\n' "$((n+3))"
    printf '%s. 臨時 VPS（未實作）\n0. 返回\n' "$((n+4))"
    if [ "$n" -gt 0 ]; then
      netlab_menu_prompt '請選擇 [預設 1]: ' || return 1
    else
      netlab_menu_prompt '請選擇 [沒有預設]: ' || return 1
    fi
    choice="$NETLAB_MENU_REPLY"
    [ -n "$choice" ] || { [ "$n" -gt 0 ] && choice=1; }
    case "$choice" in
      0) return 1 ;;
      ''|*[!0-9]*) netlab_menu_invalid; continue ;;
    esac
    if [ "${#choice}" -gt 6 ]; then netlab_menu_invalid; continue; fi
    choice=$((10#$choice))
    if [ "$choice" -ge 1 ] && [ "$choice" -le "$n" ]; then
      NETLAB_MENU_SELECTED_ID="${NETLAB_MENU_TARGET_IDS[$((choice-1))]}"
      netlab_menu_show_target_details "${NETLAB_MENU_TARGET_ROWS[$((choice-1))]}"
      return 0
    fi
    case "$choice" in
      "$((n+1))") netlab_menu_invoke c targets add ;;
      "$((n+2))") netlab_menu_invoke c targets edit --editor nano ;;
      "$((n+3))") netlab_menu_invoke c targets edit --editor vim ;;
      "$((n+4))") printf '[NetworkLab] 臨時 VPS: NOT_IMPLEMENTED (8)\n' ;;
      *) netlab_menu_invalid ;;
    esac
    [ "$NETLAB_MENU_EOF" -eq 0 ] || return 1
  done
}

# Strict 1,3,5 / 2-6 / all parser for the S tool selector.
netlab_menu_parse_modules() {
  local input="$1" item first last idx selected='' ids=''
  local -a chosen=()
  local -a tools=(netquality tcpquality hardwarequality ipquality nexttrace mtr flent)
  NETLAB_MENU_MODULES=''
  NETLAB_MENU_HEAVY=0
  input="${input//[[:space:]]/}"
  if [ -z "$input" ] || [ "$input" = all ]; then
    NETLAB_MENU_MODULES=all
    return 0
  fi
  [[ "$input" =~ ^[0-9,-]+$ ]] || return 1
  case "$input" in ,*|*,|*,,*) return 1 ;; esac
  IFS=',' read -r -a chosen <<< "$input"
  [ "${#chosen[@]}" -gt 0 ] || return 1
  for item in "${chosen[@]}"; do
    [[ "$item" =~ ^[0-9]+(-[0-9]+)?$ ]] || return 1
    if [[ "$item" == *-* ]]; then
      first="${item%%-*}"; last="${item#*-}"
    else
      first="$item"; last="$item"
    fi
    [ "${#first}" -le 2 ] && [ "${#last}" -le 2 ] || return 1
    first=$((10#$first)); last=$((10#$last))
    [ "$first" -ge 1 ] && [ "$last" -le 7 ] && [ "$first" -le "$last" ] || return 1
    for ((idx=first; idx<=last; idx++)); do
      case ",$selected," in *",$idx,"*) ;; *) selected="${selected:+$selected,}$idx" ;; esac
    done
  done
  [ -n "$selected" ] || return 1
  for ((idx=1; idx<=7; idx++)); do
    case ",$selected," in
      *",$idx,"*)
        ids="${ids:+$ids,}${tools[$((idx-1))]}"
        if [ "$idx" -eq 3 ] || [ "$idx" -eq 7 ]; then NETLAB_MENU_HEAVY=1; fi
        ;;
    esac
  done
  NETLAB_MENU_MODULES="$ids"
  return 0
}

netlab_menu_toolbox() {
  while :; do
    netlab_menu_header Server '公開網路測試工具（v0.1.0 均未整合）'
    printf '%s\n' '1. NetQuality        網路互聯與回程' '2. TcpQuality        TCP 品質與單流' '3. HardwareQuality   硬體跑分（可能高負載）' '4. IPQuality         IP 身分' '5. NextTrace         路由追蹤' '6. MTR               路由品質' '7. Flent             負載延遲（可能高負載）' '' '0. 返回'
    netlab_menu_prompt '編號、1,3,5、2-6、all [預設 all（安全常規項）]: ' || return 0
    [ "$NETLAB_MENU_REPLY" != 0 ] || return 0
    if ! netlab_menu_parse_modules "$NETLAB_MENU_REPLY"; then
      netlab_menu_invalid; continue
    fi
    netlab_menu_profile s || return 0
    printf '\n模組：%s\nProfile：%s\n' "$NETLAB_MENU_MODULES" "$NETLAB_MENU_PROFILE"
    printf '外部執行參數／耗時／流量估算：未知（工具尚未整合）\n'
    if [ "$NETLAB_MENU_HEAVY" -eq 1 ] || [ "$NETLAB_MENU_PROFILE" = deep ]; then
      printf '警告：所選項目將來可能包含高負載或高流量測試；本版本不會執行。\n'
    fi
    if netlab_menu_confirm; then
      netlab_menu_invoke s toolbox --modules "$NETLAB_MENU_MODULES" --profile "$NETLAB_MENU_PROFILE"
    fi
    return 0
  done
}

netlab_menu_simple_submenu() {
  local role="$1" label="$2" choice
  shift 2
  while :; do
    netlab_menu_header "$([ "$role" = c ] && printf Client || printf Server)" "$label"
    case "$label" in
      targets)
        printf '1. 列出 VPS 清單\n2. 查看指定 VPS 配置\n3. 互動新增 VPS\n4. 使用 nano 編輯清單\n5. 使用 vim 編輯清單\n6. 驗證 VPS 清單\n' ;;
      results)
        printf '1. 列出測試結果\n2. 查看指定 Run ID 的摘要\n3. 列出執行日誌\n' ;;
      c-maintenance)
        printf '1. 用 nano 編輯 C 端設定\n2. 用 vim 編輯 C 端設定\n3. 驗證 C 端設定\n4. 系統診斷（doctor）\n5. 骨架自檢（self-test）\n6. 檢查更新\n7. 升級指定版本\n' ;;
      s-service)
        printf '1. 查看測試服務狀態\n2. 啟動測試服務\n3. 停止 NetworkLab 管理的測試服務\n' ;;
      s-schedule)
        printf '1. 列出定時任務\n2. 新增定時任務\n3. 修改定時任務\n4. 啟用定時任務\n5. 停用定時任務\n6. 執行指定任務\n7. 查看排程執行日誌\n' ;;
      s-config)
        printf '1. 查看 Quick／Standard／Deep 設定\n2. 用 nano 編輯 S 端設定\n3. 用 vim 編輯 S 端設定\n4. 驗證 S 端設定\n' ;;
      s-maintenance)
        printf '1. 系統診斷（doctor）\n2. 骨架自檢（self-test）\n3. 檢查更新\n4. 升級指定版本\n' ;;
    esac
    printf '\n0. 返回主選單\n'
    netlab_menu_prompt '請選擇: ' || return 0
    choice="$NETLAB_MENU_REPLY"
    [ "$choice" != 0 ] || return 0
    [ -n "$choice" ] || continue
    case "$label:$choice" in
      targets:1) netlab_menu_invoke c targets list ;;
      targets:2)
        if netlab_menu_target; then netlab_menu_invoke c targets show "$NETLAB_MENU_SELECTED_ID"; fi ;;
      targets:3) netlab_menu_invoke c targets add ;;
      targets:4) netlab_menu_invoke c targets edit --editor nano ;;
      targets:5) netlab_menu_invoke c targets edit --editor vim ;;
      targets:6) netlab_menu_invoke c targets validate ;;
      results:1) netlab_menu_invoke "$role" results list ;;
      results:2)
        if netlab_menu_prompt 'Run ID（0 返回）: '; then
          case "$NETLAB_MENU_REPLY" in ''|0) ;; *) netlab_menu_invoke "$role" results show "$NETLAB_MENU_REPLY" ;; esac
        fi ;;
      results:3) netlab_menu_invoke "$role" logs list ;;
      c-maintenance:1) netlab_menu_invoke c config edit --editor nano ;;
      c-maintenance:2) netlab_menu_invoke c config edit --editor vim ;;
      c-maintenance:3) netlab_menu_invoke c config validate ;;
      c-maintenance:4) netlab_menu_invoke c doctor ;;
      c-maintenance:5) netlab_menu_invoke c self-test ;;
      c-maintenance:6) netlab_menu_invoke c update check ;;
      c-maintenance:7|s-maintenance:4)
        if netlab_menu_prompt '指定版本（如 v0.1.1；0 返回）: '; then
          case "$NETLAB_MENU_REPLY" in ''|0) ;; *)
            local requested_version="$NETLAB_MENU_REPLY"
            printf '準備更新為 %s，將從配置的可信 GitHub Release 取得版本並驗證 SHA-256。\n' "$requested_version"
            if netlab_menu_confirm; then netlab_menu_invoke "$role" update apply --version "$requested_version"; fi ;;
          esac
        fi ;;
      s-service:1) netlab_menu_invoke s service status ;;
      s-service:2|s-service:3)
        printf '此操作未來可能改變公網服務狀態，目前不會執行。\n'
        if netlab_menu_confirm; then
          if [ "$choice" = 2 ]; then netlab_menu_invoke s service start; else netlab_menu_invoke s service stop; fi
        fi ;;
      s-schedule:1) netlab_menu_invoke s schedule list ;;
      s-schedule:2) netlab_menu_invoke s schedule add ;;
      s-schedule:3|s-schedule:4|s-schedule:5|s-schedule:6)
        if netlab_menu_prompt 'Job ID（0 返回）: '; then
          case "$NETLAB_MENU_REPLY" in ''|0) ;; *)
            local job="$NETLAB_MENU_REPLY" action=''
            case "$choice" in 3) action=edit ;; 4) action=enable ;; 5) action=disable ;; 6) action=run ;; esac
            if [ "$choice" = 4 ] || [ "$choice" = 5 ]; then
              printf '排程狀態變更需要確認（目前不會真正修改）。\n'
              if ! netlab_menu_confirm; then continue; fi
            fi
            if [ "$choice" = 6 ]; then netlab_menu_invoke s schedule "$action" "$job" --non-interactive
            else netlab_menu_invoke s schedule "$action" "$job"; fi ;;
          esac
        fi ;;
      s-schedule:7) netlab_menu_invoke s schedule logs ;;
      s-config:1) netlab_menu_invoke s config profiles ;;
      s-config:2) netlab_menu_invoke s config edit --editor nano ;;
      s-config:3) netlab_menu_invoke s config edit --editor vim ;;
      s-config:4) netlab_menu_invoke s config validate ;;
      s-maintenance:1) netlab_menu_invoke s doctor ;;
      s-maintenance:2) netlab_menu_invoke s self-test ;;
      s-maintenance:3) netlab_menu_invoke s update check ;;
      *) netlab_menu_invalid ;;
    esac
    [ "$NETLAB_MENU_EOF" -eq 0 ] || return 0
  done
}

netlab_menu_main() {
  local role="$1" choice
  [ -t 0 ] || { netlab_cli_error 'TTY required for interactive menu'; return 2; }
  NETLAB_MENU_EOF=0
  trap 'exit 130' INT  # B05 will own cancellation during real execution.
  while :; do
    if [ "$role" = c ]; then
      netlab_menu_header Client '主選單'
      printf '1. 本機設備與網路環境盤點\n2. 公共網路獨立測試\n3. Mac ↔ VPS 聯動測試\n4. Bettbox 代理與應用測試\n5. 從 VPS 下載測試結果\n6. 管理 VPS 配置\n7. 查看測試結果與執行日誌\n8. 系統設定、診斷與更新\n\n0. 退出\n'
      netlab_menu_prompt '請選擇 [0-8]: ' || return 0
      choice="$NETLAB_MENU_REPLY"
      case "$choice" in
        0) return 0 ;;
        '') continue ;;
        1) netlab_menu_invoke c inventory ;;
        2|4)
          if netlab_menu_profile c; then
            if [ "$choice" = 2 ]; then netlab_menu_invoke c standalone --profile "$NETLAB_MENU_PROFILE"
            else netlab_menu_invoke c proxy --profile "$NETLAB_MENU_PROFILE"; fi
          fi ;;
        3|5)
          if netlab_menu_target; then
            if [ "$choice" = 3 ]; then
              if netlab_menu_profile c; then netlab_menu_invoke c paired --target "$NETLAB_MENU_SELECTED_ID" --profile "$NETLAB_MENU_PROFILE"; fi
            else netlab_menu_invoke c collect --target "$NETLAB_MENU_SELECTED_ID"; fi
          fi ;;
        6) netlab_menu_simple_submenu c targets ;;
        7) netlab_menu_simple_submenu c results ;;
        8) netlab_menu_simple_submenu c c-maintenance ;;
        *) netlab_menu_invalid ;;
      esac
    else
      netlab_menu_header Server '主選單'
      printf '1. VPS 設備與系統盤點\n2. 公開網路測試工具\n3. 管理聯動測試服務\n4. 定時任務與靜默採集\n5. 管理測試參數與 Profile\n6. 查看測試結果與執行日誌\n7. 系統診斷與更新\n\n0. 退出\n'
      netlab_menu_prompt '請選擇 [0-7]: ' || return 0
      choice="$NETLAB_MENU_REPLY"
      case "$choice" in
        0) return 0 ;;
        '') continue ;;
        1) netlab_menu_invoke s inventory ;;
        2) netlab_menu_toolbox ;;
        3) netlab_menu_simple_submenu s s-service ;;
        4) netlab_menu_simple_submenu s s-schedule ;;
        5) netlab_menu_simple_submenu s s-config ;;
        6) netlab_menu_simple_submenu s results ;;
        7) netlab_menu_simple_submenu s s-maintenance ;;
        *) netlab_menu_invalid ;;
      esac
    fi
    [ "$NETLAB_MENU_EOF" -eq 0 ] || return 0
  done
}
