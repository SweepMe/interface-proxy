"""Make sure that the version number has been increased and does not exist on PyPI yet."""

import importlib.metadata
import subprocess

lib = "interface-proxy"

lib_version = importlib.metadata.version(lib)

not_found = False

try:
    subprocess.check_call(
        [  # noqa: S603, S607
            "python",
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--ignore-installed",
            "--dry-run",
            f"{lib}=={lib_version}",
        ],
    )
except subprocess.SubprocessError:
    not_found = True

if not_found is False:
    exc_msg = (
        f"Version {lib_version} seems to be published already. "
        f"Did you forget to increase the version number in interface_proxy/__init__.py?"
    )
    print(f"::error::{exc_msg}")  # noqa: T201
    raise ValueError(exc_msg)
