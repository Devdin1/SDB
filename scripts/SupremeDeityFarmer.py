"""Opt-in Windows live entry point; check/replay modes import no desktop drivers."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Supreme Deity Hell/Hard: screenshot/mouse controller")
    parser.add_argument("--num-clears", type=int, default=1)
    parser.add_argument("--difficulty", choices=["hell", "hard"], default=None)
    parser.add_argument("--sd-strategy", choices=["v1"], default="v1")
    parser.add_argument("--config", default="config/supreme_deity/v1.json")
    parser.add_argument("--registration-multiplier", type=int, choices=[1, 3], default=3)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Requires a complete calibrated profile; F8 stops")
    mode.add_argument("--dry-run", metavar="SCREENSHOT", help="Perceive and propose without desktop input")
    mode.add_argument("--replay", metavar="JSONL", help="Replay evidence fixtures; no desktop input")
    parser.add_argument("--check", action="store_true", help="List missing calibration; default mode")
    parser.add_argument("--resume", metavar="CHECKPOINT", help="Restore counters only at a verified out-of-battle boundary")
    parser.add_argument("--stop-file", help=argparse.SUPPRESS)
    parser.add_argument("--pause-file", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.num_clears < 1:
        parser.error("--num-clears must be positive")
    if args.replay:
        from utilities.supreme_deity_replay import replay
        return replay(args.replay)
    root = Path(__file__).resolve().parent
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if args.sd_strategy:
        config["route"] = args.sd_strategy
    config["registration_multiplier"] = args.registration_multiplier
    profile_path = root / config["profile"]
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if args.difficulty:
        config["difficulty"] = args.difficulty
    from utilities.supreme_deity_difficulty import configure_difficulty
    config, profile = configure_difficulty(config, profile, root)
    from utilities.supreme_deity_vision import validate_profile, Perception, read_image
    errors = validate_profile(config, profile, root / "images")
    if args.dry_run:
        from utilities.supreme_deity_core import BattleState, Planner, Unsafe
        from dataclasses import asdict
        perception = Perception(profile, root / "images")
        screenshot = read_image(args.dry_run)
        if screenshot is None:
            raise SystemExit("Cannot read screenshot")
        obs = perception.observe(screenshot, 0., args.dry_run)
        print(json.dumps(asdict(obs), indent=2))
        print("Single-frame dry run: no actions; temporal stability requires replay.")
        return 0
    if errors:
        print("LIVE BLOCKED: calibration is incomplete\n- " + "\n- ".join(errors))
        return 2
    if not args.live:
        from termcolor import colored
        print(colored("[SUCCESS] Installation Successfull", "green"))
        print("Configuration, dependencies, and assets checked. Ready to start.")
        return 0
    if float(args.num_clears) <= 0:
        raise SystemExit("--num-clears must be positive")
    config["live"] = True
    if args.stop_file:
        config["stop_file"] = str(Path(args.stop_file).resolve())
    if args.pause_file:
        config["pause_file"] = str(Path(args.pause_file).resolve())
    print("[SD] Live mode starting. F8 or the launcher Stop button stops input.", flush=True)
    if args.resume:
        config["resume_checkpoint"] = str(Path(args.resume).resolve())
    # Import side-effectful project modules only after live intent and preflight.
    from utilities.supreme_deity_farming_logic import SupremeDeityFarmer, States
    from utilities.supreme_deity_windows import input_access_error
    access_error = input_access_error()
    if access_error:
        print("[SD] INPUT BLOCKED: " + access_error, flush=True)
        return 3
    from utilities.farming_factory import FarmingFactory
    FarmingFactory.main_loop(farmer=SupremeDeityFarmer, starting_state=States.GOING_TO_SD,
                             battle_strategy=None, num_clears=args.num_clears,
                             sd_strategy=config["route"], sd_config=config,
                             sd_profile=profile, sd_asset_root=root / "images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
