import random
import sys
import threading
import unittest
import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from utilities.supreme_deity_core import BattleState
from utilities.supreme_deity_fighter import SupremeDeityFighter
from utilities.supreme_deity_farming_logic import States, SupremeDeityFarmer
from utilities.supreme_deity_gui_view import BattleView
from utilities.supreme_deity_mouse import MouseMotion
from utilities.supreme_deity_pause import PauseControl
from utilities import utilities


class SupremeDeityInputInactivityTests(unittest.TestCase):
    def test_successful_click_refreshes_monotonic_input_time(self):
        mouse = MouseMotion(threading.Event(), rng=random.Random(1))
        mouse.last_input_time = 10.0
        mouse.travel = Mock()
        perform = Mock()

        with patch("utilities.supreme_deity_mouse.time.monotonic", return_value=42.0):
            mouse.click((0, 0, 100, 100), (0, 0), perform)

        self.assertEqual(mouse.last_input_time, 42.0)
        perform.assert_called_once()

    def test_successful_drag_refreshes_monotonic_input_time(self):
        mouse = MouseMotion(threading.Event(), rng=random.Random(1))
        mouse.last_input_time = 10.0
        mouse.travel = Mock()
        perform = Mock()

        with patch("utilities.supreme_deity_mouse.time.monotonic", return_value=42.0):
            mouse.drag((0, 0, 100, 100), (100, 0, 100, 100), (0, 0), perform)

        self.assertEqual(mouse.last_input_time, 42.0)
        perform.assert_called_once()

    def test_cursor_travel_refreshes_monotonic_input_time(self):
        mouse = MouseMotion(threading.Event(), rng=random.Random(1))
        mouse.last_input_time = 10.0

        with patch.object(utilities.pyautogui, "moveTo") as move_to:
            with patch("utilities.supreme_deity_mouse.time.monotonic", return_value=42.0):
                mouse.travel((10, 20), (0, 0))

        self.assertEqual(mouse.last_input_time, 42.0)
        move_to.assert_called_once()

    def test_successful_start_followup_click_refreshes_monotonic_input_time(self):
        mouse = MouseMotion(threading.Event(), rng=random.Random(1))
        mouse.last_input_time = 10.0
        mouse.travel = Mock()

        with patch.object(utilities.pyautogui, "position", return_value=(10, 20)):
            with patch.object(utilities.win32api, "mouse_event"):
                with patch.object(utilities.click_tracker, "record_click"):
                    with patch("utilities.supreme_deity_mouse.time.sleep"):
                        with patch("utilities.supreme_deity_mouse.time.monotonic", return_value=42.0):
                            sent = mouse.click_start_followup((10, 20))

        self.assertTrue(sent)
        self.assertEqual(mouse.last_input_time, 42.0)

    def test_failed_click_does_not_refresh_input_time(self):
        mouse = MouseMotion(threading.Event(), rng=random.Random(1))
        mouse.last_input_time = 10.0
        mouse.travel = Mock()

        def failed_input(*args, **kwargs):
            raise OSError("mouse input failed")

        with patch("utilities.supreme_deity_mouse.time.monotonic", return_value=42.0):
            with self.assertRaises(OSError):
                mouse.click((0, 0, 100, 100), (0, 0), failed_input)

        self.assertEqual(mouse.last_input_time, 10.0)

    def test_idle_under_300_seconds_does_not_request_reset(self):
        fighter = self._fighter(last_input_time=100.0)

        with patch("utilities.supreme_deity_fighter.time.monotonic", return_value=399.0):
            self.assertFalse(fighter._check_input_timeout())

        self.assertIsNone(fighter.sd.abort_reason)
        fighter.journal.write.assert_not_called()

    def test_300_seconds_idle_requests_one_reset_and_rearms_timer(self):
        fighter = self._fighter(last_input_time=100.0)

        with patch("utilities.supreme_deity_fighter.time.monotonic", return_value=400.0):
            self.assertTrue(fighter._check_input_timeout())

        self.assertEqual(fighter.sd.abort_reason, "NO_INPUT_TIMEOUT")
        self.assertTrue(fighter.sd.restart_allowed)
        self.assertEqual(fighter.mouse.last_input_time, 400.0)
        fighter.journal.write.assert_called_once()

        with patch("utilities.supreme_deity_fighter.time.monotonic", return_value=800.0):
            self.assertFalse(fighter._check_input_timeout())

        fighter.journal.write.assert_called_once()

    def test_existing_restart_reasons_remain_allowed(self):
        for reason in (
            "CURRENT_PHASE_UNVERIFIED",
            "UNEXPECTED_PHASE_TRANSITION",
            "RUN_TIMEOUT",
            "RED_WAVE_HIGH_GAUGE",
            "P4_ENTRY_GAUGE_NO_WEAKENING",
        ):
            with self.subTest(reason=reason):
                state = BattleState(route="v1")
                state.abort_reason = reason
                self.assertTrue(state.restart_allowed)

    def test_timeout_cleanup_counts_one_gui_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            state = BattleState(route="v1")
            state.abort_reason = "NO_INPUT_TIMEOUT"
            fighter = SimpleNamespace(
                sd=state,
                journal=SimpleNamespace(root=Path(directory)),
                perception=SimpleNamespace(reset=Mock()),
                clock=SimpleNamespace(now=Mock(return_value=500.0)),
            )
            farmer = object.__new__(SupremeDeityFarmer)
            farmer.sd_fighting_thread = None
            farmer._completed_victory = False
            farmer.aborted_runs = 0
            farmer.num_clears = 0
            farmer.max_clears = 2
            farmer.config = {"route": "v1", "difficulty": "hell"}
            farmer.fighter = fighter
            farmer.current_state = States.CLEANUP
            farmer._start_issued = False
            farmer._new_frames = 0
            farmer._nav_pending = None
            farmer._stamina_pending = False
            farmer._intro_skip_pending = False
            farmer._start_followup = None
            farmer._start_attempts = 0
            farmer._battle_seen_at = None
            farmer._navigation_started = 0.0

            output = io.StringIO()
            with redirect_stdout(output):
                farmer.cleanup_state()
                farmer.cleanup_state()

            abort_lines = [line for line in output.getvalue().splitlines() if "[ABORT]" in line]
            self.assertEqual(farmer.aborted_runs, 1)
            self.assertEqual(abort_lines, ["[ABORT] NO_INPUT_TIMEOUT"])

            view = object.__new__(BattleView)
            view.reset_count = 0
            view.resets = SimpleNamespace(set=lambda value: setattr(view, "resets_value", value))
            view.reset = Mock()
            view.consume(abort_lines[0])
            self.assertEqual(view.reset_count, 1)
            self.assertEqual(view.resets_value, "1")

    def test_fighting_loop_sends_timeout_through_existing_forfeit_flow(self):
        fighter = self._fighter(last_input_time=100.0)
        observation = SimpleNamespace(get=lambda key, default=None: default)

        def wait_with_watchdog(*, on_wait=None):
            if on_wait is not None:
                on_wait()
            return True

        fighter.clock = SimpleNamespace(wait=wait_with_watchdog, now=Mock(return_value=400.0))
        fighter.config = {"run_timeout": 900}
        fighter._run_started = 0.0
        fighter._check_context = Mock(return_value=False)
        fighter.observe = Mock(return_value=observation)
        fighter._handle_result = Mock(return_value=False)
        fighter._skip_between_phases = Mock(return_value=False)
        fighter.forfeit = SimpleNamespace(done=False, step=Mock(return_value=None))

        with patch("utilities.supreme_deity_fighter.time.monotonic", return_value=400.0):
            fighter.fighting_state()

        self.assertEqual(fighter.sd.abort_reason, "NO_INPUT_TIMEOUT")
        fighter.forfeit.step.assert_called_once_with(observation)

    def test_idle_timeout_is_checked_during_pause_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            pause_file = Path(directory) / "pause"
            pause_file.touch()

            class ResumeAfterFirstWait:
                def __init__(self):
                    self.reset_requested_while_paused = False

                def is_set(self):
                    return False

                def wait(self, timeout=None):
                    self.reset_requested_while_paused = fighter.sd.abort_reason == "NO_INPUT_TIMEOUT"
                    pause_file.unlink(missing_ok=True)
                    return False

            fighter = self._fighter(last_input_time=100.0)
            pause_event = ResumeAfterFirstWait()
            observation = SimpleNamespace(get=lambda key, default=None: default)
            fighter.clock = PauseControl(
                {"pause_file": str(pause_file)}, pause_event, clock=lambda: 400.0
            )
            fighter.config = {"run_timeout": 900}
            fighter._run_started = 0.0
            fighter._check_context = Mock(return_value=False)
            fighter.observe = Mock(return_value=observation)
            fighter._handle_result = Mock(return_value=False)
            fighter._skip_between_phases = Mock(return_value=False)
            fighter.forfeit = SimpleNamespace(done=False, step=Mock(return_value=None))

            with patch("utilities.supreme_deity_fighter.time.monotonic", return_value=400.0):
                fighter.fighting_state()

            self.assertEqual(fighter.sd.abort_reason, "NO_INPUT_TIMEOUT")
            self.assertTrue(pause_event.reset_requested_while_paused)
            fighter.forfeit.step.assert_called_once_with(observation)

    def test_new_fight_rearms_timer_for_another_independent_timeout(self):
        fighter = self._fighter(last_input_time=100.0)
        fighter.config = {"route": "v1", "phase_turn_limit": 4}
        fighter.battle_strategy = Mock()
        fighter._reset_instance_variables = Mock()
        fighter.clock = SimpleNamespace(now=Mock(return_value=500.0))
        fighter.perception = SimpleNamespace(reset=Mock())

        with patch("utilities.supreme_deity_mouse.time.monotonic", return_value=500.0):
            fighter.prepare_for_new_fight(verified_new_battle=True)

        self.assertEqual(fighter.mouse.last_input_time, 500.0)
        with patch("utilities.supreme_deity_fighter.time.monotonic", return_value=799.0):
            self.assertFalse(fighter._check_input_timeout())
        with patch("utilities.supreme_deity_fighter.time.monotonic", return_value=800.0):
            self.assertTrue(fighter._check_input_timeout())

    @staticmethod
    def _fighter(last_input_time):
        fighter = object.__new__(SupremeDeityFighter)
        fighter.sd = BattleState(route="v1")
        fighter.mouse = MouseMotion(threading.Event(), rng=random.Random(1))
        fighter.mouse.last_input_time = last_input_time
        fighter.journal = Mock()
        fighter._reset_notice_printed = False
        return fighter


if __name__ == "__main__":
    unittest.main()
