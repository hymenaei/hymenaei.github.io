import re, requests, yaml, json, hashlib, zipfile, io
from packaging.version import Version, InvalidVersion

CONFIG = yaml.safe_load(open("extensions.yml"))

def get_latest_branch(repo, prefixes, fallback="main"):
    r = requests.get(f"https://api.github.com/repos/{repo}/branches", timeout=30)
    r.raise_for_status()
    branches = r.json()
    names = [b["name"] for b in branches]

    candidates = [n for n in names if any(n.startswith(p) for p in prefixes)]
    if not candidates:
        return fallback

    def branch_key(name):
        # Prefer version-like branches such as v4.2.5, v4.10.0, etc.
        m = re.match(r"^v(\d+(?:\.\d+)*)$", name)
        if m:
            try:
                return (1, Version(m.group(1)))
            except InvalidVersion:
                pass

        m = re.match(r"^v(\d+(?:\.\d+)*)\.", name)
        if m:
            try:
                return (1, Version(m.group(1)))
            except InvalidVersion:
                pass

        # Put non-version branches behind real version branches.
        return (0, name)

    return max(candidates, key=branch_key)


def download_zip(repo, branch):
    url = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.content
    sha = hashlib.sha256(data).hexdigest()
    return data, sha, len(data), url


def extract_manifest(zip_bytes):
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    manifest_file = [f for f in z.namelist() if "blender_manifest.toml" in f][0]
    content = z.read(manifest_file).decode()

    meta = {}
    for line in content.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip().strip('"')

    return meta


output = {
    "version": "v1",
    "blocklist": [],
    "data": []
}

for ext in CONFIG["extensions"]:
    repo = ext["repo"]
    prefixes = ext.get("prefixes", ["main"])

    branch = get_latest_branch(repo, prefixes, fallback="main")

    zip_data, sha, size, url = download_zip(repo, branch)
    manifest = extract_manifest(zip_data)

    output["data"].append({
        "schema_version": "1.0.0",
        "id": ext["id"],
        "name": manifest.get("name", ext["id"]),
        "version": manifest.get("version", branch),
        "type": "add-on",
        "website": f"https://github.com/{repo}",
        "archive_url": url,
        "archive_size": size,
        "archive_hash": f"sha256:{sha}",
    })

with open("api/v1/extensions.json", "w") as f:
    json.dump(output, f, indent=2)
