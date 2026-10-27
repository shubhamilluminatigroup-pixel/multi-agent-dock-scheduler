import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_ID = "178c6fc778ccc68e1d6a"
REPO_NAME = "multi-agent-dock-scheduler"
REPO_DESC = (
    "Autonomous Multi-Agent ETA Dock & Slot Scheduler — 5-Agent Pipeline, "
    "Dual SQLite DBs, 24-Hr Scrollable Gantt Chart (30/45/60m Slots & Red Overlap Indicator), "
    "External TMS/WMS/Telematics Connectors & Carrier Transport Portal"
)

EXCLUDE_DIRS = {"__pycache__", "chrome_ppt_profile", ".git", ".venv", "venv"}


def github_api(method, url, token, payload=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "MultiAgentDockScheduler-Uploader",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
        except Exception:
            err_json = {"message": err_body}
        return e.code, err_json


def copy_to_clipboard(text):
    try:
        p = subprocess.Popen(["clip"], stdin=subprocess.PIPE, close_fds=True)
        p.communicate(input=text.encode("utf-8"))
    except Exception:
        pass


def start_device_flow():
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "scope": "repo read:user",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://github.com/login/device/code",
        data=data,
        headers={"Accept": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
    device_code = resp["device_code"]
    user_code = resp["user_code"]
    verification_uri = resp["verification_uri"]
    interval = int(resp.get("interval", 5))

    copy_to_clipboard(user_code)
    print("=" * 72, flush=True)
    print("GITHUB AUTHORIZATION REQUIRED (ONE-CLICK BROWSER LOGIN)", flush=True)
    print(f"1. Verification URL : {verification_uri}", flush=True)
    print(f"2. One-Time Code    : {user_code}  (Already copied to your clipboard!)", flush=True)
    print("=" * 72, flush=True)

    try:
        webbrowser.open(verification_uri)
    except Exception:
        pass

    return device_code, user_code, verification_uri, interval


def poll_for_token(device_code, interval):
    poll_url = "https://github.com/login/oauth/access_token"
    while True:
        time.sleep(interval)
        data = urllib.parse.urlencode({
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }).encode("utf-8")
        req = urllib.request.Request(
            poll_url,
            data=data,
            headers={"Accept": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
        if "access_token" in resp:
            return resp["access_token"]
        err = resp.get("error")
        if err == "authorization_pending":
            continue
        elif err == "slow_down":
            interval += 5
            continue
        else:
            raise RuntimeError(f"GitHub authorization failed or expired: {err}")


def collect_project_files():
    files_to_upload = []
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel_root = os.path.relpath(root, BASE_DIR)
        for fname in files:
            if fname.endswith(".pyc"):
                continue
            if rel_root == "static" and fname.endswith(".pptx"):
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, BASE_DIR).replace("\\", "/")
            files_to_upload.append((rel_path, full_path))
    files_to_upload.sort(key=lambda x: x[0])
    return files_to_upload


def ensure_repo_exists(token, owner):
    status, repo_info = github_api("GET", f"https://api.github.com/repos/{owner}/{REPO_NAME}", token)
    if status == 200:
        print(f"Found existing repository: https://github.com/{owner}/{REPO_NAME}", flush=True)
        # Ensure it isn't completely empty without a default branch commit
        return repo_info

    print(f"Creating new public repository '{REPO_NAME}' under '{owner}'...", flush=True)
    status, created = github_api(
        "POST",
        "https://api.github.com/user/repos",
        token,
        {
            "name": REPO_NAME,
            "description": REPO_DESC,
            "private": False,
            "auto_init": True,
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"Failed to create repository ({status}): {created}")
    time.sleep(2.0)
    return created


def push_all_files_to_github(token):
    status, user_info = github_api("GET", "https://api.github.com/user", token)
    if status != 200:
        raise RuntimeError(f"Could not fetch GitHub user profile ({status}): {user_info}")
    owner = user_info["login"]
    print(f"Authenticated as GitHub user: {owner}", flush=True)

    repo_info = ensure_repo_exists(token, owner)
    default_branch = repo_info.get("default_branch") or "main"

    # Get latest commit SHA on default_branch
    status, ref_info = github_api(
        "GET",
        f"https://api.github.com/repos/{owner}/{REPO_NAME}/git/ref/heads/{default_branch}",
        token,
    )
    if status != 200:
        # Initialize with a README via Contents API if branch doesn't exist yet
        github_api(
            "PUT",
            f"https://api.github.com/repos/{owner}/{REPO_NAME}/contents/README.md",
            token,
            {
                "message": "Initialize repository",
                "content": base64.b64encode(b"# Autonomous Multi-Agent Dock Scheduler\n").decode("ascii"),
            },
        )
        time.sleep(1.5)
        status, ref_info = github_api(
            "GET",
            f"https://api.github.com/repos/{owner}/{REPO_NAME}/git/ref/heads/{default_branch}",
            token,
        )

    latest_commit_sha = ref_info["object"]["sha"]
    status, commit_info = github_api(
        "GET",
        f"https://api.github.com/repos/{owner}/{REPO_NAME}/git/commits/{latest_commit_sha}",
        token,
    )
    base_tree_sha = commit_info["tree"]["sha"]

    project_files = collect_project_files()
    print(f"Uploading {len(project_files)} files to {owner}/{REPO_NAME}...", flush=True)

    tree_entries = []
    for idx, (rel_path, full_path) in enumerate(project_files, 1):
        with open(full_path, "rb") as f:
            raw_bytes = f.read()
        b64_content = base64.b64encode(raw_bytes).decode("ascii")
        status, blob_info = github_api(
            "POST",
            f"https://api.github.com/repos/{owner}/{REPO_NAME}/git/blobs",
            token,
            {
                "content": b64_content,
                "encoding": "base64",
            },
        )
        if status not in (200, 201):
            raise RuntimeError(f"Failed creating blob for {rel_path} ({status}): {blob_info}")
        tree_entries.append({
            "path": rel_path,
            "mode": "100644",
            "type": "blob",
            "sha": blob_info["sha"],
        })
        print(f"  [{idx}/{len(project_files)}] Uploaded {rel_path} ({len(raw_bytes):,} bytes)", flush=True)

    status, new_tree = github_api(
        "POST",
        f"https://api.github.com/repos/{owner}/{REPO_NAME}/git/trees",
        token,
        {
            "base_tree": base_tree_sha,
            "tree": tree_entries,
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"Failed creating git tree ({status}): {new_tree}")

    commit_msg = (
        "Add Autonomous Multi-Agent ETA Dock & Slot Scheduler, "
        "24-Hr Gantt Chart, Transport Portal, Screenshots & 14-Slide PPTX"
    )
    status, new_commit = github_api(
        "POST",
        f"https://api.github.com/repos/{owner}/{REPO_NAME}/git/commits",
        token,
        {
            "message": commit_msg,
            "tree": new_tree["sha"],
            "parents": [latest_commit_sha],
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"Failed creating commit ({status}): {new_commit}")

    status, updated_ref = github_api(
        "PATCH",
        f"https://api.github.com/repos/{owner}/{REPO_NAME}/git/refs/heads/{default_branch}",
        token,
        {
            "sha": new_commit["sha"],
            "force": True,
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"Failed updating branch ref ({status}): {updated_ref}")

    repo_url = f"https://github.com/{owner}/{REPO_NAME}"
    print("=" * 72, flush=True)
    print(f"SUCCESS! All {len(project_files)} files pushed to GitHub:", flush=True)
    print(f"Repository URL: {repo_url}", flush=True)
    print("=" * 72, flush=True)


if __name__ == "__main__":
    device_code, user_code, verification_uri, interval = start_device_flow()
    token = poll_for_token(device_code, interval)
    push_all_files_to_github(token)
