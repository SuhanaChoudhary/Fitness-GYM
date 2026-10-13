"""ACEest Fitness & Gym - Flask application.

Exposes an HTML dashboard plus a JSON API used by the dashboard and by the
automated Pytest suite.
"""

from __future__ import annotations

import os
from datetime import date
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import fitness
import models

APP_VERSION = "1.0.0"


def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    """Application factory used by gunicorn, the CLI and the test suite."""
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("ACEEST_SECRET_KEY", os.urandom(32).hex()),
        DATABASE=os.environ.get("ACEEST_DB_PATH", os.path.join(app.root_path, "aceest_fitness.db")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("ACEEST_COOKIE_SECURE", "0") == "1",
        JSON_SORT_KEYS=False,
    )
    if config:
        app.config.update(config)

    app.teardown_appcontext(models.close_db)
    register_routes(app)

    with app.app_context():
        models.init_db()

    return app


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Reject anonymous requests, answering JSON for API calls."""

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _payload() -> Dict[str, Any]:
    """Return the request body from JSON or form encoded submissions."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def _optional_number(value: Any, field: str, cast: Callable[[Any], Any]) -> Optional[Any]:
    if value in (None, "", "null"):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError) as exc:
        raise fitness.ValidationError(f"{field} must be numeric") from exc


