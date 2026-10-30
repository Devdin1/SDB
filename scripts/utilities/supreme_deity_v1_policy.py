"""Desktop-free V1 policy. Actions are proposals, never assumed successes."""

LINEUP = ["Odin", "LR Freyr", "Hel", "Gawain"]
CARD_IDENTITIES = {
    name: dict(id=name, skill=name, owner=owner, ultimate=suffix == "ult",
               target_type="st" if name in ("odin_1", "freyr_1", "freyr_2", "freyr_ult", "gawain_1") else "aoe",
               kind="debuff" if name in ("hel_2", "freyr_2") else "attack")
    for prefix, owner in zip(("odin", "freyr", "hel", "gawain"), LINEUP)
    for suffix in ("1", "2", "ult")
    for name in (prefix + "_" + suffix,)
}
NORMAL_ST = ("odin_1", "freyr_1", "freyr_2", "gawain_1")
NORMAL_AOE = ("odin_2", "gawain_2", "hel_1", "hel_2")
FINAL_PRIORITY = (("odin_ult",), ("gawain_ult",), ("freyr_ult",), ("hel_ult",),
                  ("odin_1", "odin_2"), ("gawain_1", "gawain_2"),
                  ("freyr_1", "freyr_2"), ("hel_1", "hel_2"))


def card_category(card):
    definition = CARD_IDENTITIES.get(card.get("id"), card)
    return "ultimate" if definition.get("ultimate") else definition.get("kind")


