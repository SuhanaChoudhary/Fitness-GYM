"""Core domain logic for ACEest Fitness & Gym.

This module is intentionally free of Flask and database imports so that the
business rules can be unit tested in isolation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

# Calorie factor is kcal per kg of body weight per day for the given program.
PROGRAMS: Dict[str, Dict[str, Any]] = {
    "FL3": {
        "name": "Fat Loss - 3 Day",
        "goal": "fat_loss",
        "level": "beginner",
        "factor": 22,
        "description": "3-day full-body circuit focused on a calorie deficit.",
        "workout": [
            "Mon: Full body circuit - squat, push-up, row (3 rounds)",
            "Wed: 30 min steady state cardio + core",
            "Fri: Kettlebell complex + 15 min intervals",
        ],
        "diet": "High protein, moderate carbs. 3 meals + 1 snack.",
    },
    "FL5": {
        "name": "Fat Loss - 5 Day",
        "goal": "fat_loss",
        "level": "advanced",
        "factor": 24,
        "description": "5-day split with higher training volume for fat loss.",
        "workout": [
            "Mon: Lower body strength",
            "Tue: Upper body push + HIIT finisher",
            "Wed: Assault bike EMOM 20 min",
            "Thu: Upper body pull",
            "Fri: Metabolic conditioning (10 rounds for time)",
        ],
        "diet": "Carb cycling around training days. 4 meals.",
    },
    "MG_PPL": {
        "name": "Muscle Gain - Push/Pull/Legs",
        "goal": "muscle_gain",
        "level": "intermediate",
        "factor": 35,
        "description": "Hypertrophy focused push/pull/legs split in a surplus.",
        "workout": [
            "Mon: Push - bench 5x5, overhead press, triceps",
            "Tue: Pull - deadlift 4x6, rows, biceps",
            "Thu: Legs - back squat 5x5, lunges, calves",
            "Fri: Push accessory volume",
            "Sat: Pull accessory volume",
        ],
        "diet": "Calorie surplus, 1.8 g protein per kg body weight.",
    },
    "BG": {
        "name": "Beginner Foundation",
        "goal": "general",
        "level": "beginner",
        "factor": 26,
        "description": "Technique first, 3 sessions per week full body.",
        "workout": [
            "Mon: Air squats, ring rows, push-ups (technique)",
            "Wed: Goblet squat, dumbbell press, plank",
            "Fri: Mobility, light strength, 20 min walk",
        ],
        "diet": "Balanced plate: protein, complex carbs, vegetables.",
    },
}

VALID_GOALS = sorted({program["goal"] for program in PROGRAMS.values()})
MEMBERSHIP_EXPIRY_WARNING_DAYS = 14


class ValidationError(ValueError):
    """Raised when user supplied data fails a business rule."""


def list_programs() -> List[Dict[str, Any]]:
    """Return all programs as a serialisable list."""
    return [dict(code=code, **details) for code, details in PROGRAMS.items()]


def get_program(code: str) -> Dict[str, Any]:
    """Return a single program definition.

    Raises:
        ValidationError: if the program code is unknown.
    """
    if code not in PROGRAMS:
        raise ValidationError(f"Unknown program code: {code}")
    return dict(code=code, **PROGRAMS[code])


def calculate_calories(weight_kg: float, program_code: str) -> int:
    """Return the daily calorie target for a client on a given program."""
    if weight_kg is None or weight_kg <= 0:
        raise ValidationError("Weight must be greater than zero")
    if weight_kg > 500:
        raise ValidationError("Weight must be a realistic value in kilograms")
    return int(round(weight_kg * get_program(program_code)["factor"]))


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """Return the Body Mass Index rounded to one decimal place."""
    if not weight_kg or weight_kg <= 0:
        raise ValidationError("Weight must be greater than zero")
    if not height_cm or height_cm <= 0:
        raise ValidationError("Height must be greater than zero")
    height_m = height_cm / 100
    return round(weight_kg / (height_m * height_m), 1)


def bmi_category(bmi: float) -> str:
    """Map a BMI value to its standard WHO classification."""
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25:
        return "Normal"
    if bmi < 30:
        return "Overweight"
    return "Obese"


def recommend_program(goal: str, level: str = "beginner") -> Dict[str, Any]:
    """Deterministically select the best matching program for a client.

    Falls back to the beginner foundation program when nothing matches so the
    caller always receives a usable plan.
    """
    goal = (goal or "").strip().lower()
    level = (level or "beginner").strip().lower()

    exact = [
        code
        for code, program in PROGRAMS.items()
        if program["goal"] == goal and program["level"] == level
    ]
    if exact:
        return get_program(exact[0])

    by_goal = [code for code, program in PROGRAMS.items() if program["goal"] == goal]
    if by_goal:
        return get_program(by_goal[0])

    return get_program("BG")


def average_adherence(entries: Iterable[Dict[str, Any]]) -> float:
    """Return the mean adherence percentage for the supplied progress entries."""
    values = [entry["adherence"] for entry in entries]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def validate_adherence(value: Any) -> int:
    """Validate and normalise a weekly adherence percentage."""
    try:
        adherence = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Adherence must be a whole number") from exc
    if not 0 <= adherence <= 100:
        raise ValidationError("Adherence must be between 0 and 100")
    return adherence


def parse_date(value: str, field: str = "date") -> date:
    """Parse an ISO formatted (YYYY-MM-DD) date string."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must use the YYYY-MM-DD format") from exc


