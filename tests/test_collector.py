import sys
import threading
import time
import types

from meshseer.collector import CollectorCallbacks, CollectorStatus, MeshtasticReceiver
from meshseer.normalizers import normalize_node, normalize_packet


class FakePubSub:
    def __init__(self):
        self._subs = {}

    def subscribe(self, callback, topic):
        self._subs.setdefault(topic, []).append(callback)

    def send_message(self, topic, **kwargs):
        for callback in self._subs.get(topic, []):
            callback(**kwargs)


class FakeInterface:
    def __init__(self, *, my_node_num=None, send_data=None):
        self.closed = False
        self._send_data = send_data
        self.sent_packets = []
        if my_node_num is not None:
            self.myInfo = types.SimpleNamespace(my_node_num=my_node_num)

    def close(self):
        self.closed = True

    def sendText(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("sendText must never be called")

    def sendData(self, *args, **kwargs):
        if self._send_data is None:  # pragma: no cover
            raise AssertionError("sendData must never be called")
        self.sent_packets.append((args, kwargs))
        return self._send_data(*args, **kwargs)

    def getNode(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("getNode must never be called")

    @property
    def localNode(self):  # pragma: no cover
        raise AssertionError("localNode must never be used")


def test_receiver_connects_and_processes_events():
    pubsub = FakePubSub()
    packets = []
    nodes = []
    statuses = []
    fake_interface = FakeInterface()

    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=packets.append,
            on_node=nodes.append,
            on_status=statuses.append,
        ),
        interface_factory=lambda host, port: fake_interface,
        pubsub=pubsub,
        sleeper=lambda seconds: None,
    )

    receiver.connect_once()
    pubsub.send_message(
        "meshtastic.receive",
        packet={
            "id": 9,
            "from": 101,
            "to": 202,
            "channel": 0,
            "hopLimit": 3,
            "rxSnr": 7.5,
            "rxTime": 1_743_336_000,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "hello"},
        },
        interface=fake_interface,
    )
    pubsub.send_message(
        "meshtastic.node.updated",
        node={
            "num": 101,
            "user": {
                "id": "!00000065",
                "shortName": "ALFA",
                "longName": "Alpha",
                "hwModel": "TBEAM",
                "role": "CLIENT",
            },
            "position": {"latitude": 10.25, "longitude": -84.1, "altitude": 15},
            "lastHeard": 1_743_336_000,
            "snr": 7.5,
        },
    )

    assert packets == [normalize_packet({"id": 9, "from": 101, "to": 202, "channel": 0, "hopLimit": 3, "rxSnr": 7.5, "rxTime": 1_743_336_000, "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "hello"}})]
    assert nodes == [normalize_node({"num": 101, "user": {"id": "!00000065", "shortName": "ALFA", "longName": "Alpha", "hwModel": "TBEAM", "role": "CLIENT"}, "position": {"latitude": 10.25, "longitude": -84.1, "altitude": 15}, "lastHeard": 1_743_336_000, "snr": 7.5})]
    assert statuses[0].state == "connecting"
    assert statuses[-1].state == "connected"
    assert fake_interface.closed is False


def test_receiver_retries_with_bounded_backoff():
    pubsub = FakePubSub()
    statuses = []
    sleeps = []
    attempts = {"count": 0}

    def factory(host, port):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError(f"boom-{attempts['count']}")
        return FakeInterface()

    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=lambda packet: None,
            on_node=lambda node: None,
            on_status=statuses.append,
        ),
        interface_factory=factory,
        pubsub=pubsub,
        sleeper=sleeps.append,
    )

    interface = receiver.connect_with_retry(max_attempts=3)

    assert interface is not None
    assert sleeps == [1.0, 2.0]
    assert statuses[1] == CollectorStatus(state="disconnected", connected=False, detail="boom-1")
    assert statuses[3] == CollectorStatus(state="disconnected", connected=False, detail="boom-2")


def test_receiver_ignores_foreign_interface_and_marks_connection_lost():
    pubsub = FakePubSub()
    packets = []
    statuses = []
    fake_interface = FakeInterface()

    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=packets.append,
            on_node=lambda node: None,
            on_status=statuses.append,
        ),
        interface_factory=lambda host, port: fake_interface,
        pubsub=pubsub,
        sleeper=lambda seconds: None,
    )

    receiver.connect_once()
    receiver._handle_packet({"id": 1, "decoded": {"portnum": "TEXT_MESSAGE_APP"}}, interface=FakeInterface())
    receiver._handle_connection_established(interface=FakeInterface())
    receiver._handle_connection_lost(interface=FakeInterface())

    assert packets == []
    assert receiver.current_status() == CollectorStatus(state="connected", connected=True, detail=None)

    receiver._handle_connection_lost(interface=fake_interface)

    assert receiver.current_status() == CollectorStatus(state="disconnected", connected=False, detail="connection lost")


def test_receiver_accepts_node_update_with_interface_kwarg():
    pubsub = FakePubSub()
    nodes = []
    active_interface = FakeInterface()
    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=lambda packet: None,
            on_node=nodes.append,
            on_status=lambda status: None,
        ),
        interface_factory=lambda host, port: active_interface,
        pubsub=pubsub,
        sleeper=lambda seconds: None,
    )

    receiver.connect_once()
    receiver._handle_node(
            {
                "num": 1,
                "user": {"id": "!00000001", "shortName": "A"},
            },
            interface=active_interface,
        )

    assert nodes[0]["node_num"] == 1


