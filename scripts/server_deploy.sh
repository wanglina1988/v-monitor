#!/usr/bin/env bash
# ============================================================
# 雪球速览 · Linux 服务器一键部署（腾讯云/阿里云轻量等，Ubuntu/Debian）
# 在服务器上执行：bash server_deploy.sh
# 说明：本脚本装环境 + 拉代码 + 建每小时定时任务；登录一步需要你手动完成（见步骤 4）。
# ============================================================
set -euo pipefail

REPO_URL="https://github.com/wanglina1988/v-monitor.git"
APP_DIR="$HOME/v-monitor"
PY=python3

echo "==> [1/5] 安装系统依赖"
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git curl unzip || true

echo "==> [2/5] 安装 Playwright + Chromium"
$PY -m pip install --user playwright || $PY -m pip install playwright
$PY -m playwright install chromium --with-deps || true

echo "==> [3/5] 拉取项目"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --rebase || true
else
  git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> [4/5] 配置 PUSHPLUS_TOKEN"
if [ ! -f "$APP_DIR/.env.local" ]; then
  echo -n "请输入你的 PushPlus token（pushplus.plus 首页）："
  read -r TOKEN
  echo "PUSHPLUS_TOKEN=$TOKEN" > "$APP_DIR/.env.local"
else
  echo "已存在 .env.local，跳过"
fi

echo "==> [5/5] 建每小时定时任务（cron）"
CRON_LINE="0 * * * * cd $APP_DIR && $PY scripts/xueqiu_digest_standalone.py >> $APP_DIR/data/digest_cron.log 2>&1"
( crontab -l 2>/dev/null | grep -v "xueqiu_digest_standalone" ; echo "$CRON_LINE" ) | crontab -
echo "定时任务已添加：每小时整点运行"

echo ""
echo "============================================================"
echo "还剩最后一步【登录】："
echo "在服务器上运行：  cd $APP_DIR && python3 scripts/xueqiu_login_setup.py"
echo "服务器没有桌面时，可用 Xvfb + 截图扫码："
echo "  1) sudo apt-get install -y xvfb"
echo "  2) xvfb-run -a python3 scripts/xueqiu_login_setup.py"
echo "登录成功后再跑一次：  python3 scripts/xueqiu_digest_standalone.py --no-push  验证"
echo "============================================================"
