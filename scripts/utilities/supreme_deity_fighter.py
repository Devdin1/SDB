"""SD fighter: bounded transactions, continuous gauge guard, and verified exit."""
from __future__ import annotations

import json
import time
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from utilities.general_fighter_interface import IFighter, FightingStates
from utilities.logging_utils import LoggerWrapper
from utilities.image_assets import get_default_image_asset_resolver
from utilities.utilities import capture_window, click_im, drag_im
from utilities.supreme_deity_core import BattleState, ForfeitFlow, ResultFlow, Unsafe, Phase
from utilities.supreme_deity_vision import Perception, save_image
from utilities.supreme_deity_mouse import MouseMotion
from utilities.supreme_deity_pause import PauseControl, PauseRequested

logger = LoggerWrapper(name="SupremeDeity", log_to_file=False)
INPUT_IDLE_TIMEOUT_SECONDS = 300


class Journal:
    def __init__(self, root):
        self.root = Path(root) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        self.root.mkdir(parents=True, exist_ok=True)
        self.counter = 0
        self.lock = threading.Lock()

    def write(self, event, **data):
        with self.lock:
            with (self.root / "events.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **data}, default=str) + "\n")

    def screenshot(self, image, label):
        self.counter += 1
        path = self.root / f"{self.counter:06d}_{label}.png"
        save_image(path, image)
        return str(path)


class SupremeDeityFighter(IFighter):
    def __init__(self, battle_strategy, callback=None, *, config, profile, asset_root, stop_event=None):
        super().__init__(battle_strategy, callback)
        self.config, self.profile = config, profile
        self.battle_strategy.configure(config)
        self.perception = Perception(profile, asset_root, get_default_image_asset_resolver())
        self.sd = BattleState(route=config["route"], turn_limit=config.get("phase_turn_limit", 4))
        print("[SD] Phase counter: 0/6. Waiting for the opening battle.", flush=True)
        self.forfeit = ForfeitFlow(config.get("forfeit_timeout", 20), config.get("forfeit_max_clicks", 6))
        self.journal = Journal(config.get("log_directory", "logs/supreme_deity"))
        self.stop_event = stop_event or threading.Event()
        self.clock = PauseControl(config, self.stop_event, clock=lambda: time.monotonic())
        self.mouse = MouseMotion(self.stop_event, input_guard=self.clock.check_input)
        self.last_action = 0.
        self.failure = None
        self._last_snapshot = None
        self._last_obs = None
        self._waiting_since = None
        self._last_weakening_status = None
        self._reset_notice_printed = False
        self._context_unknown_since = None
        self._last_p3_turn_notice = None
        self._p3_selection_verified_turns = set()
        self._phase_skip = None
        self._started = False
        self._new_battle_frames = 0
        self.result_flow = ResultFlow()
        self._run_started = self.clock.now()

    def prepare_for_new_fight(self, verified_new_battle=False):
        if not verified_new_battle:
            raise Unsafe("Refusing to reset the abort latch without a verified new battle")
        # Base phase helpers mutate IFighter class attributes; keep SD state local.
        self.battle_strategy.reset_phase_turn()
        self._reset_instance_variables()
        self.sd = BattleState(route=self.config["route"], turn_limit=self.config.get("phase_turn_limit", 4))
        self._last_weakening_status = None
        self._reset_notice_printed = False
        self._context_unknown_since = None
        self._last_p3_turn_notice = None
        self._p3_selection_verified_turns = set()
        self._phase_skip = None
        print("[SD] Phase counter: 0/6. New battle reset.", flush=True)
        self.sd.guard.reset(True)
        self.forfeit = ForfeitFlow(self.config.get("forfeit_timeout", 20), self.config.get("forfeit_max_clicks", 6))
        self.failure = None
        self._waiting_since = None
        self._started = True
        self.perception.reset()
        self.result_flow = ResultFlow()
        self.last_action = 0.
        self.mouse.reset_input_timer()
        self._run_started = self.clock.now()
        self._last_obs = self._last_snapshot = None
        self.journal.write("verified_new_battle", route=self.sd.route,
                           difficulty=self.config.get("difficulty", "hell"), turn_limit=self.sd.turn_limit)

    def observe(self, label="tick"):
        screenshot, offset = capture_window(client_area=True)
        now = self.clock.now()
        path = self.journal.screenshot(screenshot, label)
        obs = self.perception.observe(screenshot, now, path)
        self._last_snapshot = (screenshot, offset)
        self._last_obs = obs
        from utilities.supreme_deity_chat import handle_chat_popup
        if handle_chat_popup(self, obs, offset, click_im):
            return obs
        previous_phase = self.sd.phase
        previous_final_enemy = self.sd.final_enemy
        self.sd.update(obs)
        if self.sd.abort_reason == "RED_WAVE_HIGH_GAUGE" and not self._reset_notice_printed:
            print(f"[SD] Red phase detected at {obs.get('gauge')}%; resetting the run.", flush=True)
            self._reset_notice_printed = True
            self.journal.write("red_wave_reset", gauge=obs.get("gauge"), evidence=obs.frame)
        if self.sd.abort_reason == "P4_ENTRY_GAUGE_NO_WEAKENING" and not self._reset_notice_printed:
            print(f"[SD] Phase 4 reset: entered at {self.sd.p4_entry_gauge}% without confirmed Weakening.", flush=True)
            self._reset_notice_printed = True
            self.journal.write("p4_weakening_reset", entry_gauge=self.sd.p4_entry_gauge, evidence=obs.frame)
        if self.sd.final_enemy and self.sd.final_enemy != previous_final_enemy:
            name = self.sd.final_enemy
            message = "Tarmiel confirmed; using Tarmiel strategy (one card per unit per turn)." if name == "tarmiel" else f"Final enemy confirmed: {name}."
            print("[SD] " + message, flush=True)
            self.journal.write("final_enemy_confirmed", enemy=name, evidence=obs.frame)
        if (self.sd.phase == Phase.P3 and self.sd.turns_completed == 0
                and obs.get("stigma_menu") is True):
            status = obs.get("weakening_available")
            if status is not None and status != self._last_weakening_status:
                self._last_weakening_status = status
                message = ("Weakening available; activating and verifying its effect before cards."
                           if status else "Weakening activation confirmed; returning to battle."
                           if obs.get("weakening_effect") is True
                           else "Weakening unavailable; using the alternate Phase 3 strategy.")
                print("[SD] Phase 3: " + message, flush=True)
        if self.sd.phase != previous_phase and self.sd.phase is not None:
            self._waiting_since = None
            if obs.get("phase_crystal_reset") is True:
                # Prevent the remembered banner from re-emitting the old phase.
                self.perception.v1.phase = int(self.sd.phase)
                self.perception.v1.banner = int(self.sd.phase)
            reason = ("new messenger wave and fresh player queue" if obs.get("phase_spawn_transition")
                      else "crystal reset and fresh player queue" if obs.get("phase_crystal_reset") else "battle/phase cue")
            print(f"[SD] Moved to Phase ({self.sd.phase_counter}/6). Turn 1.", flush=True)
            self.journal.write("phase_confirmed", counter=self.sd.phase_counter, evidence=obs.frame)
        if (self.sd.phase == Phase.P3 and (3,1,"aoe_route") in self.sd.extras
                and obs.get("selected_target") == "right" and obs.get("stable") is True):
            turn = self.sd.turns_completed+1
            if turn not in self._p3_selection_verified_turns:
                self._p3_selection_verified_turns.add(turn)
                print(f"[SD] Phase 3 turn {turn}: far-right selection visually verified; no repeat click.", flush=True)
                self.journal.write("p3_target_verified", turn=turn, target="right", evidence=obs.frame)
        self.journal.write("perception", observation=asdict(obs), phase=self.sd.phase,
                           turns=self.sd.turns_completed, abort=self.sd.abort_reason,
                           gauge=asdict(self.sd.guard.last_confirmed), queue=self.sd.queue)
        if (self.sd.phase == Phase.P3 and obs.get("turn_mode") == "player"
                and obs.get("stable") is True and not self.sd.pending
                and obs.get("empty_slots") == 4 and not self.sd.queue):
            turn = self.sd.turns_completed + 1
            alternate = (3,1,"aoe_route") in self.sd.extras
            original = any(e["phase"] == 3 and e["turn"] == 1
                           and e["action"]["kind"] == "weakening" for e in self.sd.history)
            if (alternate or original) and turn != self._last_p3_turn_notice:
                self._last_p3_turn_notice = turn
                remaining = obs.get("lit_crystals")
                detail = f"{remaining} turns left on the crystal counter. " if type(remaining) is int and 1 <= remaining <= self.sd.turn_limit else ""
                ult = ("Ultimates scheduled this turn." if turn >= self.sd.turn_limit else f"Ultimates in {self.sd.turn_limit-turn} turns.") if alternate else "Original Weakening strategy."
                print(f"[SD] Phase 3 turn {turn}/{self.sd.turn_limit}: {detail}{ult}", flush=True)
                self.journal.write("p3_turn_countdown", turn=turn, crystals=remaining,
                                   ultimate_turn=self.sd.turn_limit if alternate else None)
        return obs

    def _identify_phase(self, screenshot):
        return int(self.sd.phase) if self.sd.phase is not None else None

    def count_empty_card_slots(self, screenshot, threshold=.97):
        return self._last_obs.get("empty_slots", 0) if self._last_obs else 0

    def _finish_once(self, victory):
        if not self.sd.callback_done:
            self.sd.callback_done = True
            self.journal.write("fight_complete", victory=victory, abort=self.sd.abort_reason)
            self.complete_callback(victory=bool(victory))
        with self._lock:
            self.exit_thread = True

    def exit_fight_state(self):
        if self.sd.abort_reason:
            if self.forfeit.done:
                self._finish_once(False)
        elif self.result_flow.done:
            self._finish_once(self.sd.victory)

    def _dispatch(self, action, expected_obs, forfeit=False, result=False, menu_cleanup=False):
        if forfeit and not self.sd.restart_allowed:
            return False
        if self.stop_event.is_set() or self.exit_thread:
            raise Unsafe("Emergency stop")
        if self.clock.now() - self.last_action < self.config.get("action_interval", .6):
            return False
        fresh = self._action_observation(expected_obs)
        if (fresh.get("chat_popup") is True
                or self.sd.phase in (Phase.P4, Phase.GREY) and fresh.get("intro_skip") is True):
            return False
        if not forfeit and not result and (
                self.sd.transition_pending or expected_obs.get("phase") != fresh.get("phase")):
            return False
        if action["kind"] == "talent" and (fresh.get("talent_ready") is not True
                                         or fresh.get("talent_effect") is True):
            return False
        if forfeit:
            if not self.sd.restart_allowed:
                return False
            context = {"pause": "pause_actionable", "forfeit": "pause_menu", "forfeit_confirm": "forfeit_confirmation",
                       "menu_close": "stigma_menu"}
            if fresh.get(context[action["control"]]) is not True:
                return False
        elif result:
            if (fresh.get(self.sd.result) is not True or fresh.get("result_screen") is not True
                    or self.sd.guard.high_frames or self.sd.abort_reason):
                return False
        else:
            if not self.sd.guard.allowed or self.sd.abort_reason or self.sd.stopped_reason:
                return False
            menu_action = (action["kind"] in ("weakening", "strengthening", "destruction", "heal", "menu_close")
                           and fresh.get("stigma_menu") is True and self.sd._turn_mode == "player")
            if not menu_cleanup and (fresh.get("stable") is not True
                                     or fresh.get("turn_mode") != "player" and not menu_action):
                return False
            if self.sd.pending and not menu_cleanup:
                return False
            if menu_cleanup:
                pending = self.sd.pending
                if (not pending or pending["action"]["kind"] not in ("weakening", "strengthening", "destruction", "heal")
                        or fresh.get("stigma_menu") is not True
                        or fresh.get(pending["action"]["post"]) is not True):
                    return False
            old_hand, new_hand = expected_obs.get("hand"), fresh.get("hand")
            sig = lambda hand: [(c["id"], c["rank"], c["disabled"]) for c in (hand or [])]
            if sig(old_hand) != sig(new_hand) or fresh.get("empty_slots") != expected_obs.get("empty_slots"):
                return False
            # Re-plan the next V1 action from this exact pre-action observation.
            plan = [action] if menu_cleanup else self.battle_strategy.planner.plan(fresh, self.sd)
            if action["kind"] == "target" and plan[0].get("target") != action["target"]:
                return False
            if action["kind"] not in ("target",) and plan[0] != action:
                # Metadata timestamps change; compare semantic action identity.
                def identity(a):
                    return (a["kind"], a.get("index"), a.get("target"), a.get("control"), a.get("indices"), a.get("card", {}).get("id"))
                if identity(plan[0]) != identity(action):
                    return False
        screenshot, offset = self._last_snapshot
        view = self.perception.last_viewport
        if not self.config.get("live", False):
            self.journal.write("dry_run_action", action=action)
            self.failure = "DRY_RUN: proposed action logged; no desktop input"
            return False
        if action["kind"] == "card":
            if (action.get("target") and action.get("confirm_target", True)
                    and fresh.get("selected_target") != action["target"]):
                return False
            card = fresh.get("hand")[action["index"]]
            self.mouse.click(view.local_rect(card["rectangle"]), offset, click_im, card=True)
        elif action["kind"] == "move":
            hand = fresh.get("hand")
            i,j = action["indices"]
            if i == j or not 0 <= i < len(hand) or not 0 <= j < len(hand):
                raise Unsafe("Invalid movement indices")
            self.mouse.drag(view.local_rect(hand[i]["rectangle"]), view.local_rect(hand[j]["rectangle"]), offset, drag_im, card=True)
        elif action["kind"] == "lock":
            slot = action["slot"]
            if slot not in fresh.get("unused_slots", []):
                return False
            rect = fresh.get("slot_rectangles", {}).get(str(slot))
            if rect is None:
                return False
            self.mouse.click(view.local_rect(rect), offset, click_im)
        else:
            if (action["kind"] == "stigma_open" and self.sd.phase == Phase.P3
                    and self.sd.turns_completed == 0 and not self.sd.auto_forfeit_disabled):
                rect = self.perception.control_rect(action["control"], p3_opening=True)
            else:
                rect = self.perception.control_rect(action["control"])
            if action["kind"] in ("weakening", "strengthening", "destruction", "heal"):
                self.perception.arm_stigma(action["kind"])
            self.mouse.click(rect, offset, click_im)
        self.last_action = self.clock.now()
        self.journal.write("action", action=action, before=fresh.frame, route=self.sd.route)
        if forfeit:
            if not getattr(self, "_reset_notice_printed", False):
                print("[SD] Can not verify current phase, let's reset!", flush=True)
                self._reset_notice_printed = True
            label = {"pause":"Pause", "forfeit":"Forfeit Battle", "forfeit_confirm":"OK",
                     "menu_close":"Close Stigma menu"}[action["control"]]
            print(f"[SD] Clicked {label}.", flush=True)
        elif not result and not menu_cleanup:
            from utilities.supreme_deity_output import action_status
            print(action_status(action, self.sd.phase, self.sd.turns_completed + 1), flush=True)
        if menu_cleanup:
            self.sd.pending["menu_close_sent"] = True
        elif action["kind"] == "target" and action.get("confirm_target") is False:
            # This opening proceeds once the observed middle boss has been clicked.
            self.sd.confirm_action(action)
            self.journal.write("target_click_sent", action=action, evidence=fresh.frame,
                               phase=self.sd.phase, turn=self.sd.turns_completed)
        elif not forfeit and not result:
            self.sd.pending = {"action": action, "started": self.last_action,
                               "slots_before": fresh.get("empty_slots", self.sd.menu_slots), "hand_before": fresh.get("hand"),
                               "moved_before": fresh.get("moved_slots", []),
                               "crystals_before": fresh.get("lit_crystals"),
                               "effect_before": fresh.get(action.get("post", "")),
                               "ready_before": fresh.get("talent_ready"),
                               "origin_frame": fresh.frame, "effect_evidence": [],
                               "phase": self.sd.phase, "turn": self.sd.turns_completed,
                               "last_frame": None}
        after = self.observe("after_action")
        if self.sd.pending and not menu_cleanup and not forfeit and not result:
            # This is already a fresh capture. Count its evidence, without
            # issuing a retry from inside the dispatch transaction.
            self._pending(after, allow_retry=False)
        return True

    def _action_observation(self, expected_obs):
        # A just-verified capture is already valid input evidence. Avoid doing
        # the entire recognizer twice back-to-back when nothing was sent between
        # them. Stale frames and any intervening input always force recapture.
        age = self.clock.now() - expected_obs.time
        if (expected_obs is self._last_obs and self._last_snapshot is not None
                and self.last_action < expected_obs.time and 0 <= age <= .5):
            return expected_obs
        return self.observe("before_action")

    def _retry_unchanged_action(self, obs, pending):
        """Retry only proven no-effect input; never click through an animation."""
        action = pending["action"]
        if (self.sd.transition_pending or pending.get("phase") != self.sd.phase
                or pending.get("turn") != self.sd.turns_completed):
            return
        if action["kind"] not in ("card", "move", "lock", "talent", "stigma_open"):
            return
        if action["kind"] == "stigma_open" and not (
                self.sd.phase == Phase.P3 and self.sd.turns_completed == 0
                and obs.get("stigma_menu") is False and obs.get("stigma_closed") is True):
            return
        talent = action["kind"] == "talent"
        if talent:
            # Talent is an independent button, not a hand/queue action. A hand
            # hidden by the preceding Stigma menu cannot prevent safe retries.
            ready = (obs.get("talent_ready") is True and obs.get("talent_effect") is False
                     and obs.get("stable") is True and obs.get("turn_mode") == "player"
                     and obs.get("stigma_closed") is True and obs.get("stigma_menu") is False
                     and obs.get("queue_verified") is True
                     and obs.get("empty_slots") == pending["slots_before"]
                     and all(obs.facts[key].seen == obs.time for key in
                             ("talent_ready", "talent_effect"))
                     and obs.time > pending["started"])
            if pending.get("retry_ready_time") != obs.time:
                pending["retry_ready_frames"] = pending.get("retry_ready_frames", 0)+1 if ready else 0
                pending["retry_ready_time"] = obs.time
            if not ready or pending.get("retry_ready_frames", 0) < 2:
                return
        if obs.time-pending["started"] < self.config.get("action_retry_seconds", 2):
            return
        signature = lambda hand: [(c.get("id"), c.get("rank"), c.get("disabled"), c.get("hand_slot"))
                                  for c in hand]
        hand = obs.get("hand")
        lock_without_hand = (self.sd.phase == Phase.FINAL and action["kind"] == "lock"
                             and action["slot"] in obs.get("unused_slots", []))
        if (obs.get("stable") is not True or obs.get("turn_mode") != "player"
                or obs.get("queue_verified") is not True
                or obs.get("empty_slots") != pending["slots_before"]
                or not talent and not lock_without_hand and (hand is None or pending.get("hand_before") is None
                    or signature(hand) != signature(pending["hand_before"]))
                or obs.get("moved_slots", []) != pending.get("moved_before", [])):
            return
        attempts = pending.get("attempts", 1)
        if attempts >= self.config.get("max_action_attempts", 6):
            if self.sd.phase == Phase.FINAL:
                if action["kind"] == "card":
                    self.sd.final_failed_skills.add((self.sd.turns_completed+1, action["card"]["id"]))
                    self.sd.final_force_move = True
                    self.sd.pending = None
                    self.journal.write("final_recovery", reason="Unchanged attack after retries; use a move", action=action)
                    return
                pending["attempts"] = 1
                attempts = 1
            else:
                raise Unsafe("Action unchanged after maximum verified retries")
        # _dispatch re-observes, checks the gauge and re-plans against the current
        # hand before resolving current card rectangles. No stored screen clicks.
        self.sd.pending = None
        try:
            if self._dispatch(action, obs):
                if self.sd.pending is not None:
                    self.sd.pending["attempts"] = attempts+1
                    self.sd.pending["transaction_started"] = pending.get("transaction_started", pending["started"])
                self.journal.write("action_retry", action=action, attempt=attempts+1, evidence=obs.frame)
            else:
                self.sd.pending = pending
        except Exception:
            self.sd.pending = pending
            raise

    def _pending(self, obs, *, allow_retry=True):
        pending = self.sd.pending
        if not pending:
            return False
        action = pending["action"]
        if (action.get("p4_required") and self.sd.phase == Phase.P4
                and obs.time-pending.get("transaction_started",pending["started"]) >
                    self.config.get("p4_weakening_confirmation_timeout",20)):
            self.sd.abort_reason = "P4_ENTRY_GAUGE_NO_WEAKENING"
            self.sd.pending = None
            self.journal.write("p4_weakening_unconfirmed", action=action, evidence=obs.frame)
            return True
        crossed = (pending.get("phase") != self.sd.phase
                   or pending.get("turn") != self.sd.turns_completed)
        activation = action["kind"] in ("talent", "weakening", "strengthening", "destruction", "heal")
        if crossed and not activation:
            self.journal.write("action_superseded", action=action, phase=pending.get("phase"),
                               turn=pending.get("turn"), evidence=obs.frame)
            self.sd.pending = None
            return True
        if (not crossed and not self.sd.transition_pending
                and action["kind"] in ("weakening", "strengthening", "destruction", "heal")
                and obs.get(action["post"]) is True and obs.get("stigma_menu") is True):
            if not pending.get("menu_close_sent"):
                self._dispatch({"kind":"menu_close", "control":"menu_close", "post":"stigma_closed"},
                               obs, menu_cleanup=True)
            cleanup_timeout = (self.config.get("p4_weakening_confirmation_timeout",20)
                               if action.get("p4_required") else self.config.get("action_timeout",8))
            if obs.time-pending["started"] > cleanup_timeout:
                if self.sd.phase == Phase.FINAL:
                    pending["menu_close_sent"] = False
                    pending["started"] = obs.time
                    return True
                raise Unsafe("Stigma return to battle UI timed out")
            return True
        success = False
        if action["kind"] in ("card", "move", "lock"):
            slots = obs.get("empty_slots")
            sig = lambda hand: [(c.get("id"),c.get("rank"),c.get("disabled")) for c in (hand or [])]
            success = (type(slots) is int and slots == pending["slots_before"]-1
                       and obs.get("queue_verified") is True)
            if action["kind"] == "lock":
                success = success and action["slot"] in obs.get("locked_slots", [])
            elif action["kind"] == "move":
                from utilities.supreme_deity_core import hand_matches_action_merges
                success = (success and obs.get("hand") is not None
                           and (bool(set(obs.get("moved_slots", []))-set(pending.get("moved_before", [])))
                                or hand_matches_action_merges(pending["hand_before"], obs.get("hand"), action)))
            else:
                from utilities.supreme_deity_core import hand_matches_action_merges
                selected = action.get("card") or pending["hand_before"][action["index"]]
                count = lambda hand: sum(c.get("id") == selected.get("id") and c.get("rank") == selected.get("rank")
                                         for c in (hand or []))
                success = (success and obs.get("hand") is not None
                           and (count(obs.get("hand")) < count(pending["hand_before"])
                                or hand_matches_action_merges(pending["hand_before"], obs.get("hand"), action)))
            if pending["slots_before"] == 1 and obs.get("turn_mode") == "enemy":
                success = obs.get("queue_executed") is True
            before_crystals = pending.get("crystals_before")
            if (pending["slots_before"] == 1 and type(before_crystals) is int
                    and obs.get("lit_crystals") == before_crystals-1
                    and obs.get("turn_mode") == "player" and obs.get("stable") is True
                    and obs.get("queue_verified") is True and slots == 4
                    and obs.get("hand") is not None):
                # The enemy banner can be missed. A reduced turn counter and
                # fresh empty player queue prove the last queued action resolved.
                success = True
        elif action["kind"] == "target":
            success = obs.get("selected_target") == action["target"]
        elif action["kind"] == "stigma_open":
            success = obs.get("stigma_menu") is True
        else:
            success = (obs.get(action["post"]) is True
                       and obs.get("empty_slots") == pending["slots_before"])
            if action["kind"] in ("weakening", "strengthening", "destruction", "heal"):
                success = success and obs.get("stigma_closed") is True
            if activation:
                fact = obs.facts.get(action["post"])
                causal = (pending.get("effect_before") is not True and fact is not None
                          and fact.known(obs.time) and fact.seen > pending["started"])
                if action["kind"] == "talent":
                    causal = causal and pending.get("ready_before") is True
                success = causal and obs.get(action["post"]) is True and (crossed or success)
        if pending["last_frame"] == obs.time:
            return True
        pending["last_frame"] = obs.time
        if success and activation:
            pending.setdefault("effect_evidence", []).append(asdict(obs.facts[action["post"]]))
        pending["confirmations"] = pending.get("confirmations", 0)+1 if success else 0
        if pending["confirmations"] >= 2:
            if action["kind"] == "stigma_open":
                self.sd.menu_slots = pending["slots_before"]
            self.sd.confirm_action(action, phase=pending.get("phase"),
                                   turn=pending.get("turn", self.sd.turns_completed)+1,
                                   evidence=pending.get("effect_evidence"))
            if pending.get("phase") == Phase.P3 and action["kind"] == "weakening":
                print("[SD] Phase 3: Weakening confirmed; using the original strategy.", flush=True)
            elif pending.get("phase") == Phase.P3 and action.get("skip_extra") == "aoe_route":
                print("[SD] Phase 3: using the alternate strategy without Weakening.", flush=True)
            if pending.get("phase") == Phase.P3 and action["kind"] == "card":
                counts = self.sd.card_use_counts(Phase.P3)
                print(f"[SD] Phase 3 confirmed card selections: {sum(counts.values())} | {counts}", flush=True)
                self.journal.write("p3_card_counts", counts=counts, turn=pending.get("turn", 0)+1)
            self.journal.write("postcondition", action=action, evidence=obs.frame,
                               phase=pending.get("phase"), turn=pending.get("turn"),
                               effect_evidence=pending.get("effect_evidence", []))
            self.sd.pending = None
            self.sd.reconcile_completed_turn(obs)
            self._waiting_since = None
            return True
        if (obs.get("stigma_rejected") is True and action["kind"] == "weakening"
                and self.sd.phase == Phase.P3):
            self._p3_aoe_fallback(obs, "Weakening rejected")
            return True
        ordinary = action["kind"] in ("card", "move", "lock")
        timeout = (self.config.get("p4_weakening_confirmation_timeout",20) if action.get("p4_required")
                   else self.config.get("queue_resolution_timeout", 75) if ordinary and pending["slots_before"] == 1
                   else self.config.get("action_confirmation_timeout", 45) if ordinary
                   else self.config.get("talent_confirmation_timeout", 20) if action["kind"] == "talent"
                   else self.config.get("stigma_open_confirmation_timeout", 20)
                   if action["kind"] == "stigma_open" and self.sd.phase == Phase.P3
                   else self.config.get("action_timeout", 8))
        if obs.time-pending.get("transaction_started", pending["started"]) > timeout:
            if (not crossed and action.get("p3_optional") and self.sd.phase == Phase.P3
                    and (obs.get("stigma_menu") is True
                         or obs.get("stigma_closed") is True and obs.get("queue_verified") is True
                         and obs.get("empty_slots") == pending["slots_before"])):
                self._p3_aoe_fallback(obs, "Optional Weakening unconfirmed")
                return True
            if (not crossed and action.get("p4_optional") and self.sd.phase == Phase.P4
                    and self.sd.turns_completed >= 1
                    and (obs.get("stigma_menu") is True
                         or obs.get("stigma_closed") is True and obs.get("queue_verified") is True)):
                self.sd.extras.add((4, self.sd.turns_completed + 1, "weakening_opening_declined"))
                self.sd.pending = None
                self.journal.write("p4_opening_skipped", action=action, evidence=obs.frame,
                                   reason="Optional Weakening unconfirmed; retain original strategy")
                return True
            if crossed:
                raise Unsafe("Prior-phase activation remains unconfirmed; no cross-wave retry")
            if self.sd.phase == Phase.FINAL:
                if ((action["kind"] == "stigma_open" and obs.get("stigma_closed") is True
                     and obs.get("queue_verified") is True and obs.get("stable") is True)
                        or action["kind"] == "menu_close" and obs.get("stigma_menu") is True):
                    self.sd.pending = None  # Re-plan the still-required menu input.
                    if action["kind"] == "stigma_open":
                        key = (6,self.sd.turns_completed+1,"stigma_open")
                        started = self.sd.optional_unknown_since.setdefault(key,obs.time)
                        if obs.time-started >= 2*self.config.get("action_timeout",8):
                            extra = {1:"opening_stigma",2:"opening_stigma",3:"destruction",4:"heal"}.get(self.sd.turns_completed+1)
                            if extra:
                                self.sd.extras.add((6,self.sd.turns_completed+1,extra))
                                self.journal.write("final_recovery",reason="Optional menu did not open; continue attacks")
                elif action["kind"] in ("weakening", "strengthening", "destruction", "heal") and (
                        obs.get("stigma_menu") is True
                        or obs.get("stigma_closed") is True and obs.get("queue_verified") is True
                        and obs.get("empty_slots") == pending["slots_before"]):
                    # Optional activation remains unconfirmed, not successful.
                    # Suppress re-use this turn; planner closes any open menu.
                    self.sd.extras.add((6,self.sd.turns_completed+1,action["kind"]))
                    if action.get("skip_extra"):
                        self.sd.extras.add((6,self.sd.turns_completed+1,action["skip_extra"]))
                    self.sd.pending = None
                    self.journal.write("final_recovery", reason="Optional Stigma unconfirmed; continue attacks", action=action)
                else:
                    self._retry_unchanged_action(obs, pending)
                return True
            raise Unsafe("Action confirmation timed out; UI never established success or safe retry")
        if not success and allow_retry and not crossed and not self.sd.transition_pending:
            self._retry_unchanged_action(obs, pending)
        return True

    def _p3_aoe_fallback(self, obs, reason):
        self.sd.extras.add((3, 1, "aoe_route"))
        self.sd.pending = None
        self.journal.write("p3_aoe_route", reason=reason, evidence=obs.frame)
        print(f"[SD] {reason}; using the alternate Phase 3 strategy.", flush=True)

    def _request_context_reset(self, reason):
        self.sd.abort_reason = "CURRENT_PHASE_UNVERIFIED"
        self.sd.pending = None
        if not self._reset_notice_printed:
            print("[SD] Can not verify current phase, let's reset!", flush=True)
            self._reset_notice_printed = True
        self.journal.write("context_reset", reason=reason)

    def _check_context(self, obs):
        # Brief animations/debouncing may hide the HUD. Persistent missing or
        # contradictory context must also recover when no planner call occurs.
        menu = obs.get("stigma_menu") is True
        unknown = (self.sd.phase is None or self.sd.transition_pending
                   or obs.get("red_wave") is True
                   or obs.get("phase") is not None and obs.get("phase") != self.sd.phase
                   or obs.get("turn_mode") not in ("player", "enemy") and not menu)
        if (not menu and not self.sd.pending and obs.get("stable") is True
                and obs.get("turn_mode") == "player" and obs.get("queue_verified") is True):
            unknown = unknown or obs.get("empty_slots") != 4-len(self.sd.queue)
            crystals = obs.get("lit_crystals")
            if (self.sd.phase == Phase.P3 and obs.get("empty_slots") == 4
                    and not self.sd.queue and type(crystals) is int and 1 <= crystals <= self.sd.turn_limit):
                unknown = unknown or crystals != self.sd.turn_limit-self.sd.turns_completed
        if not unknown:
            self._context_unknown_since = None
        elif self._context_unknown_since is None:
            self._context_unknown_since = obs.time
        elif obs.time-self._context_unknown_since >= self.config.get("context_reacquire_seconds", 90):
            self._request_context_reset("Phase/turn/queue context remained unknown")
        return unknown

    def _check_input_timeout(self):
        if self.sd.abort_reason or self.sd.result:
            return False
        now = time.monotonic()
        idle_seconds = now - self.mouse.last_input_time
        if idle_seconds < INPUT_IDLE_TIMEOUT_SECONDS:
            return False

        self.mouse.reset_input_timer()
        self.sd.abort_reason = "NO_INPUT_TIMEOUT"
        self._reset_notice_printed = True
        reason = "No input for 5 minutes - assuming bot is stuck. Resetting fight."
        self.journal.write("input_idle_reset_requested", reason=reason, idle_seconds=idle_seconds)
        print(f"[SD] {reason}", flush=True)
        return True

    def play_cards(self, **kwargs):
        """SD-specific transactional override; shared _before_pick_cards is untouched."""
        obs = kwargs["observation"]
        self.battle_strategy.observation, self.battle_strategy.state = obs, self.sd
        plan = self.battle_strategy.planner.plan(obs, self.sd)
        self.journal.write("proposed_queue", queue=plan, confirmed_queue=self.sd.queue)
        action = plan[0]
        # SD has already classified identity, rank and playability. The generic
        # Card adapter repeated ML classification but its results were unused.
        # Dispatch still captures a fresh screen and revalidates the proposal.
        if (action.get("target") and action.get("confirm_target", True)
                and obs.get("selected_target") != action["target"]):
            action = {"kind": "target", "target": action["target"], "control": "target_"+action["target"]}
        self._dispatch(action, obs)

    def my_turn_state(self):
        obs = self._last_obs
        # Guard is before entering play_cards and repeats immediately before input.
        if not self.sd.guard.allowed or self.sd.abort_reason or self.sd.stopped_reason:
            return
        self.play_cards(observation=obs)

    def _skip_between_phases(self, obs):
        if self.sd.phase not in (Phase.P4, Phase.GREY):
            return False
        cue = obs.facts.get("intro_skip")
        progress = getattr(self, "_phase_skip", None)
        visible = obs.get("intro_skip") is True and cue.seen == obs.time
        if not visible:
            if progress and progress.get("active"):
                # Cutscene time must not consume the pending action's deadline.
                elapsed = obs.time - progress["started"]
                if self.sd.pending:
                    for key in ("started", "transaction_started"):
                        if key in self.sd.pending:
                            self.sd.pending[key] += elapsed
                progress["active"] = False
            return False
        if self.stop_event.is_set():
            return True
        if not progress or progress["phase"] != self.sd.phase or not progress.get("active"):
            progress = dict(phase=self.sd.phase, started=obs.time, last_click=-float("inf"), clicks=0, active=True)
            self._phase_skip = progress
        if obs.time - progress["started"] > 12:
            raise Unsafe("Phase transition Skip did not dismiss the cutscene")
        if progress["clicks"] >= 3 or obs.time - progress["last_click"] < 2:
            return True
        rect = self.perception.control_rect("skip")
        self.mouse.click(rect, self._last_snapshot[1], click_im)
        progress["last_click"] = obs.time
        progress["clicks"] += 1
        self.last_action = self.clock.now()
        self.journal.write("phase_transition_skip", phase=int(self.sd.phase), evidence=obs.frame)
        print("[SD] Clicked Skip.", flush=True)
        return True

    def fighting_state(self):
        if not self.clock.wait(on_wait=self._check_input_timeout):
            return
        obs = self.observe()
        if obs.get("chat_popup") is True:
            return
        if self._handle_result(obs):
            return
        if self._skip_between_phases(obs):
            return
        context_uncertain = False
        if not self.sd.result and not self.sd.abort_reason:
            context_uncertain = self._check_context(obs)
        if (self.clock.now() - self._run_started > self.config.get("run_timeout", 900)
                and not self.sd.result):
            self.sd.abort_reason = self.sd.abort_reason or "RUN_TIMEOUT"
        if self.sd.abort_reason:
            if not self.sd.restart_allowed:
                self.failure = "Automation stopped; battle left open: " + self.sd.abort_reason
                self.journal.write("protected_battle_stopped", reason=self.failure)
                return
            self.sd.pending = None
            action = self.forfeit.step(obs)
            if self.forfeit.done:
                self.exit_fight_state()
            elif action:
                # If rate-limited, retain state so this unissued click can be retried.
                try:
                    dispatched = self._dispatch(action, obs, forfeit=True)
                except (Unsafe, PauseRequested):
                    self.forfeit.last_control = None
                    self.forfeit.clicks -= 1
                    raise
                if not dispatched:
                    self.forfeit.last_control = None
                    self.forfeit.clicks -= 1
            return
        if self.sd.stopped_reason:
            raise Unsafe(self.sd.stopped_reason)
        if context_uncertain:
            return
        if not self.sd.guard.allowed:
            if self.sd.guard.unknown_frames >= self.sd.guard.max_unknown:
                self.sd.abort_reason = "GAUGE_REACQUISITION_EXHAUSTED"
            return
        if self.sd.pending:
            self._pending(obs)
            if self.sd.pending or self.sd.abort_reason:
                return
        if self.sd.transition_pending:
            return
        if obs.get("turn_mode") == "player" and obs.get("empty_slots", 0) > 0:
            self.battle_strategy.phase_turn = self.sd.turns_completed + 1
            self.my_turn_state()

    def _handle_result(self, obs):
        """A confirmed result takes priority over pending cards and resets."""
        if not self.sd.result:
            return False
        self.sd.pending = None
        self.sd.abort_reason = None
        action = self.result_flow.step(obs, self.sd.result)
        if self.result_flow.done:
            self.sd.victory = self.sd.result == "complete" and not self.sd.guard.high_frames
            self.exit_fight_state()
        elif action:
            try:
                if not self._dispatch(action, obs, result=True):
                    self.result_flow.clicked = False
            except (Unsafe, PauseRequested):
                self.result_flow.clicked = False
                raise
        return True

    @IFighter.run_wrapper
    def run(self, **kwargs):
        try:
            while not self.exit_thread and not self.stop_event.is_set():
                try:
                    self.fighting_state()
                    # Only consecutive failed acquisition attempts share a
                    # deadline; animation/progress must not carry an old timer.
                    self._waiting_since = None
                    if self.failure:
                        return
                except PauseRequested:
                    continue
                except Unsafe as exc:
                    # Missing evidence gets bounded passive reacquisition. A failed
                    # forfeit never calls completion or allows navigation/reentry.
                    self.journal.write("suspended", reason=str(exc))
                    if self._waiting_since is None:
                        self._waiting_since = self.clock.now()
                        if "Required resource missing" in str(exc):
                            self.journal.write("resource_deviation", reason=str(exc),
                                               audit=self.sd.resource_audit(), confirmed_history=self.sd.history)
                    if (self.sd.abort_reason and str(exc).startswith("FORFEIT_UI_TIMEOUT")) or self.sd.result:
                        self.failure = str(exc)
                        return
                    if self.clock.now()-self._waiting_since >= self.config.get("reacquire_seconds", 10):
                        self._request_context_reset(str(exc))
                self.stop_event.wait(self.config.get("tick_seconds", .25))
        except Exception as exc:
            self.failure = f"Controller error: {type(exc).__name__}: {exc}"
            self.journal.write("error", reason=self.failure)
        finally:
            if self.stop_event.is_set():
                self.failure = "EMERGENCY_STOP"
            logger.info(self.failure or "SD fighter exited")

    def stop_fighter(self):
        self.stop_event.set()
        super().stop_fighter()
