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

1. `monitor.py` 通过 GitHub API 获取用户所有 fork 仓库
2. 对比每个 fork 与上游仓库的 commit 差异
3. 生成 `data.json` 数据文件和 `index.html` 页面
4. GitHub Actions 自动 commit 并部署到 `gh-pages` 分支

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
3. 访问 `https://<username>.github.io/github-repos-update-monitor/`

### 环境变量

| 变量 | 说明 | 来源 |
|------|------|------|
| `GITHUB_TOKEN` | API 访问令牌 | GitHub Actions 自动提供 |
| `GITHUB_USERNAME` | GitHub 用户名 | 自动取仓库 owner |

> 如果你的 fork 数量较多（>60），建议在仓库 Settings → Secrets 中添加 `GITHUB_TOKEN` 为 Personal Access Token 以提高 API 速率限制。

## 本地运行

```bash
export GITHUB_USERNAME=your-username
export GITHUB_TOKEN=your-token  # 可选，公开仓库不需要
python monitor.py
# 打开 index.html 查看结果
```

## 项目结构

```
├── .github/workflows/update.yml  # GitHub Actions 工作流
├── monitor.py                    # 主脚本：获取 fork 数据并生成页面
├── template.html                 # HTML 模板
├── config.json                   # 配置：过滤/排除仓库
├── data.json                     # 生成：仓库数据 (gitignore)
├── index.html                    # 生成：最终页面 (部署到 Pages)
└── README.md
```

## License

MIT
