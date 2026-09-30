from meshseer.audit import request_source


def test_request_source_prefers_forwarded_headers_from_loopback_proxy():
    source = request_source(
        {
            "x-forwarded-for": "203.0.113.10, 127.0.0.1",
            "x-real-ip": "198.51.100.10",
        },
        "127.0.0.1",
    )

    assert source == "203.0.113.10"


def test_request_source_ignores_forwarded_headers_from_non_loopback_client():
    source = request_source(
        {
            "x-forwarded-for": "203.0.113.10",
            "x-real-ip": "198.51.100.10",
        },
        "198.51.100.77",
    )

    assert source == "198.51.100.77"
