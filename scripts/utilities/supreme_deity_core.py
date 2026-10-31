"""Pure, desktop-free Supreme Deity state estimation and conservative queue planning.

Observed facts are never replaced by predicted card effects. None means unknown.
Calibration supplies skill identities/legality, not guessed game mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import Any


class Phase(IntEnum):
    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4
    GREY = 5
    FINAL = 6


ROUTES = ("v1",)
THRESHOLD_REASON = "TOP_LEFT_PERCENT_OVER_50"


def hand_matches_action_merges(before, after, action):
    """Match the whole observed hand to this action followed by adjacent merges.

    Requires at least one merge; callers must also verify queue consumption.
    Enumerating merge order handles chained merges without assuming their result.
    """
    if before is None or after is None:
        return False
    signature = lambda cards: tuple((c.get("id"), c.get("rank")) for c in cards)
    cards = list(signature(before))
    target = signature(after)
    if any(identity is None or rank not in (0, 1, 2, 100)
           for identity, rank in cards + list(target)):
        return False
    if action.get("kind") == "card":
        index = action.get("index")
        if type(index) is not int or not 0 <= index < len(cards):
            return False
        selected = action.get("card")
        if selected and cards[index] != (selected.get("id"), selected.get("rank")):
            return False
        cards.pop(index)
    elif action.get("kind") == "move":
        indices = action.get("indices", [])
        if len(indices) != 2 or any(type(i) is not int or not 0 <= i < len(cards) for i in indices):
            return False
        source, destination = indices
        cards.insert(destination, cards.pop(source))
    else:
        return False
    if len(target) >= len(cards):
        return False
    pending, seen = [tuple(cards)], set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in seen or len(current) <= len(target):
            continue
        seen.add(current)
        for i in range(len(current)-1):
            identity, rank = current[i]
            if rank in (0, 1) and current[i] == current[i+1]:
                pending.append(current[:i] + ((identity, rank+1),) + current[i+2:])
    return False


@dataclass(frozen=True)
class Fact:
    value: Any = None
    confidence: float = 0.0
    seen: float = 0.0
    evidence: str = "unknown"
    provenance: str = "unknown"

    def known(self, now: float, ttl: float = 1.5, minimum: float = .92) -> bool:
        return (self.value is not None and self.confidence >= minimum
                and 0 <= now - self.seen <= ttl)


@dataclass
class Observation:
    time: float
    facts: dict[str, Fact] = field(default_factory=dict)
    frame: str = ""

    def get(self, key: str, default=None):
        fact = self.facts.get(key, Fact())
        return fact.value if fact.known(self.time) else default

    @classmethod
    def from_dict(cls, data):
        t = float(data["time"])
        return cls(t, {k: Fact(**v) for k, v in data.get("facts", {}).items()}, data.get("frame", ""))


class Unsafe(RuntimeError):
    """Evidence is insufficient; no battle input is allowed."""


class GaugeGuard:
    def __init__(self, confirmations=2, max_unknown=12):
        self.confirmations = confirmations
        self.max_unknown = max_unknown
        self.last_confirmed: Fact = Fact()
        self.abort_reason: str | None = None
        self.high_frames = 0
        self.unknown_frames = 0
        self.last_frame_time = None
        self.allowed = False

    def reset(self, verified_new_battle: bool):
        if not verified_new_battle:
            raise Unsafe("Gauge latch can reset only at a verified fresh battle")
        self.__init__(self.confirmations, self.max_unknown)

    def update(self, obs: Observation, phase: Phase | None, *, enforce=True):
        if not enforce:
            # Gauge readings are telemetry when availability is checked in-menu.
            # Scene/hand/queue checks still govern every input.
            f = obs.facts.get("gauge", Fact())
            if (obs.get("gauge_anchor") is True and f.known(obs.time)
                    and type(f.value) in (int,float) and 0 <= f.value <= 100):
                self.last_confirmed = f
            self.abort_reason = None
            self.high_frames = self.unknown_frames = 0
            self.last_frame_time = obs.time
            self.allowed = True
            return True
        if self.abort_reason:
            return False
        # A capture is counted only once, even when used by multiple guards.
        if obs.time == self.last_frame_time:
            return self.allowed
        self.last_frame_time = obs.time
        self.allowed = False
        final_hud = obs.get("final_hud") is True and phase == Phase.FINAL
        if final_hud and obs.get("gauge_anchor") is not True:
            # Keep the old value. Never classify final boss HP as gauge.
            self.allowed = (self.last_confirmed.value is not None
                            and self.last_confirmed.value <= 50 and self.high_frames == 0)
            if not self.allowed:
                self.unknown_frames += 1
            return self.allowed
        f = obs.facts.get("gauge", Fact())
        value = f.value
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100
        if obs.get("gauge_anchor") is True and numeric and f.known(obs.time):
            self.unknown_frames = 0
            if value > 50:
                self.high_frames += 1
                if self.high_frames >= self.confirmations:
                    self.last_confirmed = f
                    self.abort_reason = THRESHOLD_REASON
                return False  # Suspend immediately, including first apparent high frame.
            self.high_frames = 0
            self.last_confirmed = f
            self.allowed = True
            return True
        self.unknown_frames += 1
        # An occluded frame does not dismiss a pending high reading.
        return False


@dataclass
class BattleState:
    route: str = "v1"
    turn_limit: int = 4
    phase: Phase | None = None
    turns_completed: int = 0
    guard: GaugeGuard = field(default_factory=GaugeGuard)
    abort_reason: str | None = None
    stopped_reason: str | None = None
    callback_done: bool = False
    victory: bool = False
    result: str | None = None
    queue: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    extras: set[tuple] = field(default_factory=set)
    optional_unknown_since: dict = field(default_factory=dict)
    menu_slots: int | None = None
    pending: dict | None = None
    superseded_actions: list[dict] = field(default_factory=list)
    _phase_candidate: int | None = None
    _transition_target: int | None = None
    _phase_frames: int = 0
    _turn_mode: str | None = None
    _turn_candidate: str | None = None
    _turn_frames: int = 0
    _result_candidate: str | None = None
    _result_frames: int = 0
    _last_update: float | None = None
    _turn_queued: bool = False
    _enemy_boundary: bool = False
    _reduced_crystal_frames: int = 0
    _crystal_reset_armed: bool = False
    _wave_spawn_armed: bool = False
    _cutscene_armed: bool = False
    phase_counter: int = 0
    _turn_crystals: int | None = None
    auto_forfeit_disabled: bool = False
    final_failed_skills: set = field(default_factory=set)
    final_force_move: bool = False
    final_enemy: str | None = None
    _final_enemy_candidate: str | None = None
    _final_enemy_frames: int = 0
    _red_wave_frames: int = 0
    p4_entry_gauge: float | None = None

    def resource_audit(self):
        """Inspect confirmed opening actions when a guaranteed resource is missing."""
        odin_moves = gawain_moves = 0
        opening_cards = []
        for event in self.history:
            a = event["action"]
            if event["phase"] == 1 and a["kind"] == "move":
                odin_moves += event["turn"] == 1 and a.get("owner") == "Odin"
                gawain_moves += event["turn"] == 2 and a.get("owner") == "Gawain"
            if event["phase"] == 1 and event["turn"] == 2 and a["kind"] == "card":
                opening_cards.append(a["card"]["id"])
        return {"odin_moves_confirmed": odin_moves, "gawain_moves_confirmed": gawain_moves,
                "opening_cards": opening_cards,
                "opening_matches_v1": odin_moves == 4 and gawain_moves == 2
                and opening_cards == ["freyr_1", "odin_2"] and (1,2,"talent") in self.extras}

    @property
    def restart_allowed(self):
        return self.abort_reason in (
            "CURRENT_PHASE_UNVERIFIED", "UNEXPECTED_PHASE_TRANSITION", "RUN_TIMEOUT",
            "RED_WAVE_HIGH_GAUGE", "P4_ENTRY_GAUGE_NO_WEAKENING", "NO_INPUT_TIMEOUT",
        )

    def card_use_counts(self, phase):
        """Confirmed queue selections only; retries never increase this audit."""
        counts = {}
        for event in self.history:
            action = event["action"]
            if event["phase"] == int(phase) and action["kind"] == "card":
                skill = action["card"]["id"]
                counts[skill] = counts.get(skill, 0) + 1
        return counts

    def final_repeat_risk(self, turn):
        """Owners queued more than once on a completed final-phase turn.

        A risk audit, not proof of damage or a visually observed skill block.
        """
        from utilities.supreme_deity_v1_policy import CARD_IDENTITIES
        counts = {}
        for event in self.history:
            action = event["action"]
            if event["phase"] != 6 or event["turn"] != turn or action["kind"] != "card":
                continue
            owner = CARD_IDENTITIES.get(action["card"].get("id"), {}).get("owner")
            if owner:
                counts[owner] = counts.get(owner,0)+1
        return {owner for owner,count in counts.items() if count >= 2}

    @property
    def transition_pending(self):
        return self._transition_target is not None

    def confirm_action(self, action, *, phase=None, turn=None, evidence=None):
        origin_phase = int(self.phase if phase is None else phase)
        origin_turn = self.turns_completed + 1 if turn is None else turn
        current = origin_phase == self.phase and origin_turn == self.turns_completed + 1
        ordinary = action["kind"] in ("card", "move", "lock")
        self.history.append(dict(phase=origin_phase, turn=origin_turn, action=action,
                                 evidence=evidence or []))
        if ordinary and current:
            self.queue.append(action)
            self._turn_queued = True
            if self.phase == Phase.FINAL and action["kind"] in ("move", "lock"):
                self.final_force_move = False
        elif action["kind"] in ("talent", "weakening", "strengthening", "destruction", "heal"):
            self.extras.add((origin_phase, origin_turn, action["kind"]))
            if action["kind"] == "weakening":
                self.auto_forfeit_disabled = True
        if action.get("skip_extra"):
            self.extras.add((origin_phase, origin_turn, action["skip_extra"]))

    def _p3_planned_kill(self):
        """Weakening, Talent and the four planned cards were confirmed in P3
        turn 1 and one enemy turn has passed, so the wave is expected dead."""
        if self.phase != Phase.P3 or self.turns_completed != 1:
            return False
        kinds = [e["action"]["kind"] for e in self.history
                 if e["phase"] == Phase.P3 and e["turn"] == 1]
        return "weakening" in kinds and "talent" in kinds and kinds.count("card") >= 4

    def update(self, obs: Observation):
        if self._last_update == obs.time:
            return
        self._last_update = obs.time
        p = obs.get("phase")
        if self.phase in (Phase.P1, Phase.P2, Phase.P3, Phase.P4):
            if obs.get("new_wave_banner") is True and (self._turn_queued or self.pending):
                self._wave_spawn_armed = True
            crystals = obs.get("lit_crystals")
            self._reduced_crystal_frames = self._reduced_crystal_frames+1 if type(crystals) is int and 0 < crystals < self.turn_limit else 0
            if self._reduced_crystal_frames >= 2:
                self._crystal_reset_armed = True
            # The boss versus screen or Skip cutscene after a played Phase 4 turn announces the grey wave.
            if (self.phase == Phase.P4 and self.turns_completed >= 1
                    and (obs.get("intro_skip") is True or obs.get("boss_vs") is True)):
                self._cutscene_armed = True
            planned_kill = self._p3_planned_kill()
            if ((self._crystal_reset_armed or self._wave_spawn_armed or self._cutscene_armed
                    or planned_kill) and crystals == self.turn_limit
                    # A wave can finish before its last action is confirmed.
                    # Do not make phase recognition depend on that action audit.
                    and obs.get("turn_mode") == "player" and obs.get("stable") is True
                    and obs.get("queue_verified") is True and obs.get("empty_slots") == 4
                    and obs.get("hand") is not None
                    and p in (None, self.phase, self.phase + 1)):
                next_phase = int(self.phase) + 1
                confidence = obs.facts["lit_crystals"].confidence
                evidence = obs.frame + (f":new messenger wave + {self.turn_limit} crystals + fresh player queue"
                                        if self._wave_spawn_armed else
                                        f":crystals reset to {self.turn_limit} + fresh player queue"
                                        if self._crystal_reset_armed else
                                        f":boss intro + {self.turn_limit} crystals + fresh player queue"
                                        if self._cutscene_armed else
                                        f":planned Phase 3 kill + enemy turn + {self.turn_limit} crystals + fresh player queue")
                if planned_kill and not (self._crystal_reset_armed or self._wave_spawn_armed
                                         or self._cutscene_armed):
                    # Crystals never visibly dropped: the wave died in turn 1.
                    obs.facts["p3_kill_inference"] = Fact(True,confidence,obs.time,evidence,"inferred")
                obs.facts["phase"] = Fact(next_phase,confidence,obs.time,evidence,"inferred")
                obs.facts["wave_transition"] = Fact(True,confidence,obs.time,evidence,"inferred")
                obs.facts["phase_crystal_reset"] = Fact(True,confidence,obs.time,evidence,"inferred")
                if self._wave_spawn_armed:
                    obs.facts["phase_spawn_transition"] = Fact(True,confidence,obs.time,evidence,"inferred")
                if next_phase == 5:
                    obs.facts["grey_crystal_reset"] = Fact(True,confidence,obs.time,evidence,"inferred")
                if next_phase == 2:
                    obs.facts["phase2_crystal_reset"] = Fact(True,confidence,obs.time,evidence,"inferred")
                p = next_phase
        # New P1 must be positively established; banners need wave evidence.
        eligible = (p == 1 and self.phase is None and obs.get("new_battle") is True
                    or p in (2, 3, 4) and obs.get("wave_transition") is True
                    or p == 5 and self.phase == Phase.P4 and (
                        obs.get("grey_crystal_reset") is True
                        and obs.facts["grey_crystal_reset"].seen == obs.time
                        or obs.get("grey_context") is True
                        and (self._cutscene_armed
                             or obs.get("gauge_anchor") is True and obs.get("gauge") == 50)
                        and all(obs.facts.get(key, Fact()).seen == obs.time
                                for key in ("phase", "grey_context")))
                    or p == 6 and self.phase == Phase.GREY and obs.get("final_hud") is True)
        if p == self.phase and self.phase is not None:
            eligible = True
            self._transition_target = None
        if p in list(Phase) and eligible:
            if p != self.phase:
                self._transition_target = p
            self._phase_frames = self._phase_frames + 1 if p == self._phase_candidate else 1
            self._phase_candidate = p
            if self._phase_frames >= 2 and p != self.phase:
                if self.phase is not None and p != self.phase + 1:
                    self.abort_reason = "UNEXPECTED_PHASE_TRANSITION"
                else:
                    if self.pending and self.pending["action"]["kind"] not in (
                            "talent", "weakening", "strengthening", "destruction", "heal"):
                        self.superseded_actions.append(dict(
                            self.pending, phase=self.pending.get("phase", self.phase),
                            turn=self.pending.get("turn", self.turns_completed),
                            outcome="superseded", transition_evidence=obs.frame))
                        self.pending = None
                    self.phase = Phase(p)
                    self._transition_target = None
                    self.phase_counter = int(p)
                    self._turn_crystals = obs.get("lit_crystals")
                    self._reduced_crystal_frames = 0
                    self._crystal_reset_armed = False
                    self._wave_spawn_armed = False
                    self._cutscene_armed = False
                    self.turns_completed = 0
                    self._turn_mode = self._turn_candidate = None
                    self._turn_frames = 0
                    self._turn_queued = self._enemy_boundary = False
                    self.queue.clear()
                    # Preserve pending activations and their original causal evidence.
                    # Reconciliation must never attach them to the new queue.
                    self.menu_slots = None
        else:
            self._phase_frames = 0
            self._phase_candidate = None
        # Weakening's visible menu state governs the P3 opening. Percentage
        # OCR must not block opening that menu or verifying its effect.
        self.guard.update(obs, self.phase, enforce=False)
        gauge = obs.facts.get("gauge",Fact())
        if (self.phase == Phase.P4 and self.p4_entry_gauge is None
                and obs.get("gauge_anchor") is True and gauge.seen == obs.time
                and type(obs.get("gauge")) in (int,float)):
            self.p4_entry_gauge = obs.get("gauge")
        red = obs.facts.get("red_wave", Fact())
        red_confirmed = (self.phase in (Phase.P4,Phase.GREY) and obs.get("red_wave") is True
                         and red.seen == obs.time and obs.get("gauge_anchor") is True
                         and type(obs.get("gauge")) in (int,float) and obs.get("gauge") > 50)
        self._red_wave_frames = self._red_wave_frames+1 if red_confirmed else 0
        if self._red_wave_frames >= 2:
            self.abort_reason = "RED_WAVE_HIGH_GAUGE"
        if self.phase == Phase.FINAL:
            portrait = obs.get("final_portrait")
            fact = obs.facts.get("final_portrait", Fact())
            fresh = (portrait in ("tarmiel","ludociel","mael","sariel")
                     and fact.seen == obs.time and obs.get("final_hud") is True)
            if fresh:
                if portrait != self.final_enemy:
                    self.final_enemy = None
                self._final_enemy_frames = self._final_enemy_frames+1 if portrait == self._final_enemy_candidate else 1
                self._final_enemy_candidate = portrait
                if self._final_enemy_frames >= 2:
                    self.final_enemy = portrait
            else:
                self._final_enemy_candidate = None
                self._final_enemy_frames = 0
                # Keep confirmed identity through menu/animation occlusion.
                # A positive conflicting portrait clears it immediately above.
        if self.guard.abort_reason:
            self.abort_reason = self.guard.abort_reason
        mode = obs.get("turn_mode")
        if mode in ("player", "enemy"):
            self._turn_frames = self._turn_frames + 1 if mode == self._turn_candidate else 1
            self._turn_candidate = mode
            if self._turn_frames >= 2 and mode != self._turn_mode:
                if mode == "enemy" and self._turn_mode == "player":
                    self._enemy_boundary = self._turn_queued or obs.get("queue_executed") is True
                if self._turn_mode == "enemy" and mode == "player" and self._enemy_boundary:
                    self.turns_completed += 1
                    self._turn_crystals = obs.get("lit_crystals")
                    self.queue.clear()
                    self._turn_queued = self._enemy_boundary = False
                self._turn_mode = mode
        else:
            self._turn_frames = 0
        self.reconcile_completed_turn(obs)
        result = ("complete" if obs.get("complete") is True else
                  "failed" if obs.get("failed") is True else None)
        self._result_frames = self._result_frames + 1 if result == self._result_candidate else 1
        self._result_candidate = result
        if result and self._result_frames >= 2 and obs.get("result_screen") is True:
            self.result = result
        # Victory is assigned by ResultFlow only AFTER verified return.

    def reconcile_completed_turn(self, obs):
        """Also run after a late fourth-action confirmation in the same frame."""
        crystals = obs.get("lit_crystals")
        if (obs.get("turn_mode") == "player" and obs.get("stable") is True
                and obs.get("queue_verified") is True and obs.get("empty_slots") == 4
                and obs.get("hand") is not None and type(crystals) is int):
            if (type(self._turn_crystals) is int and crystals == self._turn_crystals-1
                    and self.pending is None and len(self.queue) == 4):
                # Recover a missed enemy banner only after all four actions
                # have been confirmed, including the last pending action.
                self.turns_completed += 1
                self.queue.clear()
                self._turn_queued = self._enemy_boundary = False
                self._turn_mode = self._turn_candidate = "player"
                self._turn_crystals = crystals
            elif self._turn_crystals is None:
                self._turn_crystals = crystals


from utilities.supreme_deity_v1_policy import V1Planner as Planner


class ResultFlow:
    def __init__(self, timeout=20):
        self.timeout = timeout
        self.started = None
        self.clicked = False
        self.exit_frames = 0
        self.done = False

    def step(self, obs, result):
        if self.done:
            return None
        if self.started is None:
            self.started = obs.time
        if obs.get("battle_exited") is True:
            self.exit_frames += 1
            self.done = self.exit_frames >= 2
            return None
        self.exit_frames = 0
        if obs.time - self.started > self.timeout:
            raise Unsafe("RESULT_EXIT_TIMEOUT")
        if not self.clicked and obs.get(result) is True and obs.get("result_screen") is True:
            self.clicked = True
            return dict(kind="result", control="result_ok" if result == "complete" else "failed_ok")
        return None


class ForfeitFlow:
    """One bounded, observed pause -> forfeit -> confirmation -> exit transaction."""
    def __init__(self, timeout=20., max_clicks=6, exit_timeout=60.):
        self.timeout, self.max_clicks = timeout, max_clicks
        self.exit_timeout = exit_timeout
        self.started = None
        self.clicks = 0
        self.last_control = None
        self.last_control_time = None
        self.exit_frames = 0
        self.done = False

    def step(self, obs):
        if self.done:
            return None
        if self.started is None:
            self.started = obs.time
        if obs.get("battle_exited") is True:
            self.exit_frames += 1
            if self.exit_frames >= 2:
                self.done = True
            return None
        self.exit_frames = 0
        if self.last_control == "forfeit_confirm":
            # Confirmation starts a separate loading/return transaction. Never
            # send more inputs while waiting; exit still needs two observations.
            if obs.time-self.last_control_time > self.exit_timeout:
                raise Unsafe("FORFEIT_UI_TIMEOUT: battle exit unverified; stop safely")
            return None
        progress_at = self.last_control_time if self.last_control_time is not None else self.started
        if obs.time - progress_at > self.timeout:
            raise Unsafe("FORFEIT_UI_TIMEOUT: battle exit unverified; stop safely")
        control = ("forfeit_confirm" if obs.get("forfeit_confirmation") is True else
                   "forfeit" if obs.get("pause_menu") is True else
                   "menu_close" if obs.get("stigma_menu") is True else
                   "pause" if obs.get("pause_actionable") is True else None)
        # Never repeatedly toggle pause or blindly repeat a destructive button.
        retry_pause = (control == self.last_control == "pause"
                       and self.last_control_time is not None
                       and obs.time-self.last_control_time >= 2
                       and obs.get("gauge_anchor") is True
                       and obs.get("queue_verified") is True
                       and obs.get("turn_mode") == "player"
                       and obs.get("stigma_menu") is False)
        if control and (control != self.last_control or retry_pause):
            if self.clicks >= self.max_clicks:
                raise Unsafe("FORFEIT_UI_TIMEOUT: maximum reset inputs reached")
            self.last_control = control
            self.last_control_time = obs.time
            self.clicks += 1
            return {"kind": "forfeit", "control": control}
        return None
