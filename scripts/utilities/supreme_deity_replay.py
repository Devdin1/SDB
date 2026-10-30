"""Offline replay of perception facts or actual PNG frames. Never imports input APIs."""
import json
from pathlib import Path
from utilities.supreme_deity_core import BattleState, Observation, Planner, ForfeitFlow, ResultFlow, Unsafe


def replay(path):
    path = Path(path)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    config = records.pop(0)["config"]
    state, planner, flow = BattleState(route=config["route"]), Planner(config), ForfeitFlow()
    result_flow = ResultFlow()
    perception = None
    callbacks, checked = 0, 0
    for record in records:
        if "image" in record:
            from utilities.supreme_deity_vision import Perception, read_image
            if perception is None:
                root = Path(__file__).resolve().parents[1]
                profile = json.loads((root/config["profile"]).read_text(encoding="utf-8"))
                perception = Perception(profile, root/"images")
            obs = perception.observe(read_image(path.parent/record["image"]), record["time"], record["image"])
        else:
            obs = Observation.from_dict(record)
        state.update(obs)
        action, reason = None, None
        try:
            if state.abort_reason:
                action = flow.step(obs)
                if flow.done and not state.callback_done:
                    state.callback_done = True
                    callbacks += 1
            elif state.result:
                action = result_flow.step(obs, state.result)
                if result_flow.done and not state.callback_done:
                    state.victory = state.result == "complete" and not state.guard.high_frames
                    state.callback_done = True
                    callbacks += 1
            else:
                action = planner.plan(obs, state)[0]
        except Unsafe as exc:
            reason = str(exc)
        result = {"phase": int(state.phase) if state.phase else None, "abort": state.abort_reason,
                  "allowed": state.guard.allowed, "victory": state.victory, "callbacks": callbacks,
                  "action": action["kind"] if action else None, "reason": reason}
        for key, expected in record.get("expect", {}).items():
            assert result[key] == expected, f"frame {checked} {key}: expected {expected!r}, got {result[key]!r}"
        checked += 1
        print(json.dumps({"frame": checked, **result}))
    print(f"Replay passed: {checked} frames, {callbacks} verified callback(s); zero desktop input.")
    return 0
