"""Stage a Notion download-skill response without executing or activating it."""

import io
import json
import re
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import urlopen

MAX_BYTES = 25 * 1024 * 1024


def unwrap(value):
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    if value.get("isError"):
        raise ValueError("MCP returned an error; nothing extracted")
    if "markdown" in value or "url" in value:
        return value
    if isinstance(value.get("structuredContent"), dict):
        return unwrap(value["structuredContent"])
    for block in value.get("content", []):
        if block.get("type") == "text":
            try:
                return unwrap(json.loads(block["text"]))
            except (ValueError, KeyError):
                continue
    raise ValueError("No download-skill payload found in MCP response")


def validate_skill(data):
    if len(data) > 200_000:
        raise ValueError("SKILL.md exceeds 200 KB")
    text = data.decode("utf-8")
    front = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not front:
        raise ValueError("SKILL.md needs YAML frontmatter")
    if not re.search(r"^name:\s*\S", front[1], re.M) or not re.search(
        r"^description:\s*\S", front[1], re.M
    ):
        raise ValueError("SKILL.md requires name and description")


def archive_files(data):
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        total = 0
        seen = set()
        for index, item in enumerate(archive):
            if index >= 1000:
                raise ValueError("Archive exceeds 1000 entries")
            path = PurePosixPath(item.name)
            if path.is_absolute() or ".." in path.parts or "\\" in item.name or ":" in item.name:
                raise ValueError("Unsafe archive path")
            if not path.parts:
                if item.isdir():
                    continue
                raise ValueError("Empty archive path")
            if not item.isdir() and not item.isfile():
                raise ValueError("Links and special files are not allowed")
            key = str(path).casefold()
            if key in seen:
                raise ValueError("Duplicate archive path")
            seen.add(key)
            if item.isdir():
                continue
            total += item.size
            if total > MAX_BYTES:
                raise ValueError("Expanded archive exceeds 25 MiB")
            source = archive.extractfile(item)
            if source is None:
                raise ValueError("Unreadable archive entry")
            files[path] = source.read()
    skills = [path for path in files if path.name == "SKILL.md"]
    if len(skills) != 1 or len(skills[0].parts) > 2:
        raise ValueError("Expected one SKILL.md at root or inside one top-level folder")
    root = skills[0].parent
    if any(root not in path.parents for path in files):
        raise ValueError("All supporting files must be inside the skill directory")
    validate_skill(files[skills[0]])
    return {path.relative_to(root): content for path, content in files.items()}


def extract(value, destination):
    payload = unwrap(value)
    if "markdown" in payload:
        data = payload["markdown"].encode("utf-8")
        validate_skill(data)
        files = {PurePosixPath("SKILL.md"): data}
    else:
        url = payload["url"]
        if urlparse(url).scheme != "https":
            raise ValueError("Download URL must use HTTPS")
        with urlopen(url, timeout=60) as response:
            if urlparse(response.url).scheme != "https":
                raise ValueError("Download redirected away from HTTPS")
            data = response.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("Compressed archive exceeds 20 MiB")
        files = archive_files(data)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination exists; choose a new staging directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        stage = Path(temporary) / "skill"
        stage.mkdir(mode=0o700)
        for path, content in files.items():
            target = stage.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o600)
        stage.rename(destination)
    return {
        "id": payload.get("id"), "version_id": payload.get("version_id"),
        "destination": str(destination), "files": sorted(str(path) for path in files),
        "status": "staged_for_review_not_activated",
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: extract-skill.py RESPONSE.json NEW_STAGING_DIRECTORY")
    try:
        print(json.dumps(extract(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2]), indent=2))
    except Exception as error:
        # Download URLs may contain credentials; never echo exception messages.
        sys.exit(f"Extraction refused ({type(error).__name__}); check payload/archive and choose a new staging directory.")
