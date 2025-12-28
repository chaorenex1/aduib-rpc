from aduib_rpc.server.request_handlers.default_request_handler import DefaultRequestHandler


def test_default_request_handler_init_accepts_kwargs_and_sets_types():
    handler = DefaultRequestHandler(interceptors=None, request_executors=None)
    assert handler.interceptors == []
    assert handler.request_executors == {}

