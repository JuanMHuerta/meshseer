import importlib


def test_run_uses_uvicorn_with_env(monkeypatch):
    monkeypatch.setenv("MESHSEER_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("MESHSEER_BIND_PORT", "9100")

    import meshseer.main as main

    main = importlib.reload(main)
    called = {}

    def fake_run(app, **kwargs):
        called["app"] = app
        called.update(kwargs)

    monkeypatch.setattr(main.uvicorn, "run", fake_run)

    built_app = main.build_app()
    main.run()

    assert built_app.title == "Meshseer"
    assert built_app.docs_url == "/docs"
    assert built_app.redoc_url == "/redoc"
    assert built_app.openapi_url == "/openapi.json"
    assert called["app"] is main.app
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 9100
    assert called["ws_ping_interval"] == 20.0
    assert called["ws_ping_timeout"] == 20.0


def test_build_app_disables_docs_in_production(monkeypatch):
    monkeypatch.setenv("MESHSEER_ENV", "production")

    import meshseer.main as main

    main = importlib.reload(main)
    built_app = main.build_app()

    assert built_app.docs_url is None
    assert built_app.redoc_url is None
    assert built_app.openapi_url is None
