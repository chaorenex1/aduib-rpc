import pytest

from aduib_rpc.rpc.methods import MethodName


@pytest.mark.parametrize(
    ("method", "service", "handler"),
    [
        ("rpc.v2/Calc/Calc.add", "Calc", "Calc.add"),
        (" /rpc.v2/Calc/Calc.add ", "Calc", "Calc.add"),
        ("Calc.add", "Calc", "add"),
        ("Calc.Calc.add", "Calc", "Calc.add"),
        ("Calc.some_module.add", "Calc", "some_module.add"),
        ("Calc/add", "Calc", "add"),
        ("Calc:Cls.m", "Calc", "Cls.m"),
    ],
)
def test_parse_compat(method: str, service: str, handler: str) -> None:
    parsed = MethodName.parse_compat(method)
    assert parsed.service == service
    assert parsed.handler == handler


def test_format_v2_roundtrip() -> None:
    m = MethodName.format_v2("Svc", "A.b")
    parsed = MethodName.parse_compat(m)
    assert parsed.service == "Svc"
    assert parsed.handler == "A.b"