def register_routes(app: Flask) -> None:  # noqa: C901 - route table
    @app.errorhandler(fitness.ValidationError)
    def handle_validation_error(error: fitness.ValidationError) -> Tuple[Any, int]:
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(404)
    def handle_not_found(_error: Any) -> Tuple[Any, int]:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found"}), 404
        return render_template("error.html", code=404, message="Page not found"), 404

    @app.route("/health")
    def health() -> Any:
        """Liveness probe consumed by Docker, Jenkins and GitHub Actions."""
        return jsonify({"status": "healthy", "service": "aceest-fitness", "version": APP_VERSION})

    @app.route("/")
    def index() -> Any:
        if "user" in session:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Any:
        if request.method == "POST":
            data = _payload()
            user = models.verify_user(
                (data.get("username") or "").strip(), data.get("password") or ""
            )
            if user is None:
                if request.is_json:
                    return jsonify({"error": "Invalid credentials"}), 401
                return render_template("login.html", error="Invalid credentials"), 401
            session.clear()
            session["user"] = user["username"]
            session["role"] = user["role"]
            if request.is_json:
                return jsonify({"message": "Login successful", **user})
            return redirect(url_for("dashboard"))
        if "user" in session:
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/logout", methods=["GET", "POST"])
    def logout() -> Any:
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard() -> Any:
        return render_template(
            "dashboard.html",
            user=session.get("user"),
            role=session.get("role"),
            programs=fitness.list_programs(),
            workout_types=models.WORKOUT_TYPES,
            today=date.today().isoformat(),
        )

    @app.route("/api/programs")
    @login_required
    def api_programs() -> Any:
        return jsonify({"programs": fitness.list_programs()})

    @app.route("/api/clients")
    @login_required
    def api_list_clients() -> Any:
        return jsonify({"clients": models.list_clients()})

    @app.route("/api/clients", methods=["POST"])
    @login_required
    def api_save_client() -> Any:
        data = _payload()
        name = (data.get("name") or "").strip()
        if not name:
            raise fitness.ValidationError("Client name is required")

        program_code = (data.get("program") or "").strip()
        if not program_code:
            raise fitness.ValidationError("Program is required")
        fitness.get_program(program_code)

        weight = _optional_number(data.get("weight_kg"), "weight_kg", float)
        height = _optional_number(data.get("height_cm"), "height_cm", float)
        age = _optional_number(data.get("age"), "age", int)
        target_weight = _optional_number(data.get("target_weight_kg"), "target_weight_kg", float)
        target_adherence = data.get("target_adherence")
        target_adherence = (
            fitness.validate_adherence(target_adherence)
            if target_adherence not in (None, "", "null")
            else None
        )

        calories = fitness.calculate_calories(weight, program_code) if weight else None
        membership_end = (data.get("membership_end") or "").strip() or fitness.default_membership_end()
        fitness.parse_date(membership_end, "membership_end")

        client = models.upsert_client(
            {
                "name": name,
                "age": age,
                "height_cm": height,
                "weight_kg": weight,
                "program": program_code,
                "calories": calories,
                "target_weight_kg": target_weight,
                "target_adherence": target_adherence,
                "membership_end": membership_end,
            }
        )
        return jsonify({"message": "Client saved", "client": client}), 201

    @app.route("/api/clients/<name>")
    @login_required
    def api_get_client(name: str) -> Any:
        client = models.get_client(name)
        if client is None:
            return jsonify({"error": "Client not found"}), 404
        summary = fitness.build_client_summary(
            client, models.list_progress(name), models.list_workouts(name)
        )
        return jsonify({"client": client, "summary": summary})

    @app.route("/api/clients/<name>", methods=["DELETE"])
    @login_required
    def api_delete_client(name: str) -> Any:
        if models.delete_client(name) == 0:
            return jsonify({"error": "Client not found"}), 404
        return jsonify({"message": f"Client {name} removed"})

    @app.route("/api/clients/<name>/program", methods=["POST"])
    @login_required
    def api_generate_program(name: str) -> Any:
        client = models.get_client(name)
        if client is None:
            return jsonify({"error": "Client not found"}), 404

        data = _payload()
        program = fitness.recommend_program(
            data.get("goal", ""), data.get("level", "beginner")
        )
        calories = (
            fitness.calculate_calories(client["weight_kg"], program["code"])
            if client["weight_kg"]
            else None
        )
        models.update_client_program(name, program["code"], calories)
        return jsonify({"message": "Program generated", "program": program, "calories": calories})

    @app.route("/api/clients/<name>/membership")
    @login_required
    def api_membership(name: str) -> Any:
        client = models.get_client(name)
        if client is None:
            return jsonify({"error": "Client not found"}), 404
        return jsonify({"client": name, "membership": fitness.membership_status(client["membership_end"])})

    @app.route("/api/clients/<name>/report")
    @login_required
    def api_report(name: str) -> Any:
        client = models.get_client(name)
        if client is None:
            return jsonify({"error": "Client not found"}), 404
        progress = models.list_progress(name)
        workouts = models.list_workouts(name)
        return jsonify(
            {
                "generated_on": date.today().isoformat(),
                "summary": fitness.build_client_summary(client, progress, workouts),
                "progress": progress,
                "workouts": workouts,
            }
        )

    @app.route("/api/clients/<name>/progress", methods=["GET", "POST"])
    @login_required
    def api_progress(name: str) -> Any:
        if models.get_client(name) is None:
            return jsonify({"error": "Client not found"}), 404

        if request.method == "GET":
            entries = models.list_progress(name)
            return jsonify(
                {"progress": entries, "average_adherence": fitness.average_adherence(entries)}
            )

        data = _payload()
        week = (data.get("week") or "").strip()
        if not week:
            raise fitness.ValidationError("Week label is required")
        adherence = fitness.validate_adherence(data.get("adherence"))
        entry = models.add_progress(name, week, adherence)
        return jsonify({"message": "Progress recorded", "entry": entry}), 201

    @app.route("/api/clients/<name>/workouts", methods=["GET", "POST"])
    @login_required
    def api_workouts(name: str) -> Any:
        if models.get_client(name) is None:
            return jsonify({"error": "Client not found"}), 404

        if request.method == "GET":
            return jsonify({"workouts": models.list_workouts(name)})

        data = _payload()
        workout_type = (data.get("workout_type") or "").strip()
        if workout_type not in models.WORKOUT_TYPES:
            raise fitness.ValidationError(
                f"Workout type must be one of: {', '.join(models.WORKOUT_TYPES)}"
            )
        workout_date = (data.get("date") or date.today().isoformat()).strip()
        fitness.parse_date(workout_date, "date")

        duration = _optional_number(data.get("duration_min"), "duration_min", int)
        if not duration or duration <= 0:
            raise fitness.ValidationError("Duration must be greater than zero minutes")

        workout = models.add_workout(
            name, workout_date, workout_type, duration, (data.get("notes") or "").strip()
        )
        return jsonify({"message": "Workout logged", "workout": workout}), 201


if __name__ == "__main__":
    create_app().run(
        host=os.environ.get("ACEEST_HOST", "127.0.0.1"),
        port=int(os.environ.get("ACEEST_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
