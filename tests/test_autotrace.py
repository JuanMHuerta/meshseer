from datetime import UTC, datetime

from meshradar.autotrace import AutoTracerouteConfig, AutoTracerouteService
from meshradar.collector import CollectorStatus, TraceRouteResult
from meshradar.models import NodeRecord
from meshradar.storage import MeshRepository


class FakeCollector:
    def __init__(self, result: TraceRouteResult, *, connected: bool = True):
        self.result = result
        self.status = CollectorStatus(state="connected" if connected else "disconnected", connected=connected, detail=None)
        self.calls: list[tuple[int, int, int, int]] = []

    def current_status(self) -> CollectorStatus:
        return self.status

    def trace_route(self, dest_node_num: int, *, hop_limit: int, channel_index: int, timeout_seconds: int) -> TraceRouteResult:
        self.calls.append((dest_node_num, hop_limit, channel_index, timeout_seconds))
        return self.result


def upsert_node(
    repo: MeshRepository,
    *,
    node_num: int,
    short_name: str,
    last_heard_at: str,
    hops_away: int | None,
    via_mqtt: bool,
) -> None:
    repo.upsert_node(
        NodeRecord(
            node_num=node_num,
            node_id=f"!{node_num:08x}",
            short_name=short_name,
            long_name=f"{short_name} Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at=last_heard_at,
            last_snr=5.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json=f'{{"num":{node_num}}}',
            updated_at=last_heard_at,
            hops_away=hops_away,
            via_mqtt=via_mqtt,
        )
    )


def test_autotrace_service_records_successful_cycle(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    upsert_node(repo, node_num=101, short_name="LOCAL", last_heard_at="2026-03-30T12:00:00Z", hops_away=None, via_mqtt=False)
    upsert_node(repo, node_num=202, short_name="BETA", last_heard_at="2026-03-30T11:59:00Z", hops_away=9, via_mqtt=False)
    collector = FakeCollector(
        TraceRouteResult(
            status="success",
            request_mesh_packet_id=77,
            response_mesh_packet_id=88,
            detail=None,
        )
    )
    now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC)
    service = AutoTracerouteService(
        repository=repo,
        collector=collector,
        local_node_num_getter=lambda: 101,
        config=AutoTracerouteConfig(
            interval_seconds=300,
            target_window_hours=24,
            cooldown_hours=24,
            ack_only_cooldown_hours=6,
            response_timeout_seconds=20,
        ),
        now_provider=lambda: now,
    )

    service.enable()
    attempt = service.run_cycle()

    assert collector.calls == [(202, 7, 0, 20)]
    assert attempt is not None
    assert attempt["target_node_num"] == 202
    assert attempt["status"] == "success"
    assert attempt["request_mesh_packet_id"] == 77
    assert attempt["response_mesh_packet_id"] == 88


def test_autotrace_service_failed_attempt_enters_cooldown(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    upsert_node(repo, node_num=101, short_name="LOCAL", last_heard_at="2026-03-30T12:00:00Z", hops_away=None, via_mqtt=False)
    upsert_node(repo, node_num=202, short_name="BETA", last_heard_at="2026-03-30T11:59:00Z", hops_away=2, via_mqtt=False)
    collector = FakeCollector(
        TraceRouteResult(
            status="timeout",
            request_mesh_packet_id=77,
            response_mesh_packet_id=None,
            detail="Timed out waiting for traceroute response",
        )
    )
    now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC)
    service = AutoTracerouteService(
        repository=repo,
        collector=collector,
        local_node_num_getter=lambda: 101,
        config=AutoTracerouteConfig(
            interval_seconds=300,
            target_window_hours=24,
            cooldown_hours=24,
            ack_only_cooldown_hours=6,
            response_timeout_seconds=20,
        ),
        now_provider=lambda: now,
    )

    service.enable()
    first = service.run_cycle()
    second = service.run_cycle()

    assert first is not None
    assert first["status"] == "timeout"
    assert second is None
    assert len(collector.calls) == 1


def test_autotrace_service_does_nothing_when_disabled_or_disconnected(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    upsert_node(repo, node_num=101, short_name="LOCAL", last_heard_at="2026-03-30T12:00:00Z", hops_away=None, via_mqtt=False)
    upsert_node(repo, node_num=202, short_name="BETA", last_heard_at="2026-03-30T11:59:00Z", hops_away=2, via_mqtt=False)
    collector = FakeCollector(
        TraceRouteResult(
            status="success",
            request_mesh_packet_id=77,
            response_mesh_packet_id=88,
            detail=None,
        ),
        connected=False,
    )
    service = AutoTracerouteService(
        repository=repo,
        collector=collector,
        local_node_num_getter=lambda: 101,
        config=AutoTracerouteConfig(
            interval_seconds=300,
            target_window_hours=24,
            cooldown_hours=24,
            ack_only_cooldown_hours=6,
            response_timeout_seconds=20,
        ),
        now_provider=lambda: datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC),
    )

    assert service.run_cycle() is None
    service.enable()
    assert service.run_cycle() is None
    assert collector.calls == []
    assert repo.list_recent_traceroute_attempts() == []


