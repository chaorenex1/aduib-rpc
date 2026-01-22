from __future__ import annotations

import uuid

import pytest

from aduib_rpc.discover.entities.service_instance import ServiceInstance
from aduib_rpc.discover.health.health_checker import HttpHealthChecker
from aduib_rpc.discover.health.health_status import HealthCheckConfig, HealthCheckResult, HealthStatus
from aduib_rpc.observability.metrics import Counter, Gauge, Histogram, MetricLabels, RpcMetrics
from aduib_rpc.resilience.retry_policy import RetryExecutor, RetryPolicy, RetryStrategy
from aduib_rpc.utils.constant import TransportSchemes


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeClient:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self._response = response
        self.last_url: str | None = None

    async def get(self, url: str) -> FakeResponse:
        self.last_url = url
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _get_gauge_value(gauge: Gauge, labels: MetricLabels) -> float:
    key = (labels.service, labels.method)
    with gauge._lock:
        return gauge._values.get(key, 0.0)


def _get_histogram_observations(histogram: Histogram, labels: MetricLabels) -> list[float]:
    key = (labels.service, labels.method, labels.status)
    with histogram._lock:
        return list(histogram._observations.get(key, []))


@pytest.fixture()
def health_config() -> HealthCheckConfig:
    return HealthCheckConfig()


@pytest.fixture()
def service_instance() -> ServiceInstance:
    return ServiceInstance(
        service_name="svc",
        host="localhost",
        port=8080,
        scheme=TransportSchemes.HTTP,
    )


@pytest.fixture()
def http_checker_factory(
    health_config: HealthCheckConfig, monkeypatch: pytest.MonkeyPatch
):
    def _factory(response: FakeResponse | Exception) -> tuple[HttpHealthChecker, FakeClient]:
        checker = HttpHealthChecker(health_config)
        client = FakeClient(response)

        async def _get_client() -> FakeClient:
            return client

        monkeypatch.setattr(checker, "_get_client", _get_client)
        return checker, client

    return _factory


@pytest.fixture()
def metric_labels() -> MetricLabels:
    return MetricLabels(service="svc", method="op", status="ok", error_code="")


class TestHealthStatus:
    def test_status_enum_values(self) -> None:
        assert {member.name: member.value for member in HealthStatus} == {
            "HEALTHY": "healthy",
            "UNHEALTHY": "unhealthy",
            "DEGRADED": "degraded",
            "UNKNOWN": "unknown",
        }

    def test_health_check_result_creation(self) -> None:
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            latency_ms=12.5,
            message="ok",
        )
        assert result.status is HealthStatus.HEALTHY
        assert result.latency_ms == 12.5
        assert result.message == "ok"
        assert isinstance(result.checked_at_ms, int)
        assert result.checked_at_ms > 0

    def test_health_check_config_defaults(self) -> None:
        config = HealthCheckConfig()
        assert config.interval_seconds == 10.0
        assert config.timeout_seconds == 5.0
        assert config.healthy_threshold == 2
        assert config.unhealthy_threshold == 3
        assert config.path == "/health"


class TestHttpHealthChecker:
    @pytest.mark.asyncio
    async def test_check_healthy_200(
        self,
        http_checker_factory,
        service_instance: ServiceInstance,
    ) -> None:
        checker, client = http_checker_factory(FakeResponse(200))
        result = await checker.check(service_instance)

        assert result.status is HealthStatus.HEALTHY
        assert result.message is None
        assert result.latency_ms >= 0
        assert client.last_url == "http://localhost:8080/health"

    @pytest.mark.asyncio
    async def test_check_degraded_503(
        self,
        http_checker_factory,
        service_instance: ServiceInstance,
    ) -> None:
        checker, _ = http_checker_factory(FakeResponse(503))
        result = await checker.check(service_instance)

        assert result.status is HealthStatus.DEGRADED
        assert result.message == "Service degraded"

    @pytest.mark.asyncio
    async def test_check_unhealthy_other(
        self,
        http_checker_factory,
        service_instance: ServiceInstance,
    ) -> None:
        checker, _ = http_checker_factory(FakeResponse(500))
        result = await checker.check(service_instance)

        assert result.status is HealthStatus.UNHEALTHY
        assert result.message == "HTTP 500"

    @pytest.mark.asyncio
    async def test_check_timeout_error(
        self,
        http_checker_factory,
        service_instance: ServiceInstance,
    ) -> None:
        checker, _ = http_checker_factory(TimeoutError("timeout"))
        result = await checker.check(service_instance)

        assert result.status is HealthStatus.UNHEALTHY
        assert result.message == "timeout"


