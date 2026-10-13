"""Unit tests for the pure business logic in fitness.py."""

from __future__ import annotations

from datetime import date

import pytest

import fitness


class TestPrograms:
    def test_list_programs_exposes_every_catalogue_entry(self):
        programs = fitness.list_programs()
        assert len(programs) == len(fitness.PROGRAMS)
        assert {program["code"] for program in programs} == set(fitness.PROGRAMS)

    def test_get_program_returns_definition(self):
        program = fitness.get_program("MG_PPL")
        assert program["name"] == "Muscle Gain - Push/Pull/Legs"
        assert program["factor"] == 35

    def test_get_program_rejects_unknown_code(self):
        with pytest.raises(fitness.ValidationError):
            fitness.get_program("NOPE")


class TestCalorieAndBmiCalculations:
    @pytest.mark.parametrize(
        "weight,program,expected",
        [(80, "FL3", 1760), (80, "FL5", 1920), (70, "MG_PPL", 2450), (60, "BG", 1560)],
    )
    def test_calculate_calories_uses_program_factor(self, weight, program, expected):
        assert fitness.calculate_calories(weight, program) == expected

    @pytest.mark.parametrize("weight", [0, -5, None, 900])
    def test_calculate_calories_rejects_invalid_weight(self, weight):
        with pytest.raises(fitness.ValidationError):
            fitness.calculate_calories(weight, "FL3")

    def test_calculate_bmi(self):
        assert fitness.calculate_bmi(80, 175) == 26.1

    def test_calculate_bmi_rejects_zero_height(self):
        with pytest.raises(fitness.ValidationError):
            fitness.calculate_bmi(80, 0)

    @pytest.mark.parametrize(
        "bmi,category",
        [(17.0, "Underweight"), (22.0, "Normal"), (27.5, "Overweight"), (34.0, "Obese")],
    )
    def test_bmi_category_boundaries(self, bmi, category):
        assert fitness.bmi_category(bmi) == category


class TestProgramRecommendation:
    def test_exact_goal_and_level_match(self):
        assert fitness.recommend_program("fat_loss", "advanced")["code"] == "FL5"

    def test_goal_match_when_level_is_unavailable(self):
        assert fitness.recommend_program("muscle_gain", "beginner")["code"] == "MG_PPL"

    def test_unknown_goal_falls_back_to_beginner_program(self):
        assert fitness.recommend_program("space_travel", "expert")["code"] == "BG"

    def test_recommendation_is_deterministic(self):
        first = fitness.recommend_program("fat_loss", "beginner")
        second = fitness.recommend_program("FAT_LOSS", " Beginner ")
        assert first["code"] == second["code"] == "FL3"


class TestAdherence:
    def test_average_adherence(self):
        entries = [{"adherence": 70}, {"adherence": 80}, {"adherence": 95}]
        assert fitness.average_adherence(entries) == 81.7

    def test_average_adherence_without_entries(self):
        assert fitness.average_adherence([]) == 0.0

    @pytest.mark.parametrize("value", [-1, 101, "abc", None])
    def test_validate_adherence_rejects_out_of_range(self, value):
        with pytest.raises(fitness.ValidationError):
            fitness.validate_adherence(value)

    def test_validate_adherence_accepts_string_numbers(self):
        assert fitness.validate_adherence("85") == 85


class TestMembership:
    def test_active_membership(self):
        result = fitness.membership_status("2026-12-31", today=date(2026, 1, 1))
        assert result["status"] == "Active"
        assert result["days_left"] == 364

    def test_membership_expiring_soon(self):
        result = fitness.membership_status("2026-01-10", today=date(2026, 1, 1))
        assert result["status"] == "Expiring Soon"

    def test_expired_membership(self):
        result = fitness.membership_status("2025-12-01", today=date(2026, 1, 1))
        assert result["status"] == "Expired"
        assert result["days_left"] < 0

    def test_missing_end_date_is_inactive(self):
        assert fitness.membership_status(None)["status"] == "Inactive"

    def test_invalid_date_format_is_rejected(self):
        with pytest.raises(fitness.ValidationError):
            fitness.membership_status("31-12-2026")


class TestClientSummary:
    @staticmethod
    def _client(**overrides):
        base = {
            "name": "Ravi Kumar",
            "age": 29,
            "height_cm": 175,
            "weight_kg": 80,
            "program": "FL3",
            "calories": 1760,
            "target_weight_kg": 72,
            "target_adherence": 80,
            "membership_end": "2026-12-31",
        }
        base.update(overrides)
        return base

    def test_summary_aggregates_progress_and_workouts(self):
        summary = fitness.build_client_summary(
            self._client(),
            progress=[{"adherence": 80}, {"adherence": 90}],
            workouts=[{"duration_min": 60}, {"duration_min": 45}],
            today=date(2026, 1, 1),
        )
        assert summary["average_adherence"] == 85.0
        assert summary["weeks_logged"] == 2
        assert summary["total_workouts"] == 2
        assert summary["total_minutes"] == 105
        assert summary["bmi"] == 26.1
        assert summary["bmi_category"] == "Overweight"
        assert summary["weight_delta_kg"] == 8.0
        assert summary["on_track"] is True

    def test_summary_flags_client_below_target(self):
        summary = fitness.build_client_summary(
            self._client(),
            progress=[{"adherence": 40}],
            workouts=[],
            today=date(2026, 1, 1),
        )
        assert summary["on_track"] is False

    def test_summary_without_body_metrics(self):
        summary = fitness.build_client_summary(
            self._client(height_cm=None, weight_kg=None, target_weight_kg=None),
            progress=[],
            workouts=[],
            today=date(2026, 1, 1),
        )
        assert summary["bmi"] is None
        assert summary["weight_delta_kg"] is None
        assert summary["average_adherence"] == 0.0
