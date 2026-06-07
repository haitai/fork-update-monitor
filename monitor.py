#!/usr/bin/env python3
"""
GitHub Fork Repos Update Monitor
检查 fork 的仓库是否有上游更新，生成 JSON 数据和 HTML 页面。
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone


GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "")


def api_request(url, params=None):
    """发送 GitHub API 请求，返回 JSON 数据。"""
    if params is None:
        params = {}
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    separator = "&" if "?" in url else "?"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}{separator}{query}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        if e.code == 403:
            print(f"  [WARN] API rate limit or forbidden: {url}", file=sys.stderr)
            print(f"  [WARN] Response: {body}", file=sys.stderr)
            return None
        print(f"  [ERROR] HTTP {e.code} for {url}: {body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [ERROR] Request failed for {url}: {e}", file=sys.stderr)
        return None


def get_fork_repos(username):
    """获取用户所有 fork 的仓库列表。
    
    优先使用 /user/repos（需要 token，可访问私有仓库），
    回退到 /users/{username}/repos（公开仓库，无需 token）。
    """
    repos = []
    
    # 方法1: /user/repos（认证用户的仓库，含私有）
    if GITHUB_TOKEN:
        print(f"  Using /user/repos API (authenticated)")
        page = 1
        while True:
            data = api_request(
                f"{GITHUB_API}/user/repos",
                params={"type": "forks", "per_page": "100", "page": str(page), "sort": "updated"},
            )
            if not data:
                break
            repos.extend(data)
            print(f"    Page {page}: got {len(data)} repos")
            if len(data) < 100:
                break
            page += 1
        if repos:
            return repos
        print(f"  /user/repos returned no data, falling back...")

    # 方法2: /users/{username}/repos（公开仓库）
    print(f"  Using /users/{username}/repos API (public)")
    page = 1
    while True:
        data = api_request(
            f"{GITHUB_API}/users/{username}/repos",
            params={"type": "forks", "per_page": "100", "page": str(page), "sort": "updated"},
        )
        if not data:
            break
        repos.extend(data)
        print(f"    Page {page}: got {len(data)} repos")
        if len(data) < 100:
            break
        page += 1
    return repos


def compare_fork_with_parent(repo):
    """比较 fork 与上游仓库的差异，返回状态信息。"""
    parent = repo.get("parent")
    if not parent:
        return None

    fork_full_name = repo["full_name"]
    parent_full_name = parent["full_name"]
    fork_default_branch = repo.get("default_branch", "main")
    parent_default_branch = parent.get("default_branch", "main")

    behind_by = 0
    ahead_by = 0
    status = "unknown"

    # 方法1: 使用 Compare API
    compare_url = (
        f"{GITHUB_API}/repos/{parent_full_name}/compare/"
        f"{parent_default_branch}...{fork_full_name}:{fork_default_branch}"
    )
    comparison = api_request(compare_url)

    if comparison:
        behind_by = comparison.get("behind_by", 0)
        ahead_by = comparison.get("ahead_by", 0)

        if behind_by == 0 and ahead_by == 0:
            status = "up_to_date"
        elif behind_by > 0 and ahead_by == 0:
            status = "behind"
        elif behind_by == 0 and ahead_by > 0:
            status = "ahead"
        else:
            status = "diverged"
    else:
        # Compare API 失败，用 commit 时间做粗略判断
        print(f"    Compare API failed for {fork_full_name}, using fallback method", file=sys.stderr)
        parent_commit = api_request(
            f"{GITHUB_API}/repos/{parent_full_name}/commits/{parent_default_branch}"
        )
        fork_commit = api_request(
            f"{GITHUB_API}/repos/{fork_full_name}/commits/{fork_default_branch}"
        )
        
        if parent_commit and fork_commit:
            parent_date = parent_commit.get("commit", {}).get("committer", {}).get("date", "")
            fork_date = fork_commit.get("commit", {}).get("committer", {}).get("date", "")
            if parent_date and fork_date:
                if parent_date > fork_date:
                    status = "behind"
                    behind_by = -1  # 未知具体数量
                elif parent_date <= fork_date:
                    status = "up_to_date"
        else:
            # 最后用 pushed_at 判断
            parent_pushed = parent.get("pushed_at", "")
            fork_pushed = repo.get("pushed_at", "")
            if parent_pushed and fork_pushed:
                if parent_pushed > fork_pushed:
                    status = "behind"
                    behind_by = -1
                else:
                    status = "up_to_date"

    return {
        "fork_repo": fork_full_name,
        "fork_url": repo["html_url"],
        "fork_description": repo.get("description") or "",
        "fork_default_branch": fork_default_branch,
        "fork_updated_at": repo.get("updated_at", ""),
        "fork_pushed_at": repo.get("pushed_at", ""),
        "fork_stars": repo.get("stargazers_count", 0),
        "fork_forks": repo.get("forks_count", 0),
        "parent_repo": parent_full_name,
        "parent_url": parent["html_url"],
        "parent_description": parent.get("description") or "",
        "parent_default_branch": parent_default_branch,
        "parent_updated_at": parent.get("updated_at", ""),
        "parent_pushed_at": parent.get("pushed_at", ""),
        "parent_stars": parent.get("stargazers_count", 0),
        "parent_forks": parent.get("forks_count", 0),
        "behind_by": behind_by,
        "ahead_by": ahead_by,
        "status": status,
    }


def load_config():
    """加载 config.json 配置。"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def filter_repos(results, config):
    """根据配置过滤仓库。"""
    exclude = set(config.get("exclude", []))
    include_only = config.get("include_only", None)
    if include_only is not None:
        include_only = set(include_only)

    filtered = []
    for r in results:
        if r is None:
            continue
        name = r["fork_repo"]
        if name in exclude:
            continue
        if include_only is not None and name not in include_only:
            continue
        filtered.append(r)
    return filtered


