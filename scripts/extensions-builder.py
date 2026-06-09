import re
import requests
import yaml
import json
import hashlib
import zipfile
import io
import tomllib
from packaging.version import Version, InvalidVersion

CONFIG = yaml.safe_load(open("extensions.yml", "r", encoding="utf-8"))

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "extensions-builder"
}


def get_default_branch(repo):
    r = requests.get(
        f"https://api.github.com/repos/{repo}",
        headers=HEADERS,
        timeout=30
    )
    r.raise_for_status()
    return r.json()["default_branch"]


def get_latest_branch(repo, prefixes):
    page = 1
    names = []

    while True:
        r = requests.get(
            f"https://api.github.com/repos/{repo}/branches",
            headers=HEADERS,
            params={"per_page": 100, "page": page},
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        names.extend(b["name"] for b in data)
        page += 1

    candidates = [
        n for n in names
        if prefixes and any(n.startswith(p) for p in prefixes)
    ]

    print(f"Candidates for prefixes {prefixes}: {candidates}")

    if candidates:
        def version_key(name):
            m = re.match(r"^v(\d+(?:\.\d+)*)", name)
            if m:
                try:
                    return Version(m.group(1))
                except InvalidVersion:
                    pass
            return Version("0.0.0")

        return max(candidates, key=version_key)

    return get_default_branch(repo)


def download_zip(repo, branch):
    url = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    data = r.content
    sha = hashlib.sha256(data).hexdigest()

    return data, sha, len(data), url


def extract_manifest(zip_bytes):
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))

    matches = [f for f in z.namelist() if f.endswith("blender_manifest.toml")]
    if not matches:
        raise Exception("Missing blender_manifest.toml")

    content = z.read(matches[0])
    return tomllib.loads(content.decode("utf-8"))


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


output = {
    "version": "v1",
    "blocklist": [],
    "data": []
}

for ext in CONFIG["extensions"]:
    repo = ext["repo"]
    prefixes = ext.get("prefixes", [])

    branch = get_latest_branch(repo, prefixes)

    zip_data, sha, size, url = download_zip(repo, branch)
    manifest = extract_manifest(zip_data)
    manifest = json_safe(manifest)

    entry = {
        "schema_version": "1.0.0",
        "id": ext["id"],
        "website": f"https://github.com/{repo}",
        "archive_url": url,
        "archive_size": size,
        "archive_hash": f"sha256:{sha}",
        "manifest": manifest,
    }

    output["data"].append(entry)

with open("api/v1/extensions.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
