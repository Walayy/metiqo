from fastapi.testclient import TestClient
from metiquo_api.auth_config import AuthSettings
from metiquo_api.main import create_app
from metiquo_core.config import Settings
from sqlalchemy.exc import OperationalError


def test_unexpected_and_database_errors_have_safe_responses_and_recovery_headers():
    app = create_app(
        Settings(database_url="postgresql+psycopg://test:test@127.0.0.1:1/errors_test"),
        AuthSettings(auth_secret="isolated-error-test-key-with-32-characters"),
    )

    @app.get("/api/v1/auth/test-unexpected")
    def unexpected():
        raise RuntimeError("private-credential-must-not-be-returned")

    @app.get("/api/v1/admin/test-database")
    def database():
        raise OperationalError("private SQL", {}, Exception("private connection string"))

    with TestClient(app, raise_server_exceptions=False) as client:
        error = client.get("/api/v1/auth/test-unexpected")
        assert error.status_code == 500
        assert error.headers["cache-control"] == "no-store"
        assert "private" not in error.text
        assert isinstance(error.json()["detail"], str)
        unavailable = client.get("/api/v1/admin/test-database")
        assert unavailable.status_code == 503
        assert unavailable.headers["retry-after"] == "30"
        assert unavailable.headers["cache-control"] == "no-store"
        assert "private" not in unavailable.text
        assert client.get("/api/v1/unknown").status_code == 404
