"""Normalized, evidence-producing perception. No desktop imports in offline modes."""
from __future__ import annotations

import json
from pathlib import Path
from dataclasses import asdict
import cv2
import numpy as np

from utilities.supreme_deity_core import Fact, Observation, Unsafe


def read_image(path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def save_image(path, im):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, data = cv2.imencode(path.suffix or ".png", im)
    if not ok:
        raise ValueError("Cannot encode image")
    data.tofile(str(path))


class Viewport:
    def __init__(self, image, config):
        h, w = image.shape[:2]
        x, y, rw, rh = config.get("viewport", [0, 0, 1, 1])
        self.rect = (round(x*w), round(y*h), round(rw*w), round(rh*h))
        x, y, rw, rh = self.rect
        if rw <= 0 or rh <= 0 or x < 0 or y < 0 or x+rw > w or y+rh > h:
            raise Unsafe("Invalid viewport bounds")
        self.size = tuple(config.get("reference_size", [530, 950]))
        if abs(rw/rh - self.size[0]/self.size[1]) > .035:
            raise Unsafe("Portrait viewport aspect changed; recalibrate letterboxing")
        self.image = cv2.resize(image[y:y+rh, x:x+rw], self.size)

    def local_rect(self, rectangle):
        x, y, w, h = self.rect
        a, b, c, d = rectangle
        sx, sy = w/self.size[0], h/self.size[1]
        return (x+a*sx, y+b*sy, c*sx, d*sy)

    def normalized_rect(self, rectangle):
        a, b, c, d = rectangle
        return self.local_rect((a*self.size[0], b*self.size[1], c*self.size[0], d*self.size[1]))


def crop(im, roi):
    h, w = im.shape[:2]
    x, y, rw, rh = roi
    if min(x,y) < 0 or min(rw,rh) <= 0 or x+rw > 1.000001 or y+rh > 1.000001:
        return im[:0,:0]
    return im[round(y*h):round((y+rh)*h), round(x*w):round((x+rw)*w)]


class Perception:
    def __init__(self, profile, asset_root, resolver=None):
        self.profile = profile
        self.asset_root = Path(asset_root)
        self.resolver = resolver
        self.templates = {}
        self._scaled_templates = {}
        self.last_viewport = None
        self.last_observation = None
        self._stable_signature = None
        self._stable_count = 0
        self.enemy_tracks = {}
        self._tracked_phase = None
        self._candidate_phase = None
        self._phase_count = 0
        from utilities.supreme_deity_ocr import PercentageReader
        self.percentage_reader = PercentageReader()

    def reset(self):
        self.enemy_tracks.clear()
        self.last_observation = None
        self._stable_signature = None
        self._stable_count = 0
        self._tracked_phase = self._candidate_phase = None
        self._phase_count = 0
        if hasattr(self, "v1"):
            self.v1.reset()

    def arm_stigma(self, name):
        """Discard old activation evidence just before a new verified request."""
        if hasattr(self, "v1"):
            self.v1.spent.discard(name)
            self.v1.activated.discard(name)
            self.v1.armed.add(name)

    def template(self, name):
        if name not in self.templates:
            spec = self.profile.get("templates", {}).get(name)
            if not spec:
                return None
            relative = spec["file"]
            p = self.resolver.resolve(relative) if self.resolver else self.asset_root / relative
            if p.is_file():
                self.templates[name] = read_image(p)
        return self.templates.get(name)

    def match(self, im, name, roi=None):
        needle = self.template(name)
        if needle is None:
            return 0., None
        roi = roi or [0, 0, 1, 1]
        hay = crop(im, roi)
        if hay.size == 0:
            return 0., None
        scales = tuple(self.profile.get("templates", {}).get(name, {}).get("scales", [1.]))
        # SQDIFF is well defined even for nearly constant glyph crops.
        best = (0., None)
        h, w = im.shape[:2]
        for scale in scales:
            template_key = (name, scale)
            if template_key not in self._scaled_templates:
                self._scaled_templates[template_key] = cv2.resize(needle, None, fx=scale, fy=scale)
            n = self._scaled_templates[template_key]
            if hay.shape[0] < n.shape[0] or hay.shape[1] < n.shape[1]:
                continue
            if self.profile.get("templates", {}).get(name, {}).get("text_mask"):
                # Match lettering and its immediate outline independently of
                # the changing cinematic background behind a translucent button.
                gray = cv2.cvtColor(n, cv2.COLOR_BGR2GRAY)
                mask = cv2.dilate((gray > 155).astype(np.uint8)*255, np.ones((3,3), np.uint8))
                if not np.any(mask):
                    continue
                result = cv2.matchTemplate(cv2.cvtColor(hay, cv2.COLOR_BGR2GRAY), gray,
                                          cv2.TM_CCOEFF_NORMED, mask=mask)
                result = np.nan_to_num(result, nan=-1., posinf=-1., neginf=-1.)
                _, score, _, (x,y) = cv2.minMaxLoc(result)
                confidence = max(0., min(1., score))
            elif self.profile.get("templates", {}).get(name, {}).get("matching_method") == "ccoeff":
                result = cv2.matchTemplate(hay, n, cv2.TM_CCOEFF_NORMED)
                result = np.nan_to_num(result, nan=-1., posinf=-1., neginf=-1.)
                _, score, _, (x,y) = cv2.minMaxLoc(result)
                confidence = max(0., min(1., score))
            else:
                result = cv2.matchTemplate(hay, n, cv2.TM_SQDIFF_NORMED)
                score, _, (x, y), _ = cv2.minMaxLoc(result)
                confidence = max(0., 1.-score)
            if confidence > best[0]:
                best = (confidence, (x+round(roi[0]*w), y+round(roi[1]*h), n.shape[1], n.shape[0]))
        return best

    def classify(self, im, detector, now, frame):
        hits = []
        for variant in detector.get("variants", []):
            score, rect = self.match(im, variant["template"], detector["roi"])
            if score >= variant.get("threshold", detector.get("threshold", .97)):
                hits.append((variant, score, rect))
        # Contradicting values are unknown; absence is never inferred as false.
        values = {json.dumps(v[0]["value"], sort_keys=True) for v in hits}
        if len(values) != 1:
            return Fact(evidence=frame + ":absent/ambiguous")
        v, score, rect = max(hits, key=lambda item: item[1])
        return Fact(v["value"], score, now, f"{frame}:{v['template']}:{rect}", "observed")

    def gauge(self, im, now, frame, facts):
        spec = self.profile.get("gauge", {})
        score, anchor = self.match(im, spec.get("anchor", "gauge_anchor"), spec.get("anchor_roi", [0, 0, .23, .08]))
        if anchor is None or score < spec.get("threshold", .98):
            facts["gauge_anchor"] = Fact(evidence=frame + ":no winged gauge")
            facts["gauge"] = Fact(evidence=frame + ":gauge unknown")
            return
        facts["gauge_anchor"] = Fact(True, score, now, frame + ":winged gauge", "observed")
        if spec.get("reader") == "ocr":
            label = crop(im, spec["roi"])
            value, confidence = self.percentage_reader.read(label)
            if value is None and spec.get("zero_label_template"):
                needle = self.template(spec["zero_label_template"])
                if needle is not None and label.shape == needle.shape:
                    # Compare the entire fixed label including every digit and
                    # percent sign; never search for a zero substring in 50/100.
                    exact = 1.-float(cv2.matchTemplate(label,needle,cv2.TM_SQDIFF_NORMED)[0,0])
                    if exact >= .99:
                        value, confidence = 0, exact
            facts["gauge"] = Fact(value, min(score, confidence), now, frame + ":isolated gauge OCR", "observed")
            return
        # Full isolated numeric+percent templates avoid confusing boss HP with gauge.
        # All 0..100 values must be calibrated for live; never round to nearest label.
        candidates = []
        for text, template in spec.get("values", {}).items():
            # Match the ENTIRE fixed label ROI, not a substring: a 0% crop must
            # never match the tail of 10%, 60% or 100%.
            region = crop(im, spec.get("roi", [0.025, .07, .15, .033]))
            needle = self.template(template)
            if needle is None or needle.shape != region.shape:
                continue
            s = 1.-float(cv2.matchTemplate(region, needle, cv2.TM_SQDIFF_NORMED)[0,0])
            candidates.append((s, int(text), spec.get("roi")))
        candidates.sort(reverse=True)
        if (not candidates or candidates[0][0] < spec.get("value_threshold", .985)
                or len(candidates) > 1 and candidates[0][0] - candidates[1][0] < spec.get("margin", .008)):
            facts["gauge"] = Fact(evidence=frame + ":ambiguous percentage")
            return
        s, val, rect = candidates[0]
        facts["gauge"] = Fact(val, min(s, score), now, f"{frame}:percent:{rect}", "observed")

    def hand(self, im, now, frame):
        result = []
        for idx, roi in enumerate(self.profile.get("hand_slots", [])):
            region = crop(im, roi)
            candidates = []
            for definition in self.profile.get("cards", []):
                score, _ = self.match(region, definition["template"])
                if score >= definition.get("threshold", .98):
                    candidates.append((score, definition))
            if not candidates:
                return Fact(evidence=f"{frame}:unknown card slot {idx}")
            candidates.sort(key=lambda v: v[0], reverse=True)
            if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .008:
                return Fact(evidence=f"{frame}:ambiguous card slot {idx}")
            score, definition = candidates[0]
            card = {k: v for k, v in definition.items() if k not in ("template", "threshold", "rank_detector", "disabled_detector")}
            # Rank and disabled overlays require explicit independent evidence.
            for key in ("rank", "disabled"):
                detector = definition.get(key + "_detector")
                if detector:
                    fact = self.classify(region, detector, now, frame)
                    if not fact.known(now):
                        return Fact(evidence=f"{frame}:unknown {key} for {card['id']}")
                    card[key] = fact.value
                elif key not in card:
                    return Fact(evidence=f"{frame}:uncalibrated {key}")
            card["rectangle"] = [roi[0]*im.shape[1], roi[1]*im.shape[0], roi[2]*im.shape[1], roi[3]*im.shape[0]]
            card["confidence"], card["seen"], card["evidence"] = score, now, frame
            result.append(card)
        return Fact(result, min((c["confidence"] for c in result), default=0), now, frame + ":hand", "observed")

    def enemies(self, im, now, frame):
        """Discover HP anchors dynamically; keep five spatial identities across frames.

        Missing tracks remain unknown, never become dead. Reacquire a full formation
        at the next confirmed wave; no death or stack inference from damage numbers.
        """
        spec = self.profile.get("enemies", {})
        needle = self.template(spec.get("anchor", "enemy_hp_anchor"))
        if needle is None:
            return Fact(evidence=frame + ":enemy HP anchor uncalibrated")
        roi = spec.get("roi", [0, .25, 1, .3])
        region = crop(im, roi)
        scores = cv2.matchTemplate(region, needle, cv2.TM_SQDIFF_NORMED)
        detections = []
        for _ in range(5):
            value, _, (x, y), _ = cv2.minMaxLoc(scores)
            if 1-value < spec.get("threshold", .98):
                break
            detections.append((x+round(roi[0]*im.shape[1]), y+round(roi[1]*im.shape[0]), 1-value))
            radius = spec.get("nms_radius", 30)
            scores[max(0,y-radius):y+radius+1, max(0,x-radius):x+radius+1] = 1.
        if not self.enemy_tracks and len(detections) == 5:
            self.enemy_tracks = {name: (x,y) for name,(x,y,_) in zip(
                ("outer_left", "inner_left", "center", "inner_right", "outer_right"), sorted(detections))}
        if not self.enemy_tracks:
            return Fact(evidence=frame + ":need full formation for identities")
        found, used = [], set()
        for identity, (oldx, oldy) in self.enemy_tracks.items():
            candidates = sorted(((x-oldx)**2+(y-oldy)**2, i, x,y,s) for i,(x,y,s) in enumerate(detections) if i not in used)
            if not candidates or candidates[0][0] > spec.get("track_radius", 40)**2:
                found.append({"id": identity, "alive": None, "confidence": 0, "seen": now, "evidence": frame})
                continue
            _, i,x,y,s = candidates[0]
            used.add(i)
            self.enemy_tracks[identity] = (x,y)
            enemy = {"id": identity, "alive": True, "hp_anchor": [x,y], "confidence": s, "seen": now, "evidence": frame}
            # Optional calibrated local status panels/HP crops move with each HP
            # anchor, so a five-enemy formation is not a fixed three-target grid.
            for field, detector in spec.get("properties", {}).items():
                dx,dy,rw,rh = detector["relative_roi"]
                local = dict(detector, roi=[(x+dx)/im.shape[1],(y+dy)/im.shape[0],rw/im.shape[1],rh/im.shape[0]])
                fact = self.classify(im,local,now,frame)
                enemy[field] = fact.value if fact.known(now) else None
                enemy[field+"_fact"] = asdict(fact)
            found.append(enemy)
        return Fact(found, min((e["confidence"] for e in found), default=0), now, frame + ":HP anchors", "observed")

    def observe(self, screenshot, now, frame="capture"):
        view = Viewport(screenshot, self.profile)
        self.last_viewport = view
        im = view.image
        score, rect = self.match(im, "annoying_chat_popup", [.8,.3,.2,.45])
        if rect is not None and score >= .96:
            # Do not read phases, queue slots, or effects through the overlay.
            self._stable_count = 0
            self._stable_signature = None
            obs = Observation(now, {
                "chat_popup": Fact(True, score, now, frame+":chat close arrow", "observed"),
                "chat_popup_rectangle": Fact(list(rect), score, now, frame, "observed")}, frame)
            self.last_observation = obs
            return obs
        facts = {key: self.classify(im, d, now, frame) for key,d in self.profile.get("detectors", {}).items()}
        self.gauge(im, now, frame, facts)
        if self.profile.get("schema") == 2:
            from utilities.supreme_deity_detectors import V1Detectors
            if not hasattr(self, "v1"):
                self.v1 = V1Detectors(self)
            self.v1.observe(im, now, frame, facts)
        if self.profile.get("hand_slots"):
            facts["hand"] = self.hand(im, now, frame)
        phase_fact = facts.get("phase", Fact())
        phase = phase_fact.value if phase_fact.known(now) else None
        if phase is not None:
            self._phase_count = self._phase_count+1 if phase == self._candidate_phase else 1
            self._candidate_phase = phase
            if self._phase_count >= 2 and phase != self._tracked_phase:
                self.enemy_tracks.clear()
                self._tracked_phase = phase
        else:
            self._phase_count = 0
        if phase == 6 and self.profile.get("final_enemies"):
            facts["enemies"] = self.classify(im,self.profile["final_enemies"],now,frame)
        elif self.profile.get("enemies"):
            facts["enemies"] = self.enemies(im, now, frame)
        if self.profile.get("queue_slots"):
            slot_facts = [self.classify(im,d,now,frame) for d in self.profile["queue_slots"]]
            if len(slot_facts) <= 4 and all(f.known(now) and f.value in ("empty","occupied") for f in slot_facts):
                facts["empty_slots"] = Fact(sum(f.value == "empty" for f in slot_facts),
                    min(f.confidence for f in slot_facts),now,frame+":independent queue slots","observed")
            else:
                facts["empty_slots"] = Fact(evidence=frame+":queue occluded")
        # Derived rules require positive facts for every condition. No missing=false.
        for rule in self.profile.get("rules", []):
            conditions = rule.get("all", {})
            if conditions and all(k in facts and facts[k].known(now) and facts[k].value == v for k,v in conditions.items()):
                confidence = min(facts[k].confidence for k in conditions)
                facts[rule["field"]] = Fact(rule["value"], confidence, now, frame+":"+rule["evidence"], rule.get("provenance", "inferred"))
        signature = json.dumps({k: facts[k].value for k in ("phase", "hand", "empty_slots", "turn_mode") if k in facts}, sort_keys=True, default=str)
        # Ignore per-frame metadata when deciding whether the hand is stable.
        hand = facts.get("hand", Fact()).value
        signature = json.dumps([facts.get("phase", Fact()).value,
                                [(c.get("id"), c.get("rank"), c.get("disabled")) for c in hand] if hand else None,
                                facts.get("empty_slots", Fact()).value, facts.get("turn_mode", Fact()).value])
        self._stable_count = self._stable_count + 1 if signature == self._stable_signature else 1
        self._stable_signature = signature
        if self._stable_count >= 2 and facts.get("scene_actionable", Fact()).known(now) and facts["scene_actionable"].value is True:
            facts["stable"] = Fact(True, .99, now, frame+":multi-frame agreement", "observed")
        obs = Observation(now, facts, frame)
        self.last_observation = obs
        return obs

    def control_rect(self, control, *, p3_opening=False):
        spec = self.profile.get("controls", {}).get(control)
        if not spec:
            raise Unsafe(f"Uncalibrated control: {control}")
        context = spec.get("context")
        if context and (not self.last_observation or self.last_observation.get(context) is not True):
            raise Unsafe(f"Control context not verified: {control}")
        if spec.get("observed_rectangle"):
            obs = self.last_observation
            fact = obs.facts.get(spec["observed_rectangle"]) if obs else None
            if not fact or not fact.known(obs.time) or fact.seen != obs.time:
                raise Unsafe(f"Fresh control location not verified: {control}")
            return self.last_viewport.local_rect(fact.value)
        if "rectangle" in spec:
            context = spec.get("context")
            if not context or not self.last_observation or self.last_observation.get(context) is not True:
                raise Unsafe(f"Control context not verified: {control}")
            return self.last_viewport.local_rect(spec["rectangle"])
        score, rect = max((self.match(self.last_viewport.image, name, spec["roi"])
                           for name in [spec["template"]] + spec.get("alternates", [])), key=lambda pair: pair[0])
        if rect is None or score < spec.get("threshold", .98):
            obs = self.last_observation
            # Only the P3 opening may use the stable, window-relative button
            # interior when an icon composition is new. Menu/effect confirmation
            # remains required; this never infers Weakening availability.
            if (control == "stigma_open" and p3_opening
                    and spec.get("p3_opening_rectangle") and obs
                    and obs.get("phase") == 3 and obs.get("stable") is True
                    and obs.get("turn_mode") == "player"
                    and obs.get("queue_verified") is True
                    and obs.get("stigma_menu") is False
                    and obs.get("sd_battle") is True):
                return self.last_viewport.local_rect(spec["p3_opening_rectangle"])
            raise Unsafe(f"Control absent/occluded: {control}")
        return self.last_viewport.local_rect(rect)


def validate_profile(config, profile, root):
    """Check structural inputs and unresolved critical cue calibration, offline."""
    from utilities.supreme_deity_v1_policy import LINEUP, NORMAL_ST, FINAL_PRIORITY
    errors = []
    if config.get("difficulty") not in ("hell", "hard") or config.get("route") != "v1":
        errors.append("Only Hell and Hard V1 are supported")
    if config.get("lineup") != LINEUP:
        errors.append("Lineup must be Odin, LR Freyr, green Hel, Gawain in that order")
    if not set(config.get("st_fillers", NORMAL_ST)) <= set(NORMAL_ST):
        errors.append("ST fillers must be normal single-target skills")
    allowed_final = {v for group in FINAL_PRIORITY for v in group}
    if any(s not in allowed_final for group in config.get("final_later_priority", FINAL_PRIORITY) for s in group):
        errors.append("Invalid final priority card")
    if profile.get("schema") != 2 or profile.get("gauge", {}).get("reader") != "ocr":
        errors.append("V1 requires schema 2 and a general isolated percentage reader")
    try:
        import rapidocr_onnxruntime
    except ImportError:
        errors.append("Install requirements-sd-offline.txt for isolated OCR")
    for name, spec in profile.get("templates", {}).items():
        if not (Path(root) / spec["file"]).is_file():
            errors.append("Missing template: " + name)
    supplied = set(profile.get("detectors", {})) | {r["field"] for r in profile.get("rules", [])}
    for key in ("setup_verified",):
        if key not in supplied:
            errors.append("Missing positive calibration: " + key)
    # ready:false in the supplied evidence JSON is provenance, never availability.
    # Reference matching alone is not a successful live calibration claim.
    return errors
