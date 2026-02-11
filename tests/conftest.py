from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    src_path = str(SRC)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Force anyio-based tests to only run on asyncio backend.

    The repo uses anyio in runtime utilities, but the dev dependency group doesn't
    include trio. Without this, `@pytest.mark.anyio` tests get parametrized for
    (asyncio, trio) and fail on environments without trio installed.
    """

    for item in items:
        marker = item.get_closest_marker("anyio")
        if marker is None:
            continue

        # Remove the original anyio marker and replace it with one that pins backend.
        # This avoids mutating marker.kwargs (read-only in some pytest versions).
        try:
            item.own_markers = [m for m in item.own_markers if m.name != "anyio"]  # type: ignore[attr-defined]
        except Exception:
            pass

        item.add_marker(pytest.mark.anyio(backend="asyncio"))
