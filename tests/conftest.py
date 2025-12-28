import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Force anyio-based tests to only run on asyncio backend.

    The repo uses anyio in runtime utilities, but the dev dependency group doesn't
    include trio. Without this, `@pytest.mark.anyio` tests get parametrized for
    (asyncio, trio) and fail on environments without trio installed.
    """

    for item in items:
        marker = item.get_closest_marker("anyio")
        if marker is not None:
            marker.kwargs["backend"] = "asyncio"

