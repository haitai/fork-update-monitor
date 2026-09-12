# GitHub Fork Repos Update Monitor

监视你 fork 的 GitHub 仓库是否有上游更新，通过 GitHub Actions 定时检查并渲染网页到 GitHub Pages。

## 功能

- 🔍 自动检测所有 fork 仓库与上游（parent）的差异
- 📊 清晰的状态分类：Up to date / Behind / Ahead / Diverged
- 🔗 一键跳转 Sync Fork 页面
- 📱 响应式深色主题 UI
- ⏰ 每 6 小时自动更新（支持手动触发）
- 🎯 支持过滤/排除特定仓库

## 工作原理

```
GitHub Actions (cron) → monitor.py → GitHub API → data.json + index.html → GitHub Pages
```

1. `monitor.py` 通过 GitHub API 获取用户所有仓库，过滤出 `fork=True` 的仓库
2. 逐个请求 fork 仓库详情以获取 `parent`（上游）信息
3. 使用 Compare API 对比每个 fork 与上游仓库的 commit 差异
4. 生成 `data.json` 数据文件和 `index.html` 页面
5. GitHub Actions 自动 commit 并部署到 `gh-pages` 分支

## 配置

### config.json

```json
{
  "exclude": ["owner/repo-to-exclude"],
  "include_only": null
}
```

- `exclude`: 不监控的仓库列表
- `include_only`: 仅监控这些仓库（`null` = 全部监控）

### GitHub Pages 设置

1. 进入仓库 Settings → Pages
2. Source 选择 `gh-pages` 分支
3. 访问 `https://<username>.github.io/fork-update-monitor/`

### 环境变量

| 变量 | 说明 | 来源 |
|------|------|------|
| `GITHUB_TOKEN` | API 访问令牌 | 优先使用 `PERSONAL_ACCESS_TOKEN`，否则用 Actions 默认 token |
| `GITHUB_USERNAME` | GitHub 用户名 | 自动取仓库 owner |

### Personal Access Token（推荐）

GitHub Actions 默认的 `GITHUB_TOKEN` 权限有限，**建议添加 Personal Access Token**：

1. 进入 GitHub → Settings → Developer settings → **Personal access tokens** → Tokens (classic)
2. Generate new token (classic)
3. 勾选 `public_repo` scope（如需监控私有仓库则勾选 `repo`）
4. 复制 token
5. 进入本仓库 Settings → Secrets and variables → Actions → New repository secret
6. Name 填 `PERSONAL_ACCESS_TOKEN`，Value 粘贴 token

> ⚠️ Fine-grained token 需要在 **Account permissions** 中授权 **Repositories: Read-only**，否则无法调用 `/user/repos` API。推荐使用 Classic token（更简单）。

## 本地运行

```bash
export GITHUB_USERNAME=your-username
export GITHUB_TOKEN=your-token  # 推荐，否则容易触发 API rate limit
python monitor.py
# 打开 index.html 查看结果
```

## 项目结构

```
├── .github/workflows/update.yml  # GitHub Actions 工作流
├── .github/workflows/update.yml  # GitHub Actions 工作流
├── monitor.py                    # 主脚本：获取 fork 数据并生成页面（使用 curl 调用 API）
├── template.html                 # HTML 模板（深色主题）
├── config.json                   # 配置：过滤/排除仓库
├── data.json                     # 生成：仓库数据 (gitignore)
├── index.html                    # 生成：最终页面 (部署到 Pages)
└── README.md
```

## License

MIT
