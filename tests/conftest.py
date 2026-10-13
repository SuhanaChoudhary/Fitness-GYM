"""Shared Pytest fixtures for the ACEest Fitness test suite."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

TEST_USER = "admin"
TEST_PASSWORD = "test-password"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Flask app bound to an isolated SQLite database per test."""
    monkeypatch.setenv("ACEEST_ADMIN_USER", TEST_USER)
    monkeypatch.setenv("ACEEST_ADMIN_PASSWORD", TEST_PASSWORD)
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.db"),
            "SECRET_KEY": "test-secret-key",
        }
    )
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_client(client):
    """Test client with an authenticated session."""
    response = client.post(
        "/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return client


@pytest.fixture()
def saved_client(auth_client):
    """An authenticated client with one persisted gym member."""
    response = auth_client.post(
        "/api/clients",
        json={
            "name": "Ravi Kumar",
            "age": 29,
            "height_cm": 175,
            "weight_kg": 80,
            "program": "FL3",
            "target_weight_kg": 72,
            "target_adherence": 80,
            "membership_end": "2099-12-31",
        },
    )
    assert response.status_code == 201
    return auth_client
