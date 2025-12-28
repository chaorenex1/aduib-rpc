import warnings

import pytest

from aduib_rpc.server.rpc_execution.service_call import FuncCallContext, interceptors


def test_deprecated_interceptors_view_is_dynamic_and_mutable():
    FuncCallContext.reset()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", DeprecationWarning)
        interceptors.append(object())
        assert len(interceptors) == 1
        assert any(issubclass(x.category, DeprecationWarning) for x in w)

    # reset should clear default runtime and thus the view
    FuncCallContext.reset()
    assert len(interceptors) == 0

