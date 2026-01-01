def test_telemetry_optional_import_does_not_crash():
    # Telemetry is an optional extra. Importing the module should never crash,
    # even if OpenTelemetry deps are not installed in the environment.
    import aduib_rpc.telemetry as telemetry

    assert hasattr(telemetry, "TelemetryConfig")
    assert hasattr(telemetry, "configure_telemetry")


def test_public_api_reexports_optional_telemetry_symbols():
    # Root package re-exports telemetry symbols as optional.
    import aduib_rpc

    assert hasattr(aduib_rpc, "TelemetryConfig")
    assert hasattr(aduib_rpc, "configure_telemetry")

