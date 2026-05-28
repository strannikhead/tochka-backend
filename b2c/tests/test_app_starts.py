from b2c.src.main import app


def test_app_starts() -> None:
    assert len(app.routes) > 0
