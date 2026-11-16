"""V1 screenshot detectors, with unknown retained when a cue cannot be verified.

All rectangles are in the profile's canonical screenshot, never desktop coordinates.
Supplied artwork provides identity only; border rank and disabled state are separate.
"""
import cv2
import numpy as np
from utilities.supreme_deity_core import Fact
from utilities.supreme_deity_v1_policy import CARD_IDENTITIES


class V1Detectors:
    def __init__(self, perception):
        self.p = perception
        self.reset()

    def reset(self):
        self._hand_cache = {}
        self.phase = None
        self.banner = None
        self.previous_slots = None
        self.menu_seen = False
        self.activated = set()
        self.available_seen = set()
        self.spent = set()
        self.armed = set()
        self.pause_menu_seen = False
        self._grey_frames = 0
        self._grey_time = None
        self._stigma_phase = None
        self._p3_selection_frames = 0
        self._p3_selection_time = None

    def _confirm_grey(self, now, cue):
        if self._grey_time != now:
            self._grey_frames = self._grey_frames + 1 if cue else 0
            self._grey_time = now
        return cue and self._grey_frames >= 2

    def detect_wrong_team(self, im, now, frame, facts):
        setup = facts.get("setup_screen", Fact())
        if not setup.known(now) or setup.value is not True:
            return
        wrong_slots = []
        for slot in range(4):
            expected = facts.get(f"setup_owner_{slot}", Fact())
            if expected.known(now) and expected.value is True:
                continue
            detector = self.p.profile.get("detectors", {}).get(f"setup_owner_{slot}")
            if not detector:
                continue
            scores = [(self.p.match(im, f"setup_owner_{identity}", detector["roi"])[0], identity)
                      for identity in range(4)]
            for reference in self.p.profile.get("wrong_team_portraits", []):
                template = reference["template"]
                scores.append((self.p.match(im, template, detector["roi"])[0], template))
            scores.sort(key=lambda item: item[0], reverse=True)
            score, identity = scores[0]
            # Missing/occluded artwork is unknown, never a negative identity.
            # A recognized unit in another unit's slot proves a wrong lineup.
            if (identity != slot and score >= detector.get("threshold", .97)
                    and score-scores[1][0] >= .01):
                wrong_slots.append({"slot": slot, "recognized_unit": identity, "confidence": score})
        if wrong_slots:
            facts["setup_wrong_team"] = Fact(True, min(s["confidence"] for s in wrong_slots),
                                            now, frame + ":wrong ordered portrait", "observed")
            facts["setup_wrong_slots"] = Fact(wrong_slots, .99, now, frame, "observed")
            facts["setup_verified"] = Fact(False, .99, now, frame + ":wrong team", "inferred")

    def observe(self, im, now, frame, facts):
        def put(key, value, confidence=.99, evidence=""):
            facts[key] = Fact(value, confidence, now, frame + ":" + (evidence or key), "observed")

        def hit(name, roi, threshold=.96):
            score, rect = self.p.match(im, name, roi)
            return rect if score >= threshold else None

        def known(key):
            f = facts.get(key, Fact())
            return f.value if f.known(now) else None

        if self.phase in (4, 6) and self._stigma_phase != self.phase:
            # Earlier-wave Weakening evidence cannot confirm another activation.
            self.available_seen.clear()
            self.spent.clear()
            self.activated.clear()
            self.armed.clear()
            self._stigma_phase = self.phase
        top = [0, 0, 1, .12]
        bottom = [0, .68, 1, .32]
        # This is a turn counter, NOT a phase ID. Only BattleState may use a
        # reduced -> four reset, together with a fresh stable player queue.
        scores = []
        for count, names in ((1, ("one_crystal_live",)),
                             (2, ("2_turns_to_go", "two_crystals_live")),
                             (3, ("3_turns_to_go", "three_crystals_live")),
                             (4, ("phase2_confirm", "4_turns_to_go"))):
            score = max(self.p.match(im, name, [0,.12,.18,.055])[0] for name in names)
            scores.append((score,count))
        scores.sort(reverse=True)
        if self.p.profile.get("difficulty") == "hard":
            # Five positions must all be readable. A four-gem substring of the
            # Hard strip is not a four-turn counter. Blue is lit, gold is empty.
            if hit("turn_label_hard", [0,.105,.18,.04], .94):
                states = []
                for index in range(5):
                    hsv = cv2.cvtColor(im[132:150,5+15*index:23+15*index], cv2.COLOR_BGR2HSV)
                    hue, sat, val = hsv[:,:,0], hsv[:,:,1], hsv[:,:,2]
                    blue = np.mean((hue > 85) & (hue < 120) & (sat > 45) & (val > 110))
                    gold = np.mean((hue > 10) & (hue < 40) & (sat > 45) & (val > 65))
                    states.append(True if blue > .25 else False if blue < .05 and gold > .12 else None)
                if None not in states and states == sorted(states, reverse=True):
                    put("lit_crystals", sum(states), .97, "five independently classified Hard crystals")
        elif scores[0][0] >= .88 and scores[0][0]-scores[1][0] >= .02:
            put("lit_crystals", scores[0][1], scores[0][0], "crystal strip")
        elif self.phase in (4, 5):
            # The grey wave tints the strip, so a lit crystal can fall below the
            # templates. Lit crystals are blue-teal; spent ones are dark gold.
            # Live: lit .69-.87 blue, spent 0 blue and ~.4 dark, in every wave.
            states = []
            for index in range(4):
                cx = int(14 + 14.5 * index)
                hsv = cv2.cvtColor(im[133:144, cx-5:cx+6], cv2.COLOR_BGR2HSV)
                hue, sat, val = hsv[:,:,0], hsv[:,:,1], hsv[:,:,2]
                blue = np.mean((hue > 85) & (hue < 125) & (sat > 35) & (val > 70))
                dark = np.mean(val < 55)
                states.append(True if blue > .5 else False if blue < .05 and dark > .2 else None)
            if None not in states and states == sorted(states, reverse=True) and any(states):
                put("lit_crystals", sum(states), .95, "tint-tolerant crystal strip")
        if hit("hand_locked_text", [0, .75, 1, .25], .95):
            put("hand_locked", True)
        # Boss versus screen ("Total CC ???" above VS) shown between waves. Live
        # scores .93-1.0 on it and under .55 on every battle frame checked.
        if hit("boss_vs_unknown", [.3, .38, .4, .25], .90):
            put("boss_vs", True, .97, "boss versus screen: Total CC ??? and VS")
        if hit("new_wave_banner_live", [.08, .32, .84, .05], .98):
            put("new_wave_banner", True, .98, "new messengers announcement")
        menu = hit("stigma_close", [.87, .67, .13, .13]) is not None
        put("stigma_menu", menu)
        if menu:
            put("scene_actionable", True)
            self.menu_seen = True
            for name, template, roi in (
                ("weakening", "stigmata_of_weakening", [.51, .75, .2, .11]),
                ("destruction", "stigmata_of_destruction", [.06, .75, .22, .11]),
                ("heal", "stigmata_heal", [.28, .75, .2, .11]),
                ("strengthening", "strengthening_enabled", [.74, .75, .22, .11])):
                if name == "strengthening" and self.phase != 6:
                    continue
                enabled = hit(template, roi, .94)
                disabled = (hit("stigmata_of_weakening_unavailable", roi, .96)
                            or hit("stigma_locked_recorded", roi, .96))
                if enabled and not disabled:
                    put(name + "_available", True)
                    self.available_seen.add(name)
                    if self.phase == 6 and name in self.spent:
                        self.spent.discard(name)
                        self.activated.discard(name)
                        self.armed.discard(name)
                    if self.phase == 6:
                        put(name + "_effect", False)
                elif disabled and not enabled:
                    put(name + "_available", False)
                    if name in self.available_seen and (self.phase != 6 or name in self.armed):
                        self.spent.add(name)
        portrait_scores = sorted(((self.p.match(im, "final_portrait_"+name, [0,0,.18,.12])[0],name)
                                  for name in ("tarmiel", "ludociel", "mael", "sariel")), reverse=True)
        final_portrait = (portrait_scores[0][1] if portrait_scores[0][0] >= .96
                          and portrait_scores[0][0]-portrait_scores[1][0] >= .02 else None)
        if final_portrait:
            put("final_portrait", final_portrait, portrait_scores[0][0], "unique final portrait match")
        final_stigma = any(hit(name, [0,.62,.23,.15], .96)
                           for name in ("final_stigma_gold_green", "final_stigma_gold_red"))
        if final_stigma:
            put("final_stigma_frame", True, .96, "gold final Stigma frame")
        final = (hit("final_hp_frame", top, .96) is not None
                 or hit("final_boss_portrait_live", [0, 0, .18, .12], .96) is not None
                 or final_portrait is not None
                 or hit("final_hp_cap_live", [.55,.025,.08,.06], .97) is not None)
        if final:
            put("final_hud", True)
            if hit("final_stance_icon", [.12, 0, .5, .10], .96):
                put("final_stance", True, .96, "yellow stance icon in final boss status row")
        enemy = hit("enemy_turn", [.1, .72, .78, .12], .94) is not None
        if enemy:
            put("turn_mode", "enemy")
            put("queue_executed", True)
        pause = hit("pause", [.88, 0, .12, .075], .94)
        if not pause and (known("gauge_anchor") is True or final):
            pause = hit("pause_button_live", [.88,0,.12,.075], .94)
        if (not pause and self.phase in (4,5) and known("gauge_anchor") is True
                and type(known("gauge")) in (int,float) and known("gauge") > 50):
            pause = hit("pause_red_live", [.88,0,.12,.075], .94)
        if pause:
            put("pause_actionable", True)
        if pause and (known("gauge_anchor") is True or
                      final and hit("last_phase_stigmata_gauge", [0,.6,.25,.2], .94)):
            put("sd_battle", True)
        skip = (hit("skip_live_bottom", [.38,.91,.25,.08], .94)
                or hit("skip", [.6,0,.4,.25], .96))
        if skip and not menu:
            put("intro_skip", True)
            put("intro_skip_rectangle", list(skip), .94, "observed Skip lettering")
        for key, template, roi in (
            ("pause_menu", "forfeit_battle", [0, .15, 1, .65]),
            ("complete", "complete", [0, .05, 1, .8]),
            ("failed", "failed", [0, .05, 1, .8]),
            ("setup_screen", "start", [0, .75, 1, .25]),
            ("register_screen", "register_coins", [0, .1, 1, .85]),
            ("apply_screen", "apply_sd", [0, .1, 1, .85]),
        ):
            if hit(template, roi, .96):
                put(key, True)
        if hit("complete_live", [.1,.12,.8,.16], .96):
            put("complete", True)
        if (hit("failed_live", [.15,.1,.7,.2], .96)
                and hit("failed_ok_live", [.2,.85,.6,.15], .94)):
            put("failed", True, .96, "FAILED heading and bottom OK button")
        if known("complete") or known("failed"):
            put("result_screen", True)
        if hit("forfeit_battle_live", [0,.15,1,.65], .96):
            put("pause_menu", True)
        if known("pause_menu"):
            self.pause_menu_seen = True
        if (self.pause_menu_seen and not known("result_screen")
                and hit("ok_forfeit", [0,.25,1,.6], .96)
                and self.p.percentage_reader.forfeit_question(im[200:800])):
            put("forfeit_confirmation", True)
        if hit("start_recorded", [0, .75, 1, .25], .96):
            put("setup_screen", True)
        if hit("start_team_live", [0,.85,1,.15], .96):
            put("setup_screen", True, .96, "live team-screen Start text")
        if known("hell_selected") is True:
            put("difficulty_selected", True)
            put("selected_difficulty", self.p.profile.get("difficulty", "hell"))
        if (known("hell_selected") is True
                and all(known(f"setup_owner_{i}") is True for i in range(4))):
            put("setup_screen", True, .97, "selected difficulty heading and four ordered team portraits")
        # Client captures can differ slightly from compressed video lettering.
        # The relaxed Start-text match is allowed only with all four ordered
        # portraits and the Hell heading independently confirmed.
        if (known("hell_selected") is True
                and all(known(f"setup_owner_{i}") is True for i in range(4))
                and hit("start", [0, .85, 1, .15], .94)):
            put("setup_screen", True)
        # Recognize the team-screen layout independently of the selected units.
        # Requiring the correct lineup here prevents wrong-team detection.
        if (known("hell_selected") is True
                and hit("setup_layout_live", [.05, .65, .90, .22], .97)
                and hit("start", [0, .85, 1, .15], .94)):
            put("setup_screen", True, .97, "Hell heading + setup controls + Start")
        self.detect_wrong_team(im, now, frame, facts)
        sd_tile = hit("battle_hub_sd_title", [.48,.25,.52,.6], .96)
        footer_battle = hit("hub_battle_icon", [.82,.86,.18,.14], .96)
        footer_anchor = (hit("hub_quests_icon", [.15,.86,.2,.14], .96)
                         or hit("hub_tavern_icon", [0,.86,.16,.14], .96))
        tavern_battle = hit("tavern_battle_icon", [.65,.2,.35,.8], .96)
        tavern_label = None
        if tavern_battle:
            x,y,w,h = tavern_battle
            scale = w/38
            ih,iw = im.shape[:2]
            lx,ly = max(0,x-8*scale), y+40*scale
            rw,rh = min(76*scale,iw-lx), min(36*scale,ih-ly)
            if rw > 0 and rh > 0:
                tavern_label = hit("tavern_battle_label", [lx/iw,ly/ih,rw/iw,rh/ih], .94)
        if sd_tile and footer_battle and footer_anchor:
            put("battle_hub_menu", True, .96, "Supreme Deity tile and shared footer")
            put("battle_hub_sd_rectangle", list(sd_tile), .96, "Supreme Deity tile title")
        elif ((tavern_battle and tavern_label) or (footer_battle and footer_anchor)) and not any(known(k) is True for k in (
                "sd_menu", "setup_screen", "coin_screen", "apply_screen", "sd_battle", "result_screen")):
            button = tavern_battle if tavern_battle and tavern_label else footer_battle
            put("hub_battle_shortcut", True, .96, "Battle icon with label or shared hub footer")
            put("hub_battle_rectangle", list(button), .96, "observed Battle button interior")
        if known("battle_hub_menu") or known("hub_battle_shortcut"):
            put("battle_exited", True)
        if known("setup_screen") or known("apply_screen") or known("sd_menu") or known("coin_screen"):
            put("battle_exited", True)
        if known("coin_screen") or known("setup_screen"):
            put("coin_or_setup", True)
        if known("coin_screen"):
            if hit("registration_x3", [.5,.32,.3,.05], .96):
                put("registration_x3", True)
                put("registration_x1", False)
            elif hit("registration_x1", [.2,.32,.3,.05], .96):
                put("registration_x3", False)
                put("registration_x1", True)
            apply = hit("apply_recorded", [.25, .87, .5, .12], .96)
            if apply and (known("registration_x1") is True
                          or hit("coins_full", [.4,.25,.3,.06], .96)):
                put("coins_ready", True)
            elif (hit("coins_empty", [.4,.25,.3,.06], .96)
                  or hit("apply_disabled", [.25,.87,.5,.12], .97)):
                put("coins_ready", False)
            elif self.p.profile.get("difficulty") == "hard" and apply:
                # Hard x3 can show 225/225 rather than the supplied x1 75/75.
                full = self.p.percentage_reader.registration_full(im[258:286,225:315])
                if full is not None:
                    put("coins_ready", full, .96, "isolated Hard registration balance OCR")
        if hit("stamina_pot", [.3, .25, .4, .18], .95) and (
                hit("stamina_use_button_live", [.3, .68, .4, .13], .96)
                or hit("stamina_use_button_hover", [.3, .68, .4, .13], .96)
                or hit("stamuse", [.3, .68, .4, .13], .96)):
            put("stamina_dialog", True)
        # Confirmation is contextual: OK alone is deliberately insufficient.
        # Additional labeled dialog detectors in the profile take precedence.

        queue_roi = [0.24, .71, .53, .12]
        slots, rectangles = [], {}
        for idx, x in enumerate((140, 207, 274, 341)):
            roi = [x / 530, 688 / 950, 57 / 530, 96 / 950]
            names = ("empty_slot", "empty_slot_hover", "empty_slot_1 ", f"empty_slot_{idx+1}_if_skill_blocked",
                     *(f"empty_{idx}_{t}" for t in (48, 147, 230)))
            empty = any(hit(name, roi, .94) for name in names)
            locked = hit("slot_locked", roi, .94)
            moved = hit("slot_moved", roi, .94)
            # Played cards have the same artwork at the smaller queue scale.
            card = any(hit(prefix + name, roi, .94) for name in CARD_IDENTITIES
                       for prefix in ("queue_", "queue_live_"))
            if locked:
                slots.append("locked")
            elif moved or card:
                slots.append("occupied")
            elif empty:
                slots.append("empty")
            else:
                slots.append(None)
            rectangles[str(idx)] = [x, 690, 55, 90]
        if not menu and all(s is not None for s in slots):
            put("queue_verified", True)
            put("empty_slots", slots.count("empty"))
            put("unused_slots", [i for i, s in enumerate(slots) if s == "empty"])
            put("locked_slots", [i for i, s in enumerate(slots) if s == "locked"])
            put("moved_slots", [i for i, x in enumerate((140,207,274,341))
                                if hit("slot_moved", [x/530,688/950,57/530,96/950], .94)])
            put("slot_rectangles", rectangles)
            put("action_capacity", len(slots))
            if not enemy:
                put("turn_mode", "player")
            put("stigma_closed", True)
            put("scene_actionable", True)
            self.previous_slots = slots
        elif menu and self.previous_slots:
            # The menu overlays the bottom of the queue. Read visible slot tops;
            # do not count menu buttons as queued actions.
            tops = [hit(f"menu_empty_top_{i}", [x/530, 688/950, 57/530, 35/950], .96)
                    for i, x in enumerate((140, 207, 274, 341))]
            if all(tops):
                put("empty_slots", 4)
                put("queue_verified", True)
                put("turn_mode", "player")
                put("scene_actionable", True)
        # Live scores: ready orb .94-.95, spent orb .95-.953; the opposite state
        # scores only ~.55, so a lower floor stays unambiguous.
        talent_ready = hit("talent", [.42, .63, .17, .1], .90)
        talent_used = hit("talent_used", [.42, .63, .17, .1], .90)
        if talent_ready and not talent_used:
            put("talent_ready", True)
        if talent_ready and not talent_used:
            put("talent_effect", False)
        if talent_used and not talent_ready:
            put("talent_ready", False)
            put("talent_effect", True)
        # Some live activations close the menu automatically before a spent
        # menu icon can be sampled. Accept the now-locked gauge only after
        # available Weakening was observed and its activation was dispatched.
        if (self.phase != 6 and "weakening" in self.armed and "weakening" in self.available_seen
                and not menu and known("queue_verified") is True
                and (hit("stigma_gauge_spent", [0,.62,.23,.15], .96)
                     or hit("stigma_padlock", [0,.62,.23,.15], .96)
                     or hit("stigma_padlock_live", [0,.62,.23,.15], .96))):
            self.spent.add("weakening")
        # Final Stigma uses a resource icon disappearing from an intact gold
        # diamond, rather than the P3 padlock. Require observed availability,
        # dispatched activation, returned player queue and a recognized frame.
        if (self.phase == 6 and not menu and known("queue_verified") is True
                and known("turn_mode") == "player"
                and (hit("final_stigma_top_frame", [0,.62,.23,.15], .96)
                     or hit("final_stigma_top_orange", [0,.62,.23,.15], .96))):
            for name, (x,y,w,h) in (("destruction", (46,632,23,24)),
                                    ("heal", (25,653,25,29))):
                if name not in self.armed or name not in self.available_seen:
                    continue
                hsv = cv2.cvtColor(im[y:y+h,x:x+w], cv2.COLOR_BGR2HSV)
                hue, sat, val = hsv[:,:,0], hsv[:,:,1], hsv[:,:,2]
                color = ((hue < 12) | (hue > 170)) if name == "destruction" else ((hue > 35) & (hue < 85))
                # A consumed slot is predominantly dark, not just discolored
                # by a flash, fade, or animation overlay.
                if (np.mean(color & (sat > 100) & (val > 100)) < .02
                        and np.mean(val < 100) > .65):
                    self.spent.add(name)
        # Stigma success requires its effect cue plus an actionable closed menu.
        for name in ("weakening", "strengthening", "destruction", "heal"):
            if ((self.phase != 6 or name in ("destruction", "heal")) and name in self.available_seen
                    and hit(name + "_effect_cue", [0, .25, 1, .45], .95)):
                self.activated.add(name)
            # Enabled -> chained/locked at the same menu position is positive
            # activation/resource-consumption evidence, distinct from a click or
            # tooltip heading. The planner separately verifies menu closure.
            if ((name in self.activated or name in self.spent)
                    and (self.phase != 6 or name in self.armed)):
                put(name + "_effect", True)

        if known("turn_mode") == "player" and not menu:
            facts["hand"] = self.hand(im, now, frame, facts)
        banner = None
        if any(hit("phase_" + str(p), [0, .15, 1, .6], .94) for p in (2, 3, 4)):
            # The three pale banner backgrounds match each other strongly; read
            # the actual Judgment word before accepting any phase identity.
            banner = self.p.percentage_reader.judgment(im[190:570])
            if (banner is None and self.phase == 3
                    and hit("phase4_title_live", [0,.15,1,.6], .999)):
                # Full Fourth Judgment lettering from the missed live banner;
                # never infer identity from the shared pale banner background.
                banner = 4
        if banner:
            self.banner = banner
        if (not banner and self.banner and (self.phase is None or self.banner > self.phase)
                and known("turn_mode") == "player"):
            put("phase", self.banner)
            put("wave_transition", True)
            self.phase = self.banner
        elif self.phase is None and known("turn_mode") == "player":
            # The exact opening hand, empty queue and fresh formation establish
            # startup without requiring percentage OCR. Gauge checks elsewhere
            # retain their existing behavior.
            hand = known("hand") or []
            opening = ['odin_1','odin_2','freyr_1','freyr_2','hel_1','hel_2','gawain_1','gawain_2']
            if ([c['id'] for c in hand] == opening and known("empty_slots") == 4
                    and hit("p1_formation", [0, .27, 1, .29], .94)):
                self.phase = 1
                put("new_battle", True)
        if self.phase == 3 and not menu and known("queue_verified") is True and not enemy:
            # Localize the far sides from their HP medallions, not a fixed
            # desktop coordinate. Crop and click offsets come from recorded P3.
            for side, roi in (("right", [.72,.43,.22,.09]),):
                anchor = hit("p3_right_hp_anchor", roi, .94)
                if anchor:
                    x,y,w,h = anchor
                    put("p3_"+side+"_visible", True, .94, "outer enemy HP medallion")
                    put("p3_"+side+"_rectangle", [x+w/2+8,y+h+15,24,32], .94,
                        "outer enemy body below observed HP medallion")
            selected = hit("p3_right_selected", [.72,.45,.22,.13], .94)
            if selected:
                put("p3_right_selection_candidate", True, .94, "far-right selection crest; awaiting frame agreement")
            if self._p3_selection_time != now:
                self._p3_selection_frames = self._p3_selection_frames+1 if selected else 0
                self._p3_selection_time = now
            if selected and self._p3_selection_frames >= 2:
                put("selected_target", "right", .94, "far-right blue selection crest on two frames")
            if (hit("p3_stance_live", [.76,.43,.17,.065], .94)
                    or hit("p3_stance_live_dim", [.76,.43,.17,.065], .94)):
                put("p3_right_stance", True, .94, "gold stance icon in far-right status row")
        else:
            self._p3_selection_frames = 0
        if self.phase == 3 and not menu and not enemy and known("queue_verified") is True:
            # Corroborates an inferred Phase 4 before the detector phase advances.
            if (hit("p4_center_anchor", [.4,.35,.2,.10], .93)
                    or hit("p4_center_anchor_turn2", [.4,.35,.2,.10], .94)):
                put("p4_center_probe", True, .93, "middle boss HP plate while still in P3")
        if self.phase == 4:
            if hit("stigma_weakening_symbol", [.09,.63,.13,.09], .94) and not menu:
                put("p4_weakening_ready", True, .94, "Weakening symbol in Stigmata gauge")
            center = (hit("p4_center_anchor", [.4,.35,.2,.10], .93)
                      or hit("p4_center_anchor_turn2", [.4,.35,.2,.10], .94))
            if center:
                x,y,w,h = center
                put("p4_center_visible", True, .93, "middle boss HP plate")
                put("p4_center_rectangle", [x+w/2-18,y+h+22,36,50], .93,
                    "body below observed middle boss HP plate")
                selector = hit("p4_center_selector", [.43,.42,.15,.12], .96)
                if selector:
                    put("selected_target", "center", .96, "blue selector on middle boss")
        # Live grey frames score .936; the template is specific to this wave.
        grey = hit("grey_phase_check", [0, 0, .24, .12], .92)
        grey_formation = (hit("grey_messengers", [0, .3, 1, .25], .94)
                          or hit("grey_messenger_live", [.7, .4, .25, .15], .94))
        grey_lights = self.grey_lights(im)
        if grey_lights:
            put("grey_lights", True, .96, "two separated yellow lights in upper-right battlefield")
        if (self.phase in (4,5) and known("gauge_anchor") is True
                and type(known("gauge")) in (int,float) and known("gauge") > 50):
            hsv = cv2.cvtColor(im[180:380,20:490], cv2.COLOR_BGR2HSV)
            red = (((hsv[:,:,0] < 12) | (hsv[:,:,0] > 168))
                   & (hsv[:,:,1] > 75) & (hsv[:,:,2] > 60))
            if float(np.mean(red)) >= .35:
                put("red_wave", True, .99, "red battlefield and anchored above-50 gauge")
        # The gauge is not required: Weakening keeps it at 0 in this wave.
        grey_cue = bool(self.phase in (4, 5) and grey and (grey_formation or grey_lights))
        grey_confirmed = self._confirm_grey(now, grey_cue)
        if grey_cue:
            # Expose the first candidate so BattleState suspends battle input.
            put("phase", 5)
            put("grey_context", True)
        if self.phase == 4 and grey_confirmed:
            self.phase = 5
        if self.phase in (5,6):
            if (final_stigma and known("gauge_anchor") is not True
                    and known("turn_mode") == "player" and known("queue_verified") is True
                    and not menu):
                final = True
                put("final_hud", True, .96, "final Stigma frame after grey wave")
        if self.phase == 5:
            if final:
                self.phase = 6
        if self.phase:
            if not grey_cue or self.phase == 6:
                put("phase", self.phase)
            if self.phase in (2, 3, 4):
                put("wave_transition", True)
            if self.phase == 1:
                put("new_battle", True)

    @staticmethod
    def grey_lights(im):
        # Canonical battlefield region, excluding HUD and character skill effects.
        # This is supporting evidence only: transition also requires known P4,
        # the grey gauge appearance, 50%, and the state's two-frame agreement.
        hsv = cv2.cvtColor(im[120:280, 300:470], cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([15,130,210]), np.array([40,255,255]))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))
        _, _, stats, centers = cv2.connectedComponentsWithStats(mask)
        lights = []
        for (x,y,w,h,area), center in zip(stats[1:], centers[1:]):
            core = hsv[y:y+h, x:x+w]
            if (150 <= area <= 3500 and 20 <= w <= 100 and 20 <= h <= 100
                    and np.count_nonzero((core[:,:,1] < 80) & (core[:,:,2] > 240)) >= 10):
                lights.append(center)
        return len(lights) == 2 and 30 <= np.linalg.norm(lights[0]-lights[1]) <= 140

    def hand(self, im, now, frame, facts):
        from utilities.supreme_deity_vision import crop
        hand, started = [], False
        for slot in range(8):
            x = round(32 + slot * 60.4)
            region = im[805:946, x:min(x+64, 530)]
            locked = facts.get("hand_locked", Fact()).value is True
            cached = self._hand_cache.get(slot)
            if cached is not None and cached[1] == locked and np.array_equal(region, cached[0]):
                definition = dict(cached[2], seen=now, evidence=frame)
                hand.append(definition)
                started = True
                continue
            candidates = []
            for identity in CARD_IDENTITIES:
                score = max(self.p.match(region, name)[0] for name in
                            (identity, "art_" + identity, "art_alt_" + identity, "art_live_" + identity))
                if score >= .925:
                    candidates.append((score, identity))
            candidates.sort(reverse=True)
            if not candidates:
                if started:
                    return Fact(evidence=frame + ":unrecognized hand slot")
                continue  # Cards are right-aligned as skills are queued.
            started = True
            if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .012:
                return Fact(evidence=frame + ":ambiguous skill artwork")
            score, identity = candidates[0]
            definition = dict(CARD_IDENTITIES[identity])
            ranks = []
            for rank, name in enumerate(("bronze_card", "silver_card", "gold_card")):
                value = max(self.p.match(region, n, [0, .78, 1, .22])[0]
                            for n in (name, "rank_" + name.split("_")[0]))
                if value >= .78:
                    ranks.append((value, rank))
            ranks.sort(reverse=True)
            if len(ranks) > 1 and ranks[0][0] - ranks[1][0] < .10:
                return Fact(evidence=frame + ":rank ambiguous")
            rank = 100 if definition["ultimate"] else ranks[0][1] if ranks else None
            if rank is None:
                return Fact(evidence=frame + ":rank unrecognized")
            # Independent bright artwork plus absence of grey rendering. A partially
            # occluded or weakly colored crop remains unknown, never playable.
            sat = cv2.cvtColor(region[25:110, 8:52], cv2.COLOR_BGR2HSV)[:, :, 1]
            colored = float(np.mean(sat > 80))
            locked = facts.get("hand_locked", Fact()).value is True
            disabled = True if locked else False if colored > .40 else True if colored < .10 else None
            # Dark ultimate artwork can leave availability uncertain. Keep its
            # identity for hand tracking; choose() still requires disabled=False
            # before playing it. It must not hide unrelated playable skills.
            if disabled is None and not definition["ultimate"]:
                return Fact(evidence=frame + ":disabled state ambiguous")
            definition.update(rank=rank, disabled=disabled, rectangle=[x, 805, min(64,530-x), 141],
                              confidence=score, seen=now, evidence=frame, hand_slot=slot)
            hand.append(definition)
            self._hand_cache[slot] = (region.copy(), locked, dict(definition))
        return Fact(hand if hand else None, .97 if hand else 0., now, frame + ":artwork/rank/playability", "observed")
