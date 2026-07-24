#!/usr/bin/env bash
# merge-dev-to-main.sh
# 将 dev 分支合并到 main，合并时跳过 openspec/ 目录。
#
# 用法：
#   cd E:/projects/personal/CashCode
#   bash scripts/merge-dev-to-main.sh
#
# 原理：
#   1. git merge --no-commit dev   → 合并但不自动提交
#   2. 从暂存区移除 openspec/ 的所有变更（main 不跟踪此目录）
#   3. 恢复 main 的 .gitignore（保留 openspec/ 排除规则）
#   4. 提交合并结果

set -e

MAIN_BRANCH="main"
DEV_BRANCH="dev"
EXCLUDE_DIR="openspec"

# ── 安全检查 ──────────────────────────────────────────────
current=$(git rev-parse --abbrev-ref HEAD)
if [ "$current" != "$MAIN_BRANCH" ]; then
  echo "❌  当前分支是 '$current'，请先切换到 $MAIN_BRANCH：git checkout $MAIN_BRANCH"
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "❌  工作区有未提交的更改，请先 commit 或 stash"
  exit 1
fi

# ── 拉取最新远程 ──────────────────────────────────────────
echo "📥  拉取 origin/$DEV_BRANCH ..."
git fetch origin "$DEV_BRANCH"

# ── 合并（不自动提交）────────────────────────────────────
echo "🔀  合并 $DEV_BRANCH → $MAIN_BRANCH (--no-commit) ..."
git merge --no-commit --no-ff "origin/$DEV_BRANCH" || true

# ── 移除 openspec/ 的暂存变更 ────────────────────────────
if git ls-files --cached "$EXCLUDE_DIR/" | grep -q .; then
  echo "🗑️  从暂存区移除 $EXCLUDE_DIR/ ..."
  git rm -r --cached --quiet "$EXCLUDE_DIR/" 2>/dev/null || true
fi

# 同时删除工作区中被合并带入的 openspec/ 文件（若有）
if [ -d "$EXCLUDE_DIR" ] && git ls-files --others "$EXCLUDE_DIR/" | grep -q .; then
  git clean -fd "$EXCLUDE_DIR/" -q 2>/dev/null || true
fi

# ── 恢复 main 的 .gitignore ───────────────────────────────
echo "📄  恢复 main 的 .gitignore ..."
git checkout HEAD -- .gitignore

# ── 提交合并结果 ──────────────────────────────────────────
DEV_SHA=$(git rev-parse --short "origin/$DEV_BRANCH")
git commit -m "merge: $DEV_BRANCH ($DEV_SHA) into $MAIN_BRANCH (excluding $EXCLUDE_DIR/)"

echo ""
echo "✅  合并完成！$EXCLUDE_DIR/ 未包含在本次合并中。"
echo "    运行 'git push origin $MAIN_BRANCH' 推送到远程。"
