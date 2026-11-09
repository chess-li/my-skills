#!/usr/bin/env bash
# prototype-anchor 生命周期：start|stop|status（幂等；人手与 skill 共用一个脚本）
# 手动用法：bash ~/.agents/skills/prototype/scripts/anchor-serve.sh start
set -euo pipefail

PORT="${AM_PORT:-8420}"
BASE="http://127.0.0.1:$PORT"

case "${1:-}" in
  start)
    if curl -s -m 2 "$BASE/__am_ping" >/dev/null 2>&1; then
      echo "已在运行（${BASE}）"
      exit 0
    fi
    command -v prototype-anchor >/dev/null 2>&1 || {
      echo "prototype-anchor 未安装，先执行：npm link <skill目录>/scripts/prototype-anchor" >&2
      exit 1
    }
    nohup prototype-anchor serve "$PORT" >/tmp/prototype-anchor.log 2>&1 &
    sleep 1
    if curl -s -m 2 "$BASE/__am_ping" >/dev/null 2>&1; then
      echo "已启动（${BASE}，空闲约 2 分钟自动退出）"
    else
      echo "启动失败，见 /tmp/prototype-anchor.log" >&2
      exit 1
    fi
    ;;
  stop)
    if out=$(curl -s -m 2 -X POST "$BASE/__am_shutdown" 2>/dev/null) && echo "$out" | grep -q '"ok":true'; then
      echo "已停止"
    elif curl -s -m 2 "$BASE/__am_ping" >/dev/null 2>&1; then
      echo "端口 $PORT 上的服务不是 prototype-anchor，未动" >&2
      exit 1
    else
      echo "未在运行"
    fi
    ;;
  status)
    if out=$(curl -s -m 2 "$BASE/__am_ping" 2>/dev/null); then
      echo "$out"
    else
      echo "未在运行"
    fi
    ;;
  *)
    echo "用法：anchor-serve.sh start|stop|status（AM_PORT 改端口，默认 8420）" >&2
    exit 1
    ;;
esac
