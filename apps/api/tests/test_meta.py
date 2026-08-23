"""Demo mode is the honesty switch — it decides whether the whole interface warns."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from catalyst.config import Settings, get_settings
from catalyst.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _settings(providers: tuple[str, ...]) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused/unused",
        redis_url="redis://unused",
        cors_origins=("http://localhost:3000",),
        providers=providers,
    )


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mock_provider_forces_demo_mode() -> None:
    assert _settings(("mock",)).demo_mode is True


def test_real_providers_do_not_set_demo_mode() -> None:
    assert _settings(("esm2_650m", "thermompnn")).demo_mode is False


def test_demo_mode_is_set_when_mock_is_mixed_with_real_providers() -> None:
    """One fabricating provider is enough. If any number on screen could be
    synthetic, the banner shows."""
    assert _settings(("esm2_650m", "mock")).demo_mode is True


def test_meta_endpoint_reports_demo_mode(client: TestClient) -> None:
    get_settings.cache_clear()
    response = client.get("/meta")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "demo_mode",
        "providers",
        "predictors",
        "supported_objectives",
        "unknown_providers",
        "objective_support",
        "queue",
    }
    assert isinstance(body["demo_mode"], bool)


def test_meta_demo_flag_is_derived_from_the_predictors_not_the_string() -> None:
    """The two answers must agree, and only one of them can be trusted.

    ``Settings.demo_mode`` reads a string out of the environment. The service
    reads ``is_mock`` off the predictors that are actually loaded. They agree
    today; the moment they could not, the interface would be showing numbers a
    mock produced with no banner over them.
    """
    from catalyst.services import providers as provider_service

    settings = _settings(("mock",))
    assert settings.demo_mode is True
    assert provider_service.demo_mode(settings) is True

    real_only = _settings(("esm2_650m",))
    # An id that matches no predictor must not silently read as "no mocks, all
    # clear" — it is reported, and a run started against it is refused.
    assert provider_service.demo_mode(real_only) is False
    assert provider_service.unknown_ids(real_only) == ["esm2_650m"]


def test_meta_describes_every_active_predictor(client: TestClient) -> None:
    """The interface varies by model from this payload and never by naming one."""
    get_settings.cache_clear()
    body = client.get("/meta").json()
    assert body["predictors"], "the shipped configuration must load at least one predictor"

    for predictor in body["predictors"]:
        assert set(predictor) >= {
            "id",
            "name",
            "version",
            "weights_hash",
            "modality",
            "citation",
            "is_mock",
            "objectives",
            "requires",
            "metrics",
        }
        for metric in predictor["metrics"]:
            # Specification §7: the sign convention is stated in the column
            # header and never changes, so it travels with the metric.
            assert metric["sign_convention"]


def test_meta_never_claims_support_for_an_unnamed_objective(client: TestClient) -> None:
    """`other` is the bucket for an objective the parser could not name. No
    provider can support what has not been named."""
    get_settings.cache_clear()
    body = client.get("/meta").json()
    assert "other" not in body["supported_objectives"]
