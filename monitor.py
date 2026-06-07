#!/usr/bin/env python3
"""
GitHub Fork Repos Update Monitor
检查 fork 的仓库是否有上游更新，生成 JSON 数据和 HTML 页面。
使用 subprocess + curl 避免 urllib SSL 兼容性问题。
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone


GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "")


def api_request(url, params=None):
    """通过 curl 发送 GitHub API 请求，返回 JSON 数据或 None。"""
    if params is None:
        params = {}
    headers = [
        "-H", "Accept: application/vnd.github.v3+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
        "-H", "User-Agent: fork-update-monitor",
        "-s",
    ]
    if GITHUB_TOKEN:
        headers.extend(["-H", f"Authorization: Bearer {GITHUB_TOKEN}"])

    separator = "&" if "?" in url else "?"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}{separator}{query}"

    cmd = ["curl"] + headers + [url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"    [ERROR] curl returned {result.returncode}: {result.stderr[:200]}", file=sys.stderr)
            return None
        body = result.stdout
        data = json.loads(body)
        
        # 检查是否返回了错误消息
        if isinstance(data, dict) and "message" in data and "id" not in data:
            msg = data.get("message", "")
            if "rate limit" in msg.lower() or "forbidden" in msg.lower():
                print(f"    [WARN] API error: {msg}", file=sys.stderr)
                return None
            # 有些端点返回 message 但不是错误（如 compare 无差异）
        
        return data
    except subprocess.TimeoutExpired:
        print(f"    [ERROR] curl timeout for {url}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"    [ERROR] JSON decode error for {url}: {e}", file=sys.stderr)
        print(f"    [ERROR] Response: {body[:200] if 'body' in dir() else 'N/A'}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"    [ERROR] Request failed for {url}: {e}", file=sys.stderr)
        return None


def check_rate_limit():
    """检查当前 API rate limit 状态。"""
    data = api_request(f"{GITHUB_API}/rate_limit")
    if data:
        core = data.get("resources", {}).get("core", {})
        print(f"  Rate limit: {core.get('remaining', '?')}/{core.get('limit', '?')} remaining")


def get_fork_repos(username):
    """获取用户所有 fork 的仓库列表。"""
    repos = []
    
    # 方法1: /user/repos（认证用户，含私有）
    if GITHUB_TOKEN:
        print(f"  Trying /user/repos API (authenticated)...")
        page = 1
        while True:
            data = api_request(
                f"{GITHUB_API}/user/repos",
                params={"type": "forks", "per_page": "100", "page": str(page), "sort": "updated"},
            )
            if data is None:
                print(f"    /user/repos failed, falling back", file=sys.stderr)
                break
            if not isinstance(data, list):
                print(f"    /user/repos unexpected type: {type(data)}, falling back", file=sys.stderr)
                break
            repos.extend(data)
            print(f"    Page {page}: got {len(data)} repos")
            if len(data) < 100:
                break
            page += 1
        if repos:
            print(f"  Total from /user/repos: {len(repos)}")
            return repos

    # 方法2: /users/{username}/repos（公开仓库）
    repos = []
    print(f"  Using /users/{username}/repos API (public)...")
    page = 1
    while True:
        data = api_request(
            f"{GITHUB_API}/users/{username}/repos",
            params={"type": "forks", "per_page": "100", "page": str(page), "sort": "updated"},
        )
        if data is None:
            break
        if not isinstance(data, list):
            break
        repos.extend(data)
        print(f"    Page {page}: got {len(data)} repos")
        if len(data) < 100:
            break
        page += 1
    
    print(f"  Total from /users/{username}/repos: {len(repos)}")
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

    # 方法1: Compare API
    compare_url = (
        f"{GITHUB_API}/repos/{parent_full_name}/compare/"
        f"{parent_default_branch}...{fork_full_name}:{fork_default_branch}"
    )
    comparison = api_request(compare_url)

    if comparison and isinstance(comparison, dict) and "behind_by" in comparison:
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
        # 方法2: 比较最新 commit 时间
        print(f"    Compare API failed for {fork_full_name}, using fallback", file=sys.stderr)
        parent_commits = api_request(
            f"{GITHUB_API}/repos/{parent_full_name}/commits?per_page=1&sha={parent_default_branch}"
        )
        fork_commits = api_request(
            f"{GITHUB_API}/repos/{fork_full_name}/commits?per_page=1&sha={fork_default_branch}"
        )
        
        if (parent_commits and isinstance(parent_commits, list) and len(parent_commits) > 0 and
            fork_commits and isinstance(fork_commits, list) and len(fork_commits) > 0):
            parent_date = parent_commits[0].get("commit", {}).get("committer", {}).get("date", "")
            fork_date = fork_commits[0].get("commit", {}).get("committer", {}).get("date", "")
            if parent_date and fork_date:
                if parent_date > fork_date:
                    status = "behind"
                    behind_by = -1
                else:
                    status = "up_to_date"
        else:
            # 方法3: pushed_at
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
    print(f"=== Fork Update Monitor ===")
    print(f"Username: {GITHUB_USERNAME}")
    print(f"Token available: {'yes' if GITHUB_TOKEN else 'no'}")
    if GITHUB_TOKEN:
        print(f"Token prefix: {GITHUB_TOKEN[:4]}...")
    
    check_rate_limit()

    repos = get_fork_repos(GITHUB_USERNAME)
    print(f"\nFound {len(repos)} fork repos")

    if not repos:
        print("WARNING: No fork repos found!")
        check_rate_limit()

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
