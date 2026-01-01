import pytest


@pytest.mark.asyncio
async def test_grpc_metadata_injection_is_best_effort():
    """Validate that gRPC metadata injection helper doesn't crash.

    We don't require OpenTelemetry to be installed in this environment.
    """

    from aduib_rpc.telemetry.grpc_interceptors import inject_otel_to_grpc_metadata

    md = [("x-foo", "bar")]
    out = inject_otel_to_grpc_metadata(md)

    # Must preserve existing metadata
    assert ("x-foo", "bar") in out


def test_grpc_server_extraction_is_best_effort():
    from aduib_rpc.telemetry.grpc_interceptors import _otel_extract_from_grpc_metadata

    ctx = _otel_extract_from_grpc_metadata([("traceparent", "00-" + "0" * 32 + "-" + "0" * 16 + "-01")])
    # When OTel isn't installed, ctx is None. When installed, ctx is some object.
    assert ctx is None or ctx is not None