def test_autotrace_service_includes_direct_zero_hop_nodes(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    upsert_node(repo, node_num=101, short_name="LOCAL", last_heard_at="2026-03-30T12:00:00Z", hops_away=None, via_mqtt=False)
    upsert_node(repo, node_num=202, short_name="DIRECT", last_heard_at="2026-03-30T11:59:00Z", hops_away=0, via_mqtt=False)
    collector = FakeCollector(
        TraceRouteResult(
            status="success",
            request_mesh_packet_id=77,
            response_mesh_packet_id=88,
            detail=None,
        )
    )
    now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC)
    service = AutoTracerouteService(
        repository=repo,
        collector=collector,
        local_node_num_getter=lambda: 101,
        config=AutoTracerouteConfig(
            interval_seconds=300,
            target_window_hours=24,
            cooldown_hours=24,
            ack_only_cooldown_hours=6,
            response_timeout_seconds=20,
        ),
        now_provider=lambda: now,
    )

    service.enable()
    attempt = service.run_cycle()

    assert collector.calls == [(202, 1, 0, 20)]
    assert attempt is not None
    assert attempt["target_node_num"] == 202


def test_autotrace_service_retries_ack_only_after_shorter_cooldown(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    upsert_node(repo, node_num=101, short_name="LOCAL", last_heard_at="2026-03-30T12:00:00Z", hops_away=None, via_mqtt=False)
    upsert_node(repo, node_num=202, short_name="BETA", last_heard_at="2026-03-30T11:59:00Z", hops_away=3, via_mqtt=False)
    collector = FakeCollector(
        TraceRouteResult(
            status="ack_only",
            request_mesh_packet_id=77,
            response_mesh_packet_id=88,
            detail="Routing ACK did not include a route",
        )
    )
    first_now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC)
    service = AutoTracerouteService(
        repository=repo,
        collector=collector,
        local_node_num_getter=lambda: 101,
        config=AutoTracerouteConfig(
            interval_seconds=300,
            target_window_hours=24,
            cooldown_hours=24,
            ack_only_cooldown_hours=6,
            response_timeout_seconds=20,
        ),
        now_provider=lambda: first_now,
    )

    service.enable()
    first = service.run_cycle()
    assert first is not None
    assert first["status"] == "ack_only"

    service._now_provider = lambda: datetime(2026, 3, 30, 18, 30, 0, tzinfo=UTC)
    second = service.run_cycle()

    assert second is not None
    assert second["status"] == "ack_only"
    assert len(collector.calls) == 2


def test_autotrace_service_increases_ack_only_backoff_per_streak(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    upsert_node(repo, node_num=101, short_name="LOCAL", last_heard_at="2026-03-30T12:00:00Z", hops_away=None, via_mqtt=False)
    upsert_node(repo, node_num=202, short_name="BETA", last_heard_at="2026-03-30T11:59:00Z", hops_away=3, via_mqtt=False)
    collector = FakeCollector(
        TraceRouteResult(
            status="ack_only",
            request_mesh_packet_id=77,
            response_mesh_packet_id=88,
            detail="Routing ACK did not include a route",
        )
    )
    now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC)
    service = AutoTracerouteService(
        repository=repo,
        collector=collector,
        local_node_num_getter=lambda: 101,
        config=AutoTracerouteConfig(
            interval_seconds=300,
            target_window_hours=24,
            cooldown_hours=24,
            ack_only_cooldown_hours=6,
            response_timeout_seconds=20,
        ),
        now_provider=lambda: now,
    )

    service.enable()
    assert service.run_cycle() is not None

    service._now_provider = lambda: datetime(2026, 3, 30, 18, 30, 0, tzinfo=UTC)
    assert service.run_cycle() is not None

    service._now_provider = lambda: datetime(2026, 3, 30, 23, 0, 0, tzinfo=UTC)
    assert service.run_cycle() is None

    service._now_provider = lambda: datetime(2026, 3, 31, 6, 31, 0, tzinfo=UTC)
    assert service.run_cycle() is not None
    assert len(collector.calls) == 3