def render_html(data, output_path):
    """渲染 HTML 页面。"""
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    json_data = json.dumps(data, ensure_ascii=False, indent=2)
    html = template.replace("{{DATA_PLACEHOLDER}}", json_data)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    if not GITHUB_USERNAME:
        print("Error: GITHUB_USERNAME environment variable is required.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    print(f"Fetching fork repos for user: {GITHUB_USERNAME}")
    print(f"Token available: {'yes' if GITHUB_TOKEN else 'no'}")

    repos = get_fork_repos(GITHUB_USERNAME)
    print(f"Found {len(repos)} fork repos")

    if not repos:
        print("WARNING: No fork repos found! This might be due to:")
        print("  - API rate limit (no token or token lacks scope)")
        print("  - User has no fork repos")
        print("  - Token needs 'repo' scope for private repos")

    results = []
    for i, repo in enumerate(repos, 1):
        parent = repo.get("parent")
        if not parent:
            print(f"  [{i}/{len(repos)}] {repo['full_name']} — skipped (no parent)")
            continue
        print(f"  [{i}/{len(repos)}] {repo['full_name']} ← {parent['full_name']}")
        result = compare_fork_with_parent(repo)
        if result:
            print(f"    → {result['status']} (behind: {result['behind_by']}, ahead: {result['ahead_by']})")
        results.append(result)

    results = filter_repos(results, config)

    # 统计
    status_counts = {"up_to_date": 0, "behind": 0, "ahead": 0, "diverged": 0, "unknown": 0}
    for r in results:
        if r:
            status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    output_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "username": GITHUB_USERNAME,
        "total_forks": len(results),
        "status_counts": status_counts,
        "repos": [r for r in results if r is not None],
    }

    # 保存 JSON
    output_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(output_dir, "data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nJSON saved to {json_path}")

    # 渲染 HTML
    html_path = os.path.join(output_dir, "index.html")
    render_html(output_data, html_path)
    print(f"HTML saved to {html_path}")

    print(f"\nSummary:")
    print(f"  Up to date: {status_counts['up_to_date']}")
    print(f"  Behind:     {status_counts['behind']}")
    print(f"  Ahead:      {status_counts['ahead']}")
    print(f"  Diverged:   {status_counts['diverged']}")
    print(f"  Unknown:    {status_counts['unknown']}")


if __name__ == "__main__":
    main()
