"""Settings that outlive one invocation, under `~/.config/iitb/`.

One setting so far: the default download directory, written by
`iitb downloads set-default`. It lives here rather than in the core because
it is the operator's preference about their own laptop, not portal knowledge,
and because a download command must be able to fail with 203 before it
touches the network.

No v1 command downloads anything yet, so nothing reads it back yet. It is
kept ahead of its first consumer on purpose: the setting is shared by every
portal, and the next surface to be built is one that downloads.

Never in a repo, never in an environment variable, never prompted for.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import CliError

FILENAME = "config.json"

# The on-disk key, and the one thing in this module that is not ours to choose.
# The core reads the same file and resolves the same setting itself whenever it
# is not handed one, so a spelling that differs from the core's is not a cosmetic
# difference: it silently means the two never see each other's value, and
# `set-default` stops driving anything the core decides on its own.
DOWNLOAD_DIR_KEY = "downloadsDir"


def config_dir() -> Path:
    # Read at call time, not import time, so a test can point HOME elsewhere.
    return Path.home() / ".config" / "iitb"


def read() -> dict:
    path = config_dir() / FILENAME
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise CliError(190, detail=f"{path}: {exc}") from exc


def download_dir() -> Path | None:
    """The configured default download directory, or None if unset."""
    value = read().get(DOWNLOAD_DIR_KEY)
    return Path(value) if value else None


def set_download_dir(raw: str) -> dict:
    """Store the default download directory, creating it if it is not there.

    Creating it is deliberate. Refusing a path that does not exist yet would
    make the operator run a `mkdir` the CLI could perfectly well run itself.
    """
    path = Path(raw).expanduser()
    if path.exists() and not path.is_dir():
        raise CliError(202, detail=f"{path} exists and is not a directory")
    created = not path.exists()
    try:
        path.mkdir(parents=True, exist_ok=True)
        path = path.resolve()
    except OSError as exc:
        raise CliError(123, detail=f"{path}: {exc}") from exc

    directory = config_dir()
    settings = read()
    settings[DOWNLOAD_DIR_KEY] = str(path)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / FILENAME).write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise CliError(191, detail=f"{directory / FILENAME}: {exc}") from exc

    return {"downloadDir": str(path), "created": created}