def membership_status(end_date: Optional[str], today: Optional[date] = None) -> Dict[str, Any]:
    """Return the membership state derived from its end date."""
    today = today or date.today()
    if not end_date:
        return {"status": "Inactive", "days_left": None, "end_date": None}

    expiry = parse_date(end_date, "membership_end")
    days_left = (expiry - today).days
    if days_left < 0:
        status = "Expired"
    elif days_left <= MEMBERSHIP_EXPIRY_WARNING_DAYS:
        status = "Expiring Soon"
    else:
        status = "Active"
    return {"status": status, "days_left": days_left, "end_date": expiry.isoformat()}


def default_membership_end(start: Optional[date] = None, months: int = 12) -> str:
    """Return the default membership end date as an ISO string."""
    start = start or date.today()
    return (start + timedelta(days=30 * months)).isoformat()


def build_client_summary(
    client: Dict[str, Any],
    progress: Iterable[Dict[str, Any]],
    workouts: Iterable[Dict[str, Any]],
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Aggregate a client record into the payload rendered by the dashboard."""
    progress = list(progress)
    workouts = list(workouts)
    program = get_program(client["program"])
    summary: Dict[str, Any] = {
        "name": client["name"],
        "age": client["age"],
        "height_cm": client["height_cm"],
        "weight_kg": client["weight_kg"],
        "program": program,
        "calories": client["calories"],
        "target_weight_kg": client["target_weight_kg"],
        "target_adherence": client["target_adherence"],
        "membership": membership_status(client.get("membership_end"), today=today),
        "weeks_logged": len(progress),
        "average_adherence": average_adherence(progress),
        "total_workouts": len(workouts),
        "total_minutes": sum(workout["duration_min"] for workout in workouts),
    }

    if client["height_cm"] and client["weight_kg"]:
        bmi = calculate_bmi(client["weight_kg"], client["height_cm"])
        summary["bmi"] = bmi
        summary["bmi_category"] = bmi_category(bmi)
    else:
        summary["bmi"] = None
        summary["bmi_category"] = None

    if client["target_weight_kg"] and client["weight_kg"]:
        summary["weight_delta_kg"] = round(
            client["weight_kg"] - client["target_weight_kg"], 1
        )
    else:
        summary["weight_delta_kg"] = None

    target = client["target_adherence"]
    summary["on_track"] = bool(
        target and progress and summary["average_adherence"] >= target
    )
    return summary