class V1Planner:
    def __init__(self, config):
        from utilities.supreme_deity_core import Unsafe
        if config.get("route", "v1") != "v1":
            raise Unsafe("Only Supreme Deity V1 is supported")
        self.config = config

    def plan(self, obs, state):
        from utilities.supreme_deity_core import Phase, Unsafe
        if state.abort_reason or state.stopped_reason or not state.guard.allowed:
            raise Unsafe("Battle input suspended by safety guard")
        if obs.get("red_wave") is True:
            raise Unsafe("Red wave candidate; suspend battle input while confirming reset")
        if state.phase is None or state.transition_pending or obs.get("stable") is not True or state.pending:
            raise Unsafe("Phase/scene/action not stable")
        menu_open = obs.get("stigma_menu") is True
        if (obs.get("turn_mode") != "player" and not menu_open) or state._turn_mode != "player":
            raise Unsafe("Not a confirmed player turn")
        slots = obs.get("empty_slots")
        if not menu_open and (type(slots) is not int or not 1 <= slots <= 4 or obs.get("queue_verified") is not True):
            raise Unsafe("No verified free action slots")
        if menu_open and state.menu_slots is None and slots is None:
            raise Unsafe("Stigma menu lacks a verified pre-opening queue snapshot")
        turn, step = state.turns_completed + 1, len(state.queue)
        if step >= 4:
            raise Unsafe("Four actions confirmed; waiting for verified next turn or phase")
        phase = state.phase

        def ui(kind, post=None, **kw):
            return [dict(kind=kind, control=kind, post=post or kind + "_effect", **kw)]

        def stigma(name, mandatory=False):
            key = (int(phase), turn, name)
            if key in state.extras:
                if obs.get("stigma_menu") is True:
                    return ui("menu_close", "stigma_closed")
                if obs.get("stigma_closed") is not True:
                    raise Unsafe("Reacquire actionable battle UI after Stigma")
                return None
            if obs.get("stigma_menu") is not True:
                if obs.get("stigma_closed") is not True:
                    raise Unsafe("Stigma menu context unknown")
                if not mandatory:
                    opening = (int(phase), turn, "stigma_open")
                    started = state.optional_unknown_since.setdefault(opening, obs.time)
                    if obs.time-started >= self.config.get("optional_stigma_open_seconds", 8):
                        # Optional final-boss menu detection must not stall attacks
                        # indefinitely. This records a skip, never an activation.
                        state.extras.add(key)
                        return None
                return ui("stigma_open", "stigma_menu")
            available = obs.get(name + "_available")
            if available is False:
                if mandatory:
                    state.abort_reason = "MANDATORY_WEAKENING_UNAVAILABLE"
                    raise Unsafe(state.abort_reason)
                return ui("menu_close", "stigma_closed", skip_extra=name)
            if available is not True:
                if not mandatory:
                    started = state.optional_unknown_since.setdefault(key, obs.time)
                    if obs.time-started >= self.config.get("optional_stigma_reacquire_seconds", 2):
                        return ui("menu_close", "stigma_closed", skip_extra=name,
                                  reason="Optional Stigma availability remained unknown; no activation claimed")
                raise Unsafe(name + " availability unknown in open menu")
            return ui(name)

        if phase == Phase.P3:
            p3_weakening_confirmed = any(e["phase"] == 3 and e["turn"] == 1
                                        and e["action"]["kind"] == "weakening" for e in state.history)
            if turn == 1 and not p3_weakening_confirmed and (3, 1, "aoe_route") not in state.extras:
                action = stigma("weakening")
                if action:
                    if action[0].get("skip_extra") == "weakening":
                        action[0]["skip_extra"] = "aoe_route"
                    action[0]["p3_optional"] = True
                    return action
                state.extras.add((3, 1, "aoe_route"))
            if menu_open:
                return ui("menu_close", "stigma_closed")
            if not p3_weakening_confirmed and (3, 1, "aoe_route") not in state.extras:
                raise Unsafe("P3 strategy unknown: no confirmed Weakening or alternate-route decision")
        if (phase == Phase.FINAL and turn == 2 and step == 0
                and state.final_enemy in (None, "tarmiel")
                and state.final_repeat_risk(1) & {"Odin", "Gawain"}):
            action = stigma("heal")
            if action:
                return action
        if phase == Phase.FINAL and turn in (1, 2) and step == 0:
            opening = (6, turn, "opening_stigma")
            if opening not in state.extras:
                if not menu_open:
                    if obs.get("stigma_closed") is not True:
                        raise Unsafe("Stigma menu context unknown")
                    started = state.optional_unknown_since.setdefault((6, turn, "stigma_open"), obs.time)
                    if obs.time-started < self.config.get("optional_stigma_open_seconds", 8):
                        return ui("stigma_open", "stigma_menu")
                    state.extras.add(opening)  # Skip, never assume activation.
                else:
                    for name in ("weakening", "strengthening"):
                        if obs.get(name + "_available") is True:
                            return ui(name, skip_extra="opening_stigma")
                    known_unavailable = all(obs.get(name + "_available") is False
                                            for name in ("weakening", "strengthening"))
                    started = state.optional_unknown_since.setdefault(opening, obs.time)
                    if (known_unavailable or obs.time-started >=
                            self.config.get("optional_stigma_reacquire_seconds", 2)):
                        return ui("menu_close", "stigma_closed", skip_extra="opening_stigma",
                                  reason="No positively available opening Stigma; continue cards")
                    raise Unsafe("Reacquire optional Weakening/Strengthening availability")
            if menu_open:
                return ui("menu_close", "stigma_closed")
        if phase == Phase.FINAL and turn in (3, 4):
            action = stigma("destruction" if turn == 3 else "heal")
            if action:
                return action
        p4_high_entry = phase == Phase.P4 and state.p4_entry_gauge is not None and state.p4_entry_gauge >= 10
        p4_weakening_confirmed = any(e["phase"] == 4 and e["action"]["kind"] == "weakening" for e in state.history)
        if phase == Phase.P4 and state.p4_entry_gauge is None and not p4_weakening_confirmed:
            raise Unsafe("Reacquire Phase 4 entry gauge before choosing the strategy")
        if p4_high_entry and turn >= 2 and not p4_weakening_confirmed:
            state.extras.add((4,turn,"weakening_opening"))
            action = stigma("weakening")
            if not action or action[0].get("skip_extra") == "weakening":
                state.abort_reason = "P4_ENTRY_GAUGE_NO_WEAKENING"
                raise Unsafe("Phase 4 entered at 10% or higher without confirmed Weakening; reset")
            action[0]["p4_required"] = True
            return action
        p4_opening = phase == Phase.P4 and 2 <= turn <= state.turn_limit
        p4_route = (4, turn, "weakening_opening")
        p4_declined = (4, turn, "weakening_opening_declined")
        if p4_opening:
            used_before = any(e["phase"] == 4 and e["turn"] < turn
                              and e["action"]["kind"] == "weakening" for e in state.history)
            if (step == 0 and not used_before and obs.get("p4_weakening_ready") is True
                    and p4_declined not in state.extras):
                state.extras.add(p4_route)
            if p4_declined in state.extras and menu_open:
                return ui("menu_close", "stigma_closed")
            if p4_route in state.extras and p4_declined not in state.extras:
                activated = any(e["phase"] == 4 and e["turn"] == turn
                                and e["action"]["kind"] == "weakening" for e in state.history)
                if not activated:
                    action = stigma("weakening")
                    if action:
                        action[0]["p4_optional"] = True
                        if action[0].get("skip_extra") == "weakening":
                            action[0]["skip_extra"] = "weakening_opening_declined"
                        return action
                    # Optional menu/availability failed: retain the existing P4 strategy.
                    state.extras.add(p4_declined)
                else:
                    if menu_open:
                        return ui("menu_close", "stigma_closed")
                    targeted = any(e["phase"] == 4 and e["turn"] == turn
                                   and e["action"]["kind"] == "target"
                                   and e["action"].get("target") == "center" for e in state.history)
                    if not targeted:
                        return [dict(kind="target", target="center", control="target_center", confirm_target=False)]
        talent = (phase == Phase.P1 and turn == 2 or phase == Phase.GREY and turn == 1)
        talent = talent or (phase == Phase.P3 and obs.get("talent_ready") is True)
        if talent and (int(phase), turn, "talent") not in state.extras:
            if obs.get("talent_ready") is not True or obs.get("talent_effect") is True:
                raise Unsafe("Required Talent not recognized as ready")
            return ui("talent")
        if obs.get("stigma_closed") is not True:
            raise Unsafe("Battle menu is not confirmed closed")

        def lock():
            unused = obs.get("unused_slots")
            if not unused:
                raise Unsafe("Unused queue slot positions unknown")
            return [dict(kind="lock", slot=unused[0], control="slot_" + str(unused[0]))]

        hand = obs.get("hand")
        if not hand:
            if phase == Phase.FINAL:
                return lock()
            raise Unsafe("Reacquire hand identities, ranks and disabled states")

        reserve_index = None
        if phase == Phase.P3:
            reserves = [(i,c) for i,c in enumerate(hand) if c.get("disabled") is False
                        and c.get("rank") in (0,1,2)
                        and (c.get("id") == "odin_1" or c.get("id") == "freyr_1" and c["rank"] >= 1)]
            if reserves:
                # Keep a qualified Freyr first, otherwise one Odin ST, across
                # ordinary damage selections. Recompute after each hand change.
                reserve_index = min(reserves,key=lambda p:(p[1]["id"] != "freyr_1",p[1]["rank"],p[0]))[0]

        def choose(skills, required=True, minimum_rank=0, strongest=False, stance_cancel=False):
            options = [(i, c) for i, c in enumerate(hand)
                       if c.get("id") in skills and c.get("disabled") is False
                       and c.get("rank") in (0, 1, 2, 100)
                       and c["rank"] >= minimum_rank]
            if phase == Phase.P3 and not stance_cancel:
                options = [(i,c) for i,c in options if i != reserve_index]
            if phase != Phase.FINAL:
                counts = {}
                for queued in state.queue:
                    if queued['kind'] == 'card':
                        category = card_category(queued['card'])
                        counts[category] = counts.get(category, 0) + 1
                safe = [(i, c) for i, c in options
                        if card_category(c) is not None and counts.get(card_category(c), 0) < 2]
                options = safe
            if phase == Phase.FINAL:
                options = [(i,c) for i,c in options
                           if (turn,c.get("id")) not in state.final_failed_skills]
                if state.final_enemy in (None, "tarmiel"):
                    used_owners = {CARD_IDENTITIES.get(a["card"].get("id"),{}).get("owner")
                                   for a in state.queue if a["kind"] == "card"}
                    options = [(i,c) for i,c in options
                               if CARD_IDENTITIES.get(c.get("id"),{}).get("owner") not in used_owners]
            if not options:
                if required:
                    return fallback()
                return None
            # Configurable rank preference; equal-rank ties use current leftmost position.
            i, c = min(options, key=lambda p: ((-1 if strongest or self.config.get("higher_rank_first", True) else 1)
                                               * p[1]["rank"], p[0]))
            target = ("center" if p4_opening
                      and p4_route in state.extras and p4_declined not in state.extras
                      and (CARD_IDENTITIES.get(c.get("id"), c).get("target_type") == "st"
                           or c.get("id") == "gawain_2") else None)
            return [dict(kind="card", index=i, card=c, target=target, **({"confirm_target": False} if target == "center" else {}))]

        def move(owner, required=True):
            candidates = []
            for i, c in enumerate(hand):
                if CARD_IDENTITIES.get(c.get("id"), {}).get("owner") != owner:
                    continue
                for j in range(len(hand)):
                    if i == j:
                        continue
                    shifted = list(hand)
                    shifted.insert(j, shifted.pop(i))
                    merge = any(a.get("id") == b.get("id") and a.get("rank") == b.get("rank")
                                and a.get("rank") in (0, 1) for a, b in zip(shifted, shifted[1:]))
                    candidates.append((merge, i, j))
            if not candidates:
                if not required:
                    return None
                raise Unsafe("Required " + owner + " movement unavailable")
            if phase == Phase.P4:
                # Use nearby card movements, like the early-phase adjacent moves.
                # Keep the existing merge avoidance and mouse drag behavior.
                slot = lambda index: hand[index].get("hand_slot") if type(hand[index].get("hand_slot")) is int else index
                merge, i, j = min(candidates, key=lambda c: (c[0], abs(slot(c[1])-slot(c[2])), c[1], c[2]))
            else:
                merge, i, j = min(candidates)
            return [dict(kind="move", indices=[i, j], owner=owner, merge_possible=merge)]

        def fallback():
            # Spend spare cards while preserving Odin/Gawain AoEs for the route.
            return (choose(("hel_1", "hel_2", "gawain_1", "freyr_2"), False)
                    or move("Odin", False) or move("Gawain", False)
                    or move("LR Freyr", False) or move("Hel", False) or lock())

        if phase == Phase.P1:
            if turn == 1:
                return move("Odin")
            if turn == 2:
                return choose(("freyr_1",)) if step == 0 else choose(("odin_2",)) if step == 1 else move("Gawain")
            return fallback()
        if phase == Phase.P2:
            if turn == 1:
                return choose((("odin_ult",), ("gawain_1",), ("hel_2",), ("hel_1",))[step])
            if turn == 2:
                used = {}
                for queued in state.queue:
                    if queued["kind"] == "card":
                        skill = queued["card"]["id"]
                        used[skill] = used.get(skill, 0) + 1
                for skill, limit in (("freyr_2", 2), ("hel_1", 1), ("odin_1", 1)):
                    if used.get(skill, 0) < limit:
                        selected = choose((skill,), False)
                        if selected:
                            return selected
                return move("Gawain", False) or lock()
            return fallback()
        if phase == Phase.P3:
            # Enemy clicks toggle selection. Click only at the T1 opening;
            # later turns/Talent uses verify the blue crest without re-clicking.
            clicked_right = any(e["phase"] == 3 and e["action"]["kind"] == "target"
                                and e["action"].get("target") == "right" for e in state.history)
            selected_target = obs.get("selected_target")
            if (turn == 1 and step == 0 and not clicked_right and selected_target != "right"
                    and obs.get("p3_right_visible") is True):
                if obs.get("p3_right_selection_candidate") is True:
                    raise Unsafe("P3 selection confirmation pending; do not toggle a potentially selected target")
                return [dict(kind="target", target="right", control="target_right", confirm_target=False)]

            def p3_st(skills=NORMAL_ST):
                selected = choose(skills, False, strongest=True)
                if selected:
                    if selected_target != "right":
                        if turn == 1 and step == 0:
                            raise Unsafe("P3 far-right selection not visually verified at opening; wait without clicking again")
                        # The selected side enemy may already be defeated.
                        # This is not a lost phase/turn: skip ST and continue
                        # AoEs, scheduled ultimates, or moves without re-clicking.
                        return None
                    selected[0].update(target="right", confirm_target=True)
                return selected

            def p3_move():
                return (move("Gawain", False) or move("Hel", False)
                        or move("Odin", False) or move("LR Freyr", False) or lock())

            cancel_queued = any(a["kind"] == "card" and (
                a["card"]["id"] == "gawain_2"
                or a.get("target") == "right" and (a["card"]["id"] == "odin_1"
                    or a["card"]["id"] == "freyr_1" and a["card"]["rank"] >= 1)) for a in state.queue)
            if obs.get("p3_right_stance") is True and not cancel_queued:
                if selected_target == "right":
                    cancel = (choose(("freyr_1",), False, minimum_rank=1, stance_cancel=True)
                              or choose(("odin_1",), False, stance_cancel=True))
                    if cancel:
                        cancel[0].update(target="right",confirm_target=True,purpose="p3_stance_cancel")
                        return cancel
                cancel = choose(("gawain_2",), False, stance_cancel=True)
                if cancel:
                    cancel[0]["purpose"] = "p3_stance_cancel"
                    return cancel
                # Do not dump ultimates into known immortality. Keep the turn
                # moving without exceeding attack/debuff limits or re-targeting.
                return p3_move()

            if p3_weakening_confirmed:
                return (choose(("gawain_2",), False)
                        or choose(("hel_1", "hel_2", "odin_2"), False)
                        or choose(("gawain_ult", "hel_ult", "odin_ult"), False)
                        or move("Gawain", False) or move("Odin"))

            attacks = sum(a["kind"] == "card" and card_category(a["card"]) == "attack"
                          for a in state.queue)

            def p3_aoe(strong_first=False):
                # The second normal attack should be Gawain when held: its
                # reflect protection matters more than rank on a possible kill.
                if attacks == 1:
                    selected = choose(("gawain_2",), False, strongest=True)
                    if selected:
                        return selected
                if strong_first:
                    gawains = sum(c.get("id") == "gawain_2" and c.get("disabled") is False
                                  and c.get("rank") in (0, 1, 2) for c in hand)
                    if gawains == 1:
                        selected = choose(("odin_2",), False, strongest=True)
                        if selected:
                            return selected
                    selected = choose(("odin_2", "gawain_2"), False, strongest=True)
                    if selected:
                        return selected
                # While an attack slot remains, prefer attacks over Hel's
                # debuff. Each category is still capped at two for the turn.
                return (choose(("odin_2", "gawain_2"), False, strongest=True)
                        or choose(("hel_1",), False)
                        or choose(("hel_2",), False))

            if turn < state.turn_limit:
                if turn == 1 and step == 0:
                    selected = choose(("odin_2",), False, strongest=True) or p3_st(("odin_1",))
                    if selected:
                        return selected
                # Alternate from confirmed card uses, not queue slot numbers:
                # moves do not change the preferred type. Start later turns
                # with ST, retaining the T1 Odin AoE opening preference.
                normal_cards = [a["card"]["id"] for a in state.queue
                                if a["kind"] == "card"
                                and a["card"]["id"] in NORMAL_ST + NORMAL_AOE]
                want_aoe = bool(normal_cards and normal_cards[-1] in NORMAL_ST)
                first_aoe = not any(skill in NORMAL_AOE for skill in normal_cards)
                if want_aoe:
                    return p3_aoe(strong_first=first_aoe) or p3_st() or p3_move()
                return p3_st() or p3_aoe(strong_first=first_aoe) or p3_move()
            if turn == state.turn_limit:
                if step == 0:
                    return p3_aoe(strong_first=True) or p3_st() or p3_move()
                if step == 1:
                    return p3_aoe() or p3_st() or p3_move()
                if step == 2:
                    return choose(("gawain_ult",), False) or p3_st() or p3_move()
                return choose(("hel_ult",), False) or p3_st() or p3_move()
            # Continue after the planned kill turn. Use protected finishing
            # damage first, retaining all category and disabled-card checks.
            return (choose(("gawain_ult",), False) or choose(("gawain_2",), False)
                    or p3_aoe(strong_first=True) or p3_st() or p3_move())
        if phase == Phase.P4:
            if p4_opening and p4_route in state.extras and p4_declined not in state.extras:
                # Normal ST attacks and debuffs each use the existing two-card
                # category cap. Missing resources/third cards become moves.
                if step == 0:
                    for first in (("odin_1",), ("freyr_1",), ("gawain_2",)):
                        selected = choose(first, False)
                        if selected:
                            return selected
                return (choose(NORMAL_ST, False) or choose(("hel_2",), False)
                        or move("Odin", False) or move("LR Freyr", False)
                        or move("Hel", False) or move("Gawain"))
            if state.turn_limit > 4 and turn > 4:
                # Hard's spare turn uses disposable fillers rather than the
                # Odin/Gawain AoEs, ultimates or Freyr stance remover for later.
                return fallback()
            if 1 <= turn <= state.turn_limit:
                # Reserve Odin/Gawain attacks and AoE ultimates for Grey.
                # The last two slots build Odin gauge through verified moves.
                if step < 2:
                    selected = choose(("freyr_1", "freyr_2", "hel_1", "hel_2"), False)
                    selected = selected or choose(("gawain_1",), False)
                    if selected:
                        return selected
                    if not any(a["kind"] == "card" for a in state.queue):
                        selected = choose(("gawain_2", "freyr_ult", "hel_ult"), False)
                        if selected:
                            return selected
                return (move("Odin", False) or move("LR Freyr", False)
                        or move("Hel", False) or move("Gawain"))
            return fallback()
        if phase == Phase.GREY:
            # Keep burst damage on every turn, including recovery after T1.
            # Ultimates remain limited to two per turn by choose().
            for skills in (("odin_ult",), ("gawain_ult",), ("hel_ult",), ("freyr_ult",),
                           ("odin_2",), ("gawain_2",), ("hel_1", "hel_2")):
                selected = choose(skills, False)
                if selected:
                    return selected
            return fallback()
        if phase == Phase.FINAL:
            def final_move():
                return (move("Gawain", False) or move("Odin", False)
                        or move("LR Freyr", False) or move("Hel", False) or lock())
            if state.final_force_move:
                return final_move()
            # Ranks are zero-based here: silver=1. Gawain is a conditional
            # passive-based fallback, never proof that the stance was removed.
            cancel_queued = any(a["kind"] == "card" and (
                a["card"]["id"] == "freyr_1" and a["card"]["rank"] >= 1
                or a["card"]["id"] == "gawain_2") for a in state.queue)
            if obs.get("final_stance") is True and not cancel_queued:
                cancel = choose(("freyr_1",), False, minimum_rank=1) or choose(("gawain_2",), False)
                if cancel:
                    return cancel
            priorities = self.config.get("final_later_priority", FINAL_PRIORITY) if turn >= 3 else FINAL_PRIORITY
            for skills in priorities:
                # Configuration cannot introduce unknown/unrequested cards.
                legal = tuple(s for s in skills if s in {v for group in FINAL_PRIORITY for v in group})
                selected = choose(legal, False)
                if selected:
                    return selected
            return final_move()
        raise Unsafe("Unknown phase")
