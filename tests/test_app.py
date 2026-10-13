"""Integration tests for the Flask routes and JSON API."""

from __future__ import annotations

import pytest

PROTECTED_API_ROUTES = [
    "/api/clients",
    "/api/programs",
    "/api/clients/Ravi%20Kumar",
    "/api/clients/Ravi%20Kumar/progress",
    "/api/clients/Ravi%20Kumar/workouts",
]


class TestHealthAndRouting:
    def test_health_endpoint_is_public(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["status"] == "healthy"

    def test_root_redirects_anonymous_user_to_login(self, client):
        response = client.get("/")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_login_page_renders(self, client):
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Trainer Login" in response.data

    def test_unknown_api_route_returns_json_404(self, auth_client):
        response = auth_client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.get_json()["error"] == "Resource not found"


class TestAuthentication:
    def test_login_with_valid_credentials(self, client):
        response = client.post(
            "/login", json={"username": "admin", "password": "test-password"}
        )
        assert response.status_code == 200
        assert response.get_json()["role"] == "Admin"

    def test_login_with_invalid_credentials(self, client):
        response = client.post("/login", json={"username": "admin", "password": "wrong"})
        assert response.status_code == 401
        assert response.get_json()["error"] == "Invalid credentials"

    @pytest.mark.parametrize("route", PROTECTED_API_ROUTES)
    def test_api_routes_require_authentication(self, client, route):
        response = client.get(route)
        assert response.status_code == 401
        assert response.get_json()["error"] == "Authentication required"

    def test_dashboard_requires_authentication(self, client):
        response = client.get("/dashboard")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_dashboard_renders_for_authenticated_user(self, auth_client):
        response = auth_client.get("/dashboard")
        assert response.status_code == 200
        assert b"Client profile" in response.data

    def test_logout_clears_the_session(self, auth_client):
        auth_client.get("/logout")
        assert auth_client.get("/dashboard").status_code == 302


class TestClientManagement:
    def test_save_client_calculates_calories(self, auth_client):
        response = auth_client.post(
            "/api/clients",
            json={"name": "Ravi Kumar", "weight_kg": 80, "program": "FL3"},
        )
        assert response.status_code == 201
        client_record = response.get_json()["client"]
        assert client_record["calories"] == 1760
        assert client_record["program"] == "FL3"

    def test_save_client_requires_a_name(self, auth_client):
        response = auth_client.post("/api/clients", json={"program": "FL3"})
        assert response.status_code == 400
        assert "name" in response.get_json()["error"].lower()

    def test_save_client_rejects_unknown_program(self, auth_client):
        response = auth_client.post(
            "/api/clients", json={"name": "Test", "program": "INVALID"}
        )
        assert response.status_code == 400

    def test_saving_the_same_name_updates_the_record(self, saved_client):
        saved_client.post(
            "/api/clients",
            json={"name": "Ravi Kumar", "weight_kg": 75, "program": "MG_PPL"},
        )
        clients = saved_client.get("/api/clients").get_json()["clients"]
        assert len(clients) == 1
        assert clients[0]["program"] == "MG_PPL"
        assert clients[0]["calories"] == 2625

    def test_get_client_returns_summary(self, saved_client):
        payload = saved_client.get("/api/clients/Ravi Kumar").get_json()
        assert payload["client"]["name"] == "Ravi Kumar"
        assert payload["summary"]["bmi"] == 26.1
        assert payload["summary"]["membership"]["status"] == "Active"

    def test_get_missing_client_returns_404(self, auth_client):
        assert auth_client.get("/api/clients/Ghost").status_code == 404

    def test_delete_client(self, saved_client):
        assert saved_client.delete("/api/clients/Ravi Kumar").status_code == 200
        assert saved_client.get("/api/clients").get_json()["clients"] == []


class TestProgramGeneration:
    def test_generate_program_updates_client(self, saved_client):
        response = saved_client.post(
            "/api/clients/Ravi Kumar/program",
            json={"goal": "muscle_gain", "level": "intermediate"},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["program"]["code"] == "MG_PPL"
        assert body["calories"] == 2800

        stored = saved_client.get("/api/clients/Ravi Kumar").get_json()["client"]
        assert stored["program"] == "MG_PPL"

    def test_generate_program_for_missing_client(self, auth_client):
        response = auth_client.post("/api/clients/Ghost/program", json={"goal": "general"})
        assert response.status_code == 404

    def test_programs_catalogue_is_available(self, auth_client):
        programs = auth_client.get("/api/programs").get_json()["programs"]
        assert any(program["code"] == "FL5" for program in programs)


class TestProgressTracking:
    def test_record_and_list_progress(self, saved_client):
        for week, adherence in (("2026-W01", 70), ("2026-W02", 90)):
            response = saved_client.post(
                "/api/clients/Ravi Kumar/progress",
                json={"week": week, "adherence": adherence},
            )
            assert response.status_code == 201

        payload = saved_client.get("/api/clients/Ravi Kumar/progress").get_json()
        assert len(payload["progress"]) == 2
        assert payload["average_adherence"] == 80.0

    @pytest.mark.parametrize("adherence", [-10, 150, "high"])
    def test_invalid_adherence_is_rejected(self, saved_client, adherence):
        response = saved_client.post(
            "/api/clients/Ravi Kumar/progress",
            json={"week": "2026-W03", "adherence": adherence},
        )
        assert response.status_code == 400

    def test_progress_requires_a_week_label(self, saved_client):
        response = saved_client.post(
            "/api/clients/Ravi Kumar/progress", json={"adherence": 80}
        )
        assert response.status_code == 400


class TestWorkoutLogging:
    def test_log_and_list_workouts(self, saved_client):
        response = saved_client.post(
            "/api/clients/Ravi Kumar/workouts",
            json={
                "date": "2026-02-10",
                "workout_type": "Strength",
                "duration_min": 60,
                "notes": "Squat 5x5",
            },
        )
        assert response.status_code == 201

        workouts = saved_client.get("/api/clients/Ravi Kumar/workouts").get_json()["workouts"]
        assert len(workouts) == 1
        assert workouts[0]["workout_type"] == "Strength"

    def test_invalid_workout_type_is_rejected(self, saved_client):
        response = saved_client.post(
            "/api/clients/Ravi Kumar/workouts",
            json={"workout_type": "Yoga Flow", "duration_min": 45},
        )
        assert response.status_code == 400

    def test_invalid_duration_is_rejected(self, saved_client):
        response = saved_client.post(
            "/api/clients/Ravi Kumar/workouts",
            json={"workout_type": "Cardio", "duration_min": 0},
        )
        assert response.status_code == 400


class TestMembershipAndReporting:
    def test_membership_endpoint(self, saved_client):
        payload = saved_client.get("/api/clients/Ravi Kumar/membership").get_json()
        assert payload["membership"]["status"] == "Active"

    def test_report_contains_summary_progress_and_workouts(self, saved_client):
        saved_client.post(
            "/api/clients/Ravi Kumar/progress", json={"week": "2026-W01", "adherence": 85}
        )
        saved_client.post(
            "/api/clients/Ravi Kumar/workouts",
            json={"workout_type": "Cardio", "duration_min": 30},
        )
        report = saved_client.get("/api/clients/Ravi Kumar/report").get_json()
        assert report["summary"]["average_adherence"] == 85.0
        assert len(report["progress"]) == 1
        assert len(report["workouts"]) == 1
