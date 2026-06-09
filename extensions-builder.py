import requests, yaml, json, hashlib, zipfile, io

CONFIG = yaml.safe_load(open("extensions.yml"))


def get_latest_v4_branch(repo):
    url = f"https://api.github.com/repos/{repo}/branches"
    branches = requests.get(url).json()

    v4 = [b["name"] for b in branches if b["name"].startswith("v4")]
    if not v4:
        return "master"

    # naive semver sort (good enough for v4.x.x)
    return sorted(v4, reverse=True)[0]


def download_zip(repo, branch):
    url = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
    r = requests.get(url)
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

    branch = get_latest_v4_branch(repo) if "branch_prefix" in ext else "master"

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
