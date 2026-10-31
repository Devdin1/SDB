"""Additive Supreme Deity farmer using the existing factory and lifecycle."""
import threading
import time
import json
from pathlib import Path
from enum import Enum, auto

from utilities.general_farmer_interface import IFarmer
from utilities.supreme_deity_fighter import SupremeDeityFighter
from utilities.supreme_deity_fighting_strategies import STRATEGIES
from utilities.supreme_deity_core import Unsafe, ForfeitFlow
from utilities.supreme_deity_pause import PauseRequested
from utilities.utilities import capture_window, click_im


class States(Enum):
    GOING_TO_SD = auto()
    PREPARE_FIGHT = auto()
    FIGHTING = auto()
    CLEANUP = auto()
    EXIT_FARMER = auto()


class SupremeDeityFarmer(IFarmer):
    def __init__(self, starting_state=States.GOING_TO_SD, battle_strategy=None,
                 num_clears=1, sd_strategy="v1", *, sd_config, sd_profile, sd_asset_root, **kwargs):
        super().__init__()
        self.current_state = starting_state
        self.config = dict(sd_config, route=sd_strategy)
        self.profile = sd_profile
        self.num_clears = 0
        self.aborted_runs = 0
        self.max_clears = float(num_clears)
        self.stop_event = threading.Event()
        self.sd_fighting_thread = None
        self.fighter = SupremeDeityFighter(STRATEGIES[sd_strategy], self.fight_complete_callback,
                                          config=self.config, profile=sd_profile, asset_root=sd_asset_root,
                                          stop_event=self.stop_event)
        self._nav_pending = None
        self._nav_attempts = 0
        self._nav_source_frames = 0
        self._nav_frame_time = None
        self._navigation_started = self.fighter.clock.now()
        self._start_issued = False
        self._start_sent_at = 0.
        self._new_frames = 0
        self._callback_run = False
        self._last_nav_click = 0.
        self._resume_path = self.config.get("resume_checkpoint")
        self._resume_verified = not bool(self._resume_path)
        self._completed_victory = None
        self._stamina_pending = False
        self._intro_skip_pending = False
        self._start_followup = None
        self._last_nav_status = 0.
        self._start_attempts = 0
        self._startup_forfeit = None
        self._startup_restarts = 0
        self._battle_seen_at = None

    def before_state_loop_iteration(self):
        self.fighter.clock.wait(self.keep_alive)
        # SD must not invoke generic daily-login or unrelated farming automation.
        if self.config.get("stop_file") and Path(self.config["stop_file"]).exists():
            self.stop_event.set()
        if self.stop_event.is_set():
            self.current_state = States.EXIT_FARMER
        if self.sd_fighting_thread and not self.sd_fighting_thread.is_alive() and self.fighter.failure:
            self.fighter.journal.write("farmer_stopped", reason=self.fighter.failure)
            self.current_state = States.EXIT_FARMER

    def _observe_navigation(self):
        im, offset = capture_window(client_area=True)
        path = self.fighter.journal.screenshot(im, "navigation")
        obs = self.fighter.perception.observe(im, self.fighter.clock.now(), path)
        from utilities.supreme_deity_chat import handle_chat_popup
        if handle_chat_popup(self.fighter, obs, offset, click_im, farmer=self):
            if self.fighter.failure:
                raise Unsafe(self.fighter.failure)
            return obs, offset
        from utilities.supreme_deity_team import check_team
        check_team(self, obs)
        if obs.time - self._last_nav_status >= 5:
            keys = ("hub_battle_shortcut", "battle_hub_menu", "sd_menu", "hell_entry", "coin_screen", "coins_ready", "setup_screen", "hell_selected", "setup_verified", "new_battle", "sd_battle", "gauge")
            status = {key: obs.get(key) for key in keys}
            if obs.get("sd_battle") is True and obs.get("new_battle") is not True:
                status.update(queue_verified=obs.get("queue_verified"), turn_mode=obs.get("turn_mode"),
                              hand_known=obs.get("hand") is not None)
            if self.config.get("verbose_output", False):
                print(f"[SD] {self.current_state.name}: {status}", flush=True)
            self.fighter.journal.write("navigation_observation", facts=status, screenshot=path)
            self._last_nav_status = obs.time
        return obs, offset

    def _adopt_or_restart_battle(self, obs):
        """Adopt only a proven untouched opening; otherwise verify a fresh exit."""
        if self._startup_forfeit is not None:
            action = self._startup_forfeit.step(obs)
            if self._startup_forfeit.done:
                print("[SD] Existing battle exited. Starting a fresh V1 run.", flush=True)
                self.fighter.perception.reset()
                self._startup_forfeit = None
                self._battle_seen_at = None
                self._new_frames = 0
                self._start_issued = False
                self._start_attempts = 0
                self._nav_pending = None
                self._navigation_started = obs.time
                self.current_state = States.GOING_TO_SD
            elif action:
                try:
                    dispatched = self.fighter._dispatch(action, obs, forfeit=True)
                except (Unsafe, PauseRequested) as exc:
                    dispatched = False
                    self.fighter.journal.write("startup_reacquire", reason=str(exc))
                if not dispatched:
                    self._startup_forfeit.last_control = None
                    self._startup_forfeit.clicks -= 1
            return True
        self._new_frames = self._new_frames+1 if obs.get("new_battle") is True else 0
        if self._new_frames >= 2:
            print("[SD] Opening battle verified; starting V1 actions.", flush=True)
            self.fighter.prepare_for_new_fight(verified_new_battle=True)
            self._callback_run = False
            self.current_state = States.FIGHTING
            return True
        if obs.get("sd_battle") is True:
            # The gauge and pause icon appear before the opening animation,
            # debuffs, and edict banners finish. They do not prove a player turn.
            if obs.time-self._navigation_started > self.config.get("navigation_timeout", 90):
                raise Unsafe("Opening battle not verified within the startup timeout; inspect saved screenshots")
            actionable = (obs.get("queue_verified") is True and obs.get("turn_mode") == "player"
                          and obs.get("hand") is not None)
            if self._start_issued or not actionable:
                self._battle_seen_at = None
                return True
            if self._battle_seen_at is None:
                self._battle_seen_at = obs.time
            if self._new_frames == 0 and obs.time-self._battle_seen_at >= 6:
                raise Unsafe("Existing battle has no verified opening/turn history; battle left open. Restart is allowed only for P3 Weakening failure")
            return True
        self._battle_seen_at = None
        return self._new_frames > 0

    def _repeat_start_once(self, obs, offset):
        pending = getattr(self, "_start_followup", None)
        if pending is None:
            return False
        if (self.stop_event.is_set() or self._stamina_pending or tuple(offset) != pending["offset"]
                or any(obs.get(key) is True for key in
                       ("new_battle", "setup_screen", "stamina_dialog", "sd_menu", "coin_screen", "result_screen"))
                or obs.get("turn_mode") == "player" and obs.get("queue_verified") is True):
            self._start_followup = None
            return False
        if obs.time < pending["due"]:
            return True  # Keep the cursor at Start; no Skip or navigation input.
        self._start_followup = None  # Exactly one attempt, even if cancelled by cursor movement.
        intro = obs.facts.get("intro_skip")
        if obs.get("intro_skip") is not True or intro.seen != obs.time:
            self.fighter.journal.write("start_followup", sent=False,
                                       reason="No fresh verified intro screen", evidence=obs.frame)
            return False
        sent = self.fighter.mouse.click_start_followup(pending["point"])
        self._last_nav_click = obs.time
        if not sent or self.config.get("verbose_output", False):
            print("[SD] 6-second intro skip: " +
                  ("moved randomly 1-2 pixels left and clicked once." if sent else "cancelled; cursor moved or Stop requested."), flush=True)
        self.fighter.journal.write("start_followup", sent=sent, evidence=obs.frame)
        return True

    def _skip_opening(self, obs, offset):
        # Handle this before battle adoption: the gauge/pause HUD is already
        # visible during the intro and otherwise causes an early return.
        cue = obs.facts.get("intro_skip")
        if obs.get("intro_skip") is not True or cue.seen != obs.time:
            self._intro_skip_pending = False
            return False
        self._start_followup = None  # Click the actual Skip control, never old Start coordinates.
        if self.stop_event.is_set():
            return True
        if obs.time-self._last_nav_click < 2:
            return True
        rect = self.fighter.perception.control_rect("skip")
        self.fighter.mouse.click(rect, offset, click_im)
        self._last_nav_click = obs.time
        self._intro_skip_pending = True
        print("[SD] clicked on skip; waiting for the battle hand.", flush=True)
        self.fighter.journal.write("intro_skip", evidence=obs.frame)
        return True

    def _retry_hell_entry(self, obs, offset, step, started):
        """Retry only the reversible Hell selector on a freshly verified menu."""
        allowed = (step.get("control") == "hell" and step.get("post") == "coin_or_setup"
                   and step.get("when") == {"sd_menu": True, "hell_entry": True})
        unchanged = (allowed and all(obs.get(key) is True and obs.facts[key].seen == obs.time
                                     for key in ("sd_menu", "hell_entry"))
                     and not any(obs.get(key) is True for key in (
                         "coin_screen", "setup_screen", "stamina_dialog", "result_screen",
                         "sd_battle", "new_battle", "intro_skip"))
                     and obs.get("turn_mode") not in ("player", "enemy"))
        if obs.time != self._nav_frame_time:
            self._nav_source_frames = self._nav_source_frames + 1 if unchanged else 0
            self._nav_frame_time = obs.time
        if (not unchanged or self._nav_source_frames < 2
                or obs.time-started <= self.config.get("action_timeout", 8)
                or self._nav_attempts >= self.config.get("hell_entry_max_attempts", 3)
                or self.stop_event.is_set()
                or obs.time-self._last_nav_click < self.config.get("action_interval", .6)):
            return False
        # Resolve the control against this current capture. No saved coordinates,
        # no retry of coin registration, Apply, or an ambiguous/loading screen.
        rect = self.fighter.perception.control_rect("hell")
        self.fighter.mouse.click(rect, offset, click_im)
        self._last_nav_click = self.fighter.clock.now()
        self._nav_attempts += 1
        self._nav_pending = (step, obs.time)
        self._nav_source_frames = 0
        self.fighter.journal.write("navigation_retry", step=step, attempt=self._nav_attempts,
                                   evidence=obs.frame, rectangle=rect)
        print(f"[SD] Still on the difficulty menu; retrying {self.config.get('difficulty', 'hell').title()} entry "
              f"(attempt {self._nav_attempts}).", flush=True)
        return True

    def _navigation(self):
        obs, offset = self._observe_navigation()
        if obs.get("chat_popup") is True:
            return
        if not self._resume_verified:
            if obs.get("battle_exited") is not True:
                raise Unsafe("Resume requires a visually verified out-of-battle boundary")
            saved = json.loads(Path(self._resume_path).read_text(encoding="utf-8"))
            if (saved.get("boundary") != "verified_exit" or saved.get("route") != self.config["route"]
                    or saved.get("difficulty", "hell") != self.config.get("difficulty", "hell")):
                raise Unsafe("Checkpoint is not a compatible verified exit boundary")
            self.num_clears = int(saved["clears"])
            self.aborted_runs = int(saved["aborts"])
            self._resume_verified = True
            if self.num_clears >= self.max_clears:
                self.current_state = States.EXIT_FARMER
                return
        # A known correct setup supersedes an outstanding menu transition,
        # including when the user opened the team screen manually.
        if (obs.get("setup_verified") is True and obs.get("hell_selected") is True
                and obs.get("setup_screen") is True and obs.get("stamina_dialog") is not True):
            self._nav_pending = None
            self._navigation_started = obs.time
            self.current_state = States.PREPARE_FIGHT
            return
        if obs.time-self._navigation_started > self.config.get("navigation_timeout", 90):
            raise Unsafe("Navigation/reentry timed out")
        if self._skip_opening(obs, offset):
            return
        if self._adopt_or_restart_battle(obs):
            return
        # Allow navigation to arrive directly at setup, including manual screen changes.
        if obs.get("setup_screen") is True or obs.get("stamina_dialog") is True:
            self._nav_pending = None
            self.current_state = States.PREPARE_FIGHT
            return
        if self._nav_pending:
            step, started = self._nav_pending
            if obs.get(step["post"]) is True:
                self.fighter.journal.write("navigation_postcondition", step=step,
                                           attempt=self._nav_attempts, evidence=obs.frame)
                self._nav_pending = None
                self._nav_source_frames = 0
            elif self._retry_hell_entry(obs, offset, step, started):
                return
            elif obs.time-started > step.get("timeout", self.config.get("action_timeout", 8)):
                self.fighter.journal.write("navigation_unconfirmed", step=step,
                                           attempt=self._nav_attempts, evidence=obs.frame)
                raise Unsafe(f"Navigation postcondition unverified: {step['control']} -> "
                             f"{step['post']} ({self._nav_attempts} attempts)")
            return
        # Explicit calibrated screen -> one control -> screen postcondition.
        from utilities.supreme_deity_registration import navigation_steps
        for step in navigation_steps(self.profile, self.config.get("registration_multiplier", 3)):
            if all(obs.get(key) == value for key, value in step.get("when", {}).items()) and step.get("when"):
                if self.stop_event.is_set() or obs.time-self._last_nav_click < self.config.get("action_interval",.6):
                    return
                rect = self.fighter.perception.control_rect(step["control"])
                self.fighter.mouse.click(rect, offset, click_im)
                self._last_nav_click = self.fighter.clock.now()
                self._nav_pending = (step, obs.time)
                self._nav_attempts = 1
                self._nav_source_frames = 0
                self._nav_frame_time = None
                self.fighter.journal.write("navigation_action", step=step)
                if step["control"] in ("open_battle_hub", "open_supreme_deity"):
                    print("[SD] Opening " + ("Battle menu." if step["control"] == "open_battle_hub" else "Supreme Deity."), flush=True)
                return

    def going_to_sd_state(self):
        if self.num_clears >= self.max_clears:
            self.current_state = States.EXIT_FARMER
            return
        self._navigation()

    def prepare_fight_state(self):
        obs, offset = self._observe_navigation()
        if obs.get("chat_popup") is True:
            return
        if obs.time-self._navigation_started > self.config.get("navigation_timeout", 90):
            raise Unsafe("Opening battle/navigation timed out")
        if obs.get("stamina_dialog") is True:
            # Stamina takes priority over the optional intro click and Start retry.
            if self._start_followup is not None:
                self.fighter.journal.write("start_followup", sent=False,
                                           reason="Stamina dialog", evidence=obs.frame)
            self._start_followup = None
            # Same potion behavior as the existing farmer, with a local opt-out.
            if not self.config.get("use_stamina_potions", True):
                raise Unsafe("Stamina exhausted; potion use disabled by configuration")
            if not self._stamina_pending:
                rect = self.fighter.perception.control_rect("stamina_use")
                if self.stop_event.is_set():
                    return
                self.fighter.mouse.click(rect, offset, click_im)
                self.fighter.journal.write("stamina_use", evidence=obs.frame, rectangle=rect)
                self._stamina_pending = True
                self._last_nav_click = obs.time
            elif obs.time-self._last_nav_click > self.config.get("action_timeout", 8):
                raise Unsafe("Stamina restoration postcondition unverified")
            return
        # A failed Start is separate from the delayed intro click. Check the
        # positively recognized team screen before intro/battle handling.
        if (self._start_issued and not self._stamina_pending
                and obs.get("setup_screen") is True and obs.get("stamina_dialog") is not True):
            if obs.time-self._start_sent_at > 3:
                self._start_followup = None
                if self._start_attempts >= 3:
                    raise Unsafe("Start input had no effect after 3 attempts. Check privileges and keep the game unobstructed.")
                self._start_issued = False
                self.fighter.journal.write("start_retry", attempt=self._start_attempts, evidence=obs.frame)
                print("[SD] Still on setup; retrying Start after verified non-transition.", flush=True)
            return
        if self._skip_opening(obs, offset):
            return
        if self._repeat_start_once(obs, offset):
            return
        if self._adopt_or_restart_battle(obs):
            return
        if obs.get("sd_menu") is True or obs.get("coin_screen") is True:
            print("[SD] Menu detected; resuming navigation.", flush=True)
            self._start_issued = False
            self._nav_pending = None
            self.current_state = States.GOING_TO_SD
            return
        if self._stamina_pending:
            if obs.get("setup_screen") is not True and obs.get("new_battle") is not True:
                if obs.time-self._last_nav_click > self.config.get("action_timeout", 8):
                    raise Unsafe("Stamina restoration postcondition unverified")
                return
            IFarmer.stamina_pots += 1
            self._stamina_pending = False
            # The original start may have opened the stamina dialog, not entered battle.
            if obs.get("setup_screen") is True:
                self._start_issued = False
        if self._start_issued:
            if obs.time-self._navigation_started > self.config.get("navigation_timeout", 90):
                raise Unsafe("Start was issued but a fresh battle was not verified")
            return
        if obs.get("hell_selected") is not True or obs.get("setup_verified") is not True:
            if obs.time-self._navigation_started > self.config.get("navigation_timeout", 90):
                raise Unsafe("Selected difficulty/team setup not verified")
            return
        rect = self.fighter.perception.control_rect("start")
        if self.stop_event.is_set() or obs.time-self._last_nav_click < self.config.get("action_interval",.6):
            return
        point = self.fighter.mouse.click(rect, offset, click_im)
        self._start_attempts += 1
        print(f"[SD] Correct {self.config.get('difficulty', 'hell').title()} team verified; Start clicked. Waiting for the battle.", flush=True)
        self._last_nav_click = self.fighter.clock.now()
        self._start_sent_at = self._last_nav_click
        self._start_followup = dict(point=point, offset=tuple(offset), due=self._last_nav_click+6)
        self._start_issued = True
        self._navigation_started = obs.time
        # Return immediately so subsequent captures can handle a stamina
        # dialog. The optional six-second click is checked against fresh intro
        # evidence by _repeat_start_once; it never blocks screen recognition.

    def fighting_state(self):
        with IFarmer._lock:
            if self.sd_fighting_thread is None or not self.sd_fighting_thread.is_alive():
                if self.fighter.failure or self._callback_run:
                    self.current_state = States.EXIT_FARMER
                    return
                self.sd_fighting_thread = threading.Thread(target=self.fighter.run, daemon=True, name="SupremeDeityFighter")
                self.sd_fighting_thread.start()

    def fight_complete_callback(self, victory=False):
        with IFarmer._lock:
            if self._callback_run:
                return
            self._callback_run = True
            self._completed_victory = bool(victory)
            self.current_state = States.CLEANUP

    def cleanup_state(self):
        # The callback executes inside the old fighter. Wait until its wrapper has
        # returned before resetting it or navigating into another battle.
        if self.sd_fighting_thread and self.sd_fighting_thread.is_alive():
            return
        if self._completed_victory is None:
            return
        with IFarmer._lock:
            victory = self._completed_victory
            self._completed_victory = None
            if victory:
                self.num_clears += 1
                print(f"[CLEAR] Supreme Deity {self.config.get('difficulty', 'hell').title()}: {self.num_clears}")
            else:
                self.aborted_runs += 1
                print(f"[ABORT] {'BATTLE_FAILED' if self.fighter.sd.result == 'failed' else self.fighter.sd.abort_reason}")
            checkpoint = self.fighter.journal.root / "checkpoint.json"
            checkpoint.write_text(json.dumps({"boundary":"verified_exit","route":self.config["route"],
                "difficulty":self.config.get("difficulty","hell"),"clears":self.num_clears,"aborts":self.aborted_runs},indent=2),encoding="utf-8")
            if (not victory and not (self.fighter.sd.restart_allowed or self.fighter.sd.result == "failed")
                    or self.num_clears >= self.max_clears):
                self.current_state = States.EXIT_FARMER
            else:
                self.current_state = States.GOING_TO_SD
                print(f"[SD] Battle exit verified; returning to {self.config.get('difficulty', 'hell').title()} entry for the next run.", flush=True)
                self.fighter.perception.reset()
                self._start_issued = False
                self._new_frames = 0
                self._nav_pending = None
                self._stamina_pending = False
                self._intro_skip_pending = False
                self._start_followup = None
                self._start_attempts = 0
                self._battle_seen_at = None
                self._navigation_started = self.fighter.clock.now()

    def run(self):
        def pauseable(handler):
            def step():
                try:
                    handler()
                except PauseRequested:
                    pass  # Re-observe and re-plan after resume; do not reuse a target.
            return step
        try:
            self.run_state_loop({States.GOING_TO_SD: pauseable(self.going_to_sd_state),
                                 States.PREPARE_FIGHT: pauseable(self.prepare_fight_state),
                                 States.FIGHTING: pauseable(self.fighting_state),
                                 States.CLEANUP: pauseable(self.cleanup_state),
                                 States.EXIT_FARMER: pauseable(self.exit_farmer_state)},
                                login_return_state=States.GOING_TO_SD,
                                sleep_seconds=self.config.get("navigation_tick_seconds", .25), check_reconnect=False, login_check=False)
        except Exception as exc:
            # Factory retries generic Exceptions; SD failures must instead stop.
            self.fighter.journal.write("farmer_error", reason=str(exc))
            raise KeyboardInterrupt(f"SD stopped safely: {exc}") from exc
        finally:
            self.stop_event.set()
            if self.sd_fighting_thread:
                self.sd_fighting_thread.join(timeout=2)
