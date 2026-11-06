"""Probe which pages_build_version values the Pages deployment API accepts, and whether a reused one goes live."""
import json, os, sys, time, urllib.request, urllib.error

env = os.environ
repo, sha, run = env["GITHUB_REPOSITORY"], env["GITHUB_SHA"], env["GITHUB_RUN_ID"]
api = f"https://api.github.com/repos/{repo}/pages/deployments"
auth = {"Authorization": f"Bearer {env['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json", "User-Agent": "probe"}
site = f"https://linuxserver-playground.github.io/{repo.split('/')[1]}/stamp.txt"

def call(method, url, body=None, headers=auth):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers))
    if data: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:300]

def oidc():
    s, b = call("GET", env["ACTIONS_ID_TOKEN_REQUEST_URL"], headers={"Authorization": f"bearer {env['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"})
    return b["value"]

def served():
    try:
        with urllib.request.urlopen(f"{site}?t={time.time()}", timeout=20) as r:
            return r.read().decode().strip()
    except Exception as e:
        return f"error {e}"

def trial(label, version, artifact_id, want):
    print(f"\n== {label}: version {version}", flush=True)
    s, b = call("POST", api, {"artifact_id": artifact_id, "pages_build_version": version, "oidc_token": oidc()})
    print(f"create: HTTP {s} {json.dumps(b)[:300]}", flush=True)
    if s >= 300:
        return
    dep = str(b.get("id") or version)
    for _ in range(40):
        time.sleep(5)
        s2, st = call("GET", f"{api}/{dep}")
        status = st.get("status") if isinstance(st, dict) else st
        if status in ("succeed", "deployment_failed", "deployment_content_failed", "deployment_cancelled", "deployment_lost") or s2 >= 300:
            break
    print(f"status: HTTP {s2} {status}", flush=True)
    for i in range(24):
        got = served()
        if got == want:
            print(f"served: {got} after {i*5} s  -> LIVE", flush=True)
            return
        time.sleep(5)
    print(f"served: {got} (wanted {want}) -> NOT LIVE after 120 s", flush=True)

ids = json.loads(env["IDS"])
parent = env["PARENT"]
trial("A head sha", sha, int(ids["a"]), f"a-{run}")
trial("B head sha again, A live", sha, int(ids["b"]), f"b-{run}")
trial("C head sha a third time", sha, int(ids["c"]), f"c-{run}")
trial("D parent sha", parent, int(ids["d"]), f"d-{run}")
trial("E head sha after parent", sha, int(ids["e"]), f"e-{run}")
