import importlib


def test_run_uses_uvicorn_with_env(monkeypatch):
    monkeypatch.setenv("MESHRADAR_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("MESHRADAR_BIND_PORT", "9100")

    import meshradar.main as main

    main = importlib.reload(main)
    called = {}

    def fake_run(app, host, port):
        called["app"] = app
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr(main.uvicorn, "run", fake_run)

    built_app = main.build_app()
    main.run()

    assert built_app.title == "Meshradar"
    assert called["app"] is main.app
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 9100

