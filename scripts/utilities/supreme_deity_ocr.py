"""Local OCR of the isolated winged-gauge label; never scans a full HUD."""
import re
import cv2


class PercentageReader:
    def __init__(self):
        self.engine = None

    @staticmethod
    def parse_registration(text, confidence):
        text = re.sub(r"\s+", "", text)
        match = re.fullmatch(r"(\d{1,4})/(\d{1,4})", text)
        if confidence < .96 or not match:
            return None
        current, capacity = map(int, match.groups())
        if capacity <= 0 or current > capacity:
            return None
        return current == capacity

    def registration_full(self, label):
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self.engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        readings = []
        for scale in (3, 4):
            result, _ = self.engine(cv2.resize(label, None, fx=scale, fy=scale), use_det=False, use_cls=False)
            if result and len(result) == 1:
                value = self.parse_registration(*result[0])
                if value is not None:
                    readings.append(value)
        return readings[0] if len(readings) == 2 and readings[0] == readings[1] else None

    @staticmethod
    def parse(text, confidence, minimum=.96):
        text = re.sub(r"\s+", "", text)
        if confidence < minimum or not re.fullmatch(r"(?:100|[1-9]?\d)%", text):
            return None
        return int(text[:-1])

    def read(self, label):
        if label.size == 0:
            return None, 0.
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self.engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        accepted = []
        seen_values = set()
        # Independent scale observations of the same bounded label. No rounding,
        # OCR substitutions, trailing substring extraction, or guessed percentages.
        # Grayscale removes the live client's blue tint without cropping away
        # digits. Each accepted variant still needs two >=.96 readings.
        gray = cv2.cvtColor(label, cv2.COLOR_BGR2GRAY) if label.ndim == 3 else label
        for variant in (label, gray):
            readings = []
            for scale in (3, 4):
                enlarged = cv2.resize(variant, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                result, _ = self.engine(enlarged, use_det=False, use_cls=False)
                if not result or len(result) != 1:
                    continue
                text, confidence = result[0]
                candidate = self.parse(text, confidence, minimum=.90)
                if candidate is not None:
                    seen_values.add(candidate)
                value = self.parse(text, confidence)
                if value is not None:
                    readings.append((value, float(confidence)))
            if len(readings) == 2 and readings[0][0] == readings[1][0]:
                accepted.append((readings[0][0], min(r[1] for r in readings)))
        if len(seen_values) != 1 or not accepted:
            return None, 0.
        return max(accepted, key=lambda r: r[1])

    def judgment(self, banner):
        """Separate banner OCR; never passed to the percentage parser."""
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self.engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        h, w = banner.shape[:2]
        horizontal = cv2.warpAffine(banner, cv2.getRotationMatrix2D((w/2,h/2), -15, 1),
                                    (w,h), borderValue=(255,255,255))
        result, _ = self.engine(horizontal, use_cls=False)
        phases = {"Second Judgment": 2, "Third Judgment": 3, "Fourth Judgment": 4}
        hits = {phases[text] for _, text, confidence in (result or []) if text in phases and confidence >= .94}
        return next(iter(hits)) if len(hits) == 1 else None

    def forfeit_question(self, dialog):
        """Positive question text only; a generic OK or pause-menu label is insufficient."""
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self.engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        result, _ = self.engine(dialog, use_cls=False)
        lines = [text.lower() for _,text,confidence in (result or []) if confidence >= .94]
        # The live dialog uses this short question. OCR can omit spaces;
        # require the question mark to distinguish it from the pause button.
        if any(re.sub(r'\s+', '', line) == 'forfeitthebattle?' for line in lines):
            return True
        text = ' '.join(lines)
        return bool(re.search(r'(?:do you want|are you sure|would you like).{0,100}forfeit', text))
