"""Git 辅助：pull --rebase、提交并推送（带冲突重试）。"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import List, Tuple

BOT_NAME = "v-monitor-bot"
BOT_EMAIL = "v-monitor-bot@users.noreply.github.com"


def git_exe() -> str:
    return os.environ.get("GIT_EXE") or shutil.which("git") or "git"


def run_git(args: List[str], cwd=None, timeout: int = 120):
    return subprocess.run([git_exe(), *args], cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)


class GitHelper:
    @staticmethod
    def is_repo(cwd: str) -> bool:
        return os.path.isdir(os.path.join(cwd, ".git"))

    @staticmethod
    def has_remote(cwd: str) -> bool:
        res = run_git(["remote"], cwd=cwd)
        return bool((res.stdout or "").strip())

    @staticmethod
    def pull_rebase(cwd: str) -> bool:
        if not GitHelper.has_remote(cwd):
            return True
        res = run_git(["pull", "--rebase", "--autostash"], cwd=cwd)
        return res.returncode == 0

    @staticmethod
    def commit_and_push(cwd: str, message: str, paths) -> Tuple[bool, str]:
        if not GitHelper.is_repo(cwd):
            return False, "当前目录不是 git 仓库（本地使用不受影响，可忽略）"
        for attempt in range(2):
            if attempt == 1 and not GitHelper.pull_rebase(cwd):
                return False, "git pull --rebase 失败，可能有冲突，请手动处理"
            run_git(["add", "--"] + list(paths), cwd=cwd)
            status = run_git(["status", "--porcelain", "--"] + list(paths), cwd=cwd)
            if not (status.stdout or "").strip():
                return True, "没有需要提交的变更"
            res = run_git(["-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}",
                           "commit", "-m", message], cwd=cwd)
            if res.returncode != 0:
                combined = (res.stdout or "") + (res.stderr or "")
                if "nothing to commit" in combined:
                    return True, "没有需要提交的变更"
                if "Please tell me who you are" in combined:
                    run_git(["config", "user.name", BOT_NAME], cwd=cwd)
                    run_git(["config", "user.email", BOT_EMAIL], cwd=cwd)
                    res = run_git(["commit", "-m", message], cwd=cwd)
                if res.returncode != 0:
                    return False, f"提交失败: {(res.stderr or '')[:300]}"
            if not GitHelper.has_remote(cwd):
                return True, "已提交（未配置远程仓库，未推送）"
            pres = run_git(["push"], cwd=cwd)
            if pres.returncode == 0:
                return True, "已提交并推送"
            if attempt == 1:
                return False, f"推送失败: {(pres.stderr or '')[:300]}"
        return False, "未知错误"
