# V1 calibration notes

Profile: `scripts/config/supreme_deity/v1-calibration.json`. Canonical screenshot: 530 × 950. Viewport transforms produce screenshot-local rectangles before existing helpers add the window offset.

P3 right-side stance icons have two recorded variants from
`20261015T120610_887772Z/000457_tick.png` and `000465_tick.png`.
The policy reserves silver-or-higher Freyr skill 1 or any-rank Odin skill 1;
Gawain AoE is an alternative. This is an issued stance-removal attempt, not
independent proof of removal. The right target still needs blue-crest confirmation
for ST use; the one-opening-click rule remains.

The same run's `000831_tick.png` shows the red branch at 60%. The red colour
test covers a bounded battlefield region and requires anchored gauge >50.
Two fresh observations trigger a reset in P4/extra-wave context; card dispatch
is suspended from the first candidate. Queue-slot matching is deliberately not
required because the red tint occludes it in the actual recording. Reference
images and regression cases are in `tests/fixtures/stance_red`.

The ZIP's **12 card PNGs, 49 reference PNGs and evidence.json** remain byte-for-byte unchanged. `empty_slot_1 .png` retains its literal space. Additional recording crops have separate source timestamps/rectangles in `images/supreme_deity/derived/evidence.json`. No asset is labeled production-ready. Original `ready:false` flags are provenance, not runtime Stigma availability.

## Offline image evidence

- Eight opening skill identities and independent bronze/silver ranks; a later mixed silver/gold hand.
- Four empty queue slots, crossed-gold lock symbol and distinct blue movement symbol.
- Enabled Weakening in its menu position, subsequent locked icon, closed-menu return and four unchanged ordinary slots.
- General local RapidOCR CPU reader: recorded 0%/50%, resized 50% frames and final-HUD exclusion. Synthetic OCR boundary labels cover 0/49/50/51/60/100; they are not claimed as recorded game observations.
- Judgment words are OCR-confirmed after template localization. Shared pale backgrounds cannot choose phases. Remaining-turn pips are never phase IDs.
- Hell/setup portraits, x3 registration, full coin count, Apply, stamina and COMPLETE pixels.

Card identity uses supplied artwork plus labeled recording crops. `_1`/`_2` mean skills. Rank uses the existing bronze/silver/gold border templates/models plus recorded crops. English assets follow the existing Global/Japan resolver and fallback convention.

## Runtime checks and limits

Weakening availability requires an enabled or positively matched locked icon at its menu position. Missing both is unknown. A tooltip heading is never availability proof. After an issued request, an effect cue or enabled→locked resource transition supplies activation evidence. The fighter closes a still-open menu, then verifies unchanged ordinary slots. Old activation evidence is cleared before every new request.

Final Destruction/Purification use resource-transition verification. The recording does not demonstrate those requested final-turn choices, so their live effect animations remain **unvalidated**. Confirmed unavailability closes the menu and continues. Unknown optional availability gets brief bounded reacquisition, then closes without claiming activation or waiting for recharge. P3 Weakening is optional; the turn plan continues if it is unavailable or rejected.

No real forfeit dialog occurs in this successful-run recording. Confirmation requires prior pause-menu context, matching OK and high-confidence OCR of a question asking whether to forfeit. Synthetic question text exercises that OCR path, **not a real dialog**. Unrecognized/localized wording causes bounded timeout without falsely reporting exit/restarting. A positive profile `forfeit_confirmation` detector can support another validated dialog.

The P3 far-right body is located below a fresh right HP medallion match using a crop from `20261015T093658_197666Z/000251_tick.png`. Only the right side is detected on the recorded T1/T2/T3 images in `tests/fixtures/p3`. The alternate strategy clicks far right at most once at its T1 opening, after ready Talent, and skips the click if already selected. Later turns and Talent uses only verify the blue selection crest across two distinct captures; no repeat clicks. Recorded selected/deselected frames from `20261015T111753_630713Z` are in `tests/fixtures/p3_selection`. Missing opening selection enters bounded recovery. Missing selection on later turns blocks only single targets and continues AoEs/ultimates/moves, without assuming a death or resetting solely for the target. The P4 click path is unchanged. A separate two-crystal crop from `000368_tick.png` fixes the missed T3 countdown. Four positively matched slots establish capacity. Layout changes, dead units, occlusion, unknown ranks/overlays, unfamiliar setup portraits or severe scale/letterbox changes can remain unknown and cause bounded recovery. Supplied-frame tests do not establish robustness for every resolution, animation, rank or game version.

The final HP-frame cue uses the right endpoint, independently of portrait/orb color; other HUD skins are untested. Grey entry also needs P4 history and messenger context, not just 50% somewhere on screen.

Final portraits now require a unique best score (>=0.96, margin >=0.02) and
two fresh frames for confirmed identity. The Tarmiel recording
`20261015T104300_243852Z/000798_tick.png` scores 0.994 for Tarmiel and 0.890
for the next closest portrait; a canonical copy is in `tests/fixtures/final`.
This validates recognition on that image, not certainty on every live frame.
Confirmed Tarmiel selects one-card-per-owner planning. Unknown identity uses
the same restriction until confirmation; confirmed other enemies retain their
original priority. T2 optional Heal is triggered by repeated Odin/Gawain card
selections on T1. Actual skill-block icons/cleansing are not detected.

`--check` validates structural inputs, not live readiness. `--dry-run FILE` analyzes one offline image without input. Profile detectors use normalized `roi`, `variants` with `template`/`value`, and thresholds. Contradictory/absent matches are unknown; derived rules require positive antecedents. Keep provenance for new crops and never replace uncertain postconditions with always-true rules.

Gauge values remain telemetry. Stop/F8 and input verification remain active. Persistent missing or contradictory phase/turn context triggers a verified forfeit and reset, including after Weakening and in the final phase. Failure to verify the forfeit UI or battle exit stops automation.

P3 Weakening is attempted only on T1. Confirmed opening activation preserves the original working strategy on all Phase 3 turns. Only unavailable/rejected/unconfirmed Weakening selects the separate alternate T1–T4 plan. Both routes retain whole-turn two-attack/two-debuff limits. Confirmed selections are audited, but no detector verifies immortality removal, side-mob deaths, damage-cap consumption, or reflect safety. See README.md for both strategies. Card, queue, scene, and action confirmation checks remain active.
