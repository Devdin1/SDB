"""Difficulty-specific calibration and turn budgets; shared V1 card identities."""
from copy import deepcopy
import json


def configure_difficulty(config, profile, root):
    config, profile = deepcopy(config), deepcopy(profile)
    difficulty = config.get("difficulty", "hell")
    if difficulty not in ("hell", "hard"):
        raise ValueError("Difficulty must be hell or hard")
    config["difficulty"] = difficulty
    config["phase_turn_limit"] = 5 if difficulty == "hard" else 4
    profile["difficulty"] = difficulty
    profile["turn_limit"] = config["phase_turn_limit"]
    if difficulty == "hard":
        overlay = json.loads((root / "config/supreme_deity/hard-calibration.json").read_text(encoding="utf-8"))
        for section in ("templates", "detectors", "controls"):
            profile[section].update(overlay[section])
        # Legacy hell_selected/hell_entry/hell are compatibility keys for the
        # shared navigation engine. This profile maps them only to Hard art.
        for rule in profile.get("rules", []):
            rule["evidence"] = rule.get("evidence", "").replace("Hell", "Hard")
        config["run_timeout"] = config.get("hard_run_timeout", 1200)
    return config, profile