def test_receiver_exposes_local_node_num_from_interface_metadata():
    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=lambda packet: None,
            on_node=lambda node: None,
            on_status=lambda status: None,
        ),
        interface_factory=lambda host, port: FakeInterface(my_node_num=101),
        pubsub=FakePubSub(),
        sleeper=lambda seconds: None,
    )

    receiver.connect_once()

    assert receiver.local_node_num() == 101


def test_receiver_trace_route_returns_success_for_traceroute_response():
    def send_data(*args, **kwargs):
        kwargs["onResponse"](
            {
                "id": 41,
                "from": 202,
                "to": 101,
                "channel": 0,
                "hopLimit": 3,
                "hopStart": 3,
                "rxTime": 1_743_336_120,
                "decoded": {
                    "portnum": "TRACEROUTE_APP",
                    "payload": b"\x00",
                },
            }
        )
        return types.SimpleNamespace(id=77)

    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=lambda packet: None,
            on_node=lambda node: None,
            on_status=lambda status: None,
        ),
        interface_factory=lambda host, port: FakeInterface(my_node_num=101, send_data=send_data),
        pubsub=FakePubSub(),
        sleeper=lambda seconds: None,
    )

    receiver.connect_once()
    result = receiver.trace_route(202, hop_limit=3, timeout_seconds=0)

    assert result.status == "success"
    assert result.request_mesh_packet_id == 77
    assert result.response_mesh_packet_id == 41
    assert result.detail is None


def test_receiver_trace_route_returns_ack_only_for_routing_ack():
    def send_data(*args, **kwargs):
        kwargs["onResponse"](
            {
                "id": 42,
                "from": 202,
                "to": 101,
                "channel": 0,
                "rxTime": 1_743_336_121,
                "decoded": {
                    "portnum": "ROUTING_APP",
                    "routing": {"errorReason": "NONE"},
                    "payload": b"\x00",
                },
            }
        )
        return types.SimpleNamespace(id=78)

    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=lambda packet: None,
            on_node=lambda node: None,
            on_status=lambda status: None,
        ),
        interface_factory=lambda host, port: FakeInterface(my_node_num=101, send_data=send_data),
        pubsub=FakePubSub(),
        sleeper=lambda seconds: None,
    )

    receiver.connect_once()
    result = receiver.trace_route(202, hop_limit=3, timeout_seconds=0)

    assert result.status == "ack_only"
    assert result.request_mesh_packet_id == 78
    assert result.response_mesh_packet_id == 42
    assert result.detail == "Routing ACK did not include a route"


def test_receiver_trace_route_times_out_without_response():
    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=lambda packet: None,
            on_node=lambda node: None,
            on_status=lambda status: None,
        ),
        interface_factory=lambda host, port: FakeInterface(
            my_node_num=101,
            send_data=lambda *args, **kwargs: types.SimpleNamespace(id=79),
        ),
        pubsub=FakePubSub(),
        sleeper=lambda seconds: None,
    )

    receiver.connect_once()
    result = receiver.trace_route(202, hop_limit=3, timeout_seconds=0)

    assert result.status == "timeout"
    assert result.request_mesh_packet_id == 79
    assert result.response_mesh_packet_id is None
    assert result.detail == "Timed out waiting for traceroute response"


def test_receiver_start_stop_reconnects_and_closes_interfaces():
    pubsub = FakePubSub()
    statuses = []
    created = []
    reconnect_seen = threading.Event()

    def factory(host, port):
        interface = FakeInterface()
        created.append(interface)
        if len(created) == 2:
            reconnect_seen.set()
        return interface

    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=lambda packet: None,
            on_node=lambda node: None,
            on_status=statuses.append,
        ),
        interface_factory=factory,
        pubsub=pubsub,
        sleeper=lambda seconds: None,
    )

    receiver.start()

    deadline = time.monotonic() + 1.5
    while len(created) < 1 and time.monotonic() < deadline:
        time.sleep(0.01)

    receiver._handle_connection_lost(interface=created[0])
    assert reconnect_seen.wait(1.5)

    receiver.stop()

    assert created[0].closed is True
    assert created[-1].closed is True
    assert any(status.state == "connected" for status in statuses)
    assert any(status.state == "disconnected" for status in statuses)


def test_receiver_uses_default_imports_when_modules_are_available(monkeypatch):
    fake_pub = FakePubSub()
    fake_interface = FakeInterface()
    pubsub_module = types.SimpleNamespace(pub=fake_pub)

    class FakeTCPInterface:
        def __new__(cls, hostname, portNumber):
            fake_interface.host = hostname
            fake_interface.port = portNumber
            return fake_interface

    tcp_module = types.SimpleNamespace(TCPInterface=FakeTCPInterface)
    meshtastic_module = types.SimpleNamespace(tcp_interface=tcp_module)

    monkeypatch.setitem(sys.modules, "pubsub", pubsub_module)
    monkeypatch.setitem(sys.modules, "meshtastic", meshtastic_module)
    monkeypatch.setitem(sys.modules, "meshtastic.tcp_interface", tcp_module)

    receiver = MeshtasticReceiver(
        host="mesh.local",
        port=4403,
        callbacks=CollectorCallbacks(
            on_packet=lambda packet: None,
            on_node=lambda node: None,
            on_status=lambda status: None,
        ),
    )

    interface = receiver.connect_once()
    receiver.stop()

    assert interface is fake_interface
    assert fake_interface.host == "mesh.local"
    assert fake_interface.port == 4403