class TestMetrics:
    @pytest.mark.asyncio
    async def test_counter_increment(self, metric_labels: MetricLabels) -> None:
        counter = Counter("requests_total", "Total requests")
        await counter.inc(metric_labels)

        key = (
            metric_labels.service,
            metric_labels.method,
            metric_labels.status,
            metric_labels.error_code,
        )
        assert counter.get()[key] == 1.0

    @pytest.mark.asyncio
    async def test_counter_multiple_labels(self) -> None:
        counter = Counter("requests_total", "Total requests")
        labels_a = MetricLabels(service="svc-a", method="m1", status="ok", error_code="")
        labels_b = MetricLabels(service="svc-b", method="m1", status="ok", error_code="")

        await counter.record(2.0, labels_a)
        await counter.inc(labels_b)

        values = counter.get()
        assert values[(labels_a.service, labels_a.method, labels_a.status, labels_a.error_code)] == 2.0
        assert values[(labels_b.service, labels_b.method, labels_b.status, labels_b.error_code)] == 1.0

    @pytest.mark.asyncio
    async def test_histogram_percentile(self, metric_labels: MetricLabels) -> None:
        histogram = Histogram("latency", "Request latency")
        await histogram.record(0.1, metric_labels)
        await histogram.record(0.3, metric_labels)
        await histogram.record(0.2, metric_labels)

        percentile = await histogram.get_percentile(metric_labels, 50)

        assert percentile == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_gauge_set_inc_dec(self, metric_labels: MetricLabels) -> None:
        gauge = Gauge("active", "Active requests")
        await gauge.set(3.0, metric_labels)
        await gauge.inc(metric_labels, delta=2.0)
        await gauge.dec(metric_labels, delta=1.0)

        assert _get_gauge_value(gauge, metric_labels) == 4.0

    @pytest.mark.asyncio
    async def test_rpc_metrics_record_request(self) -> None:
        service = f"svc-{uuid.uuid4()}"
        labels = MetricLabels(
            service=service,
            method="rpc.call",
            status="success",
            error_code="",
        )
        await RpcMetrics.record_request(
            service=labels.service,
            method=labels.method,
            status=labels.status,
            duration_seconds=0.25,
            request_size=120,
            response_size=240,
        )

        total = RpcMetrics.request_total.get()
        total_key = (labels.service, labels.method, labels.status, labels.error_code)
        assert total[total_key] == 1.0

        duration_obs = _get_histogram_observations(RpcMetrics.request_duration, labels)
        assert duration_obs[-1] == pytest.approx(0.25)

        request_obs = _get_histogram_observations(RpcMetrics.request_size, labels)
        assert request_obs[-1] == pytest.approx(120.0)

        response_obs = _get_histogram_observations(RpcMetrics.response_size, labels)
        assert response_obs[-1] == pytest.approx(240.0)


class TestRetryPolicy:
    @pytest.mark.asyncio
    async def test_fixed_strategy_delay(self) -> None:
        policy = RetryPolicy(
            strategy=RetryStrategy.FIXED,
            initial_delay_ms=150,
            max_delay_ms=1000,
            jitter=0.0,
        )
        executor = RetryExecutor(policy)
        delay = await executor._compute_delay(attempt=3)

        assert delay == pytest.approx(0.15)

    @pytest.mark.asyncio
    async def test_exponential_strategy_delay(self) -> None:
        policy = RetryPolicy(
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay_ms=100,
            backoff_multiplier=2.0,
            max_delay_ms=1000,
            jitter=0.0,
        )
        executor = RetryExecutor(policy)
        delay = await executor._compute_delay(attempt=3)

        assert delay == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_linear_strategy_delay(self) -> None:
        policy = RetryPolicy(
            strategy=RetryStrategy.LINEAR,
            initial_delay_ms=100,
            max_delay_ms=1000,
            jitter=0.0,
        )
        executor = RetryExecutor(policy)
        delay = await executor._compute_delay(attempt=3)

        assert delay == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_retry_with_jitter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        policy = RetryPolicy(
            strategy=RetryStrategy.FIXED,
            initial_delay_ms=100,
            max_delay_ms=1000,
            jitter=0.1,
        )
        executor = RetryExecutor(policy)
        monkeypatch.setattr(
            "aduib_rpc.resilience.retry_policy.random.random",
            lambda: 1.0,
        )
        delay = await executor._compute_delay(attempt=1)

        assert delay == pytest.approx(0.11)

    @pytest.mark.asyncio
    async def test_retry_executor_max_attempts(self) -> None:
        policy = RetryPolicy(
            max_attempts=2,
            initial_delay_ms=0,
            jitter=0.0,
        )
        executor = RetryExecutor(policy)
        attempts = 0

        async def _fail() -> None:
            nonlocal attempts
            attempts += 1
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await executor.execute(_fail)

        assert attempts == 2
