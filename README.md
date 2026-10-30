# SDB

## Hard difficulty

Choose **Hard** in the launcher Run setup dropdown, then Start. Hell remains the
default. The command-line equivalent is `SupremeDeityFarmer.py --live --difficulty hard`.
Hard uses the same ordered team and V1 strategy, with five crystal positions,
a 1,200-second run timeout and an alternate Phase 3 burst on T5. Extra turns
use Hel / Gawain ST / Freyr debuff fillers or moves while preserving later
Odin/Gawain AoEs, ultimates and a qualified Phase 3 stance remover where possible.
The original Weakening route and Hell's T4 burst remain intact. Existing gauge
and unknown-phase reset guards remain enabled.

Hard calibration is an overlay in `scripts/config/supreme_deity/hard-calibration.json`.
New source and cropped templates end in `_hard.png`. Crystal calibration and team
recognition use the recorded `20261018T103521_640518Z` frames. The supplied
registration screenshot is a cropped source, so its test fixture reconstructs
the missing top margin; it is not a recorded complete registration frame.
Hard is checked offline against these images and strategy tests; a complete live
Hard clear has not yet been verified.

## Experimental battle changes (15 October 2026)

Changes apply to this copy's normal `Start Supreme Deity.vbs` launcher.

- Phase 2 T2 uses up to two Freyr debuffs, then one Hel attack AoE, then one
  Odin single target, choosing usable cards in that order. Missing cards leave
  slots for Gawain moves (or locks if no Gawain move is possible). Hel debuff
  and other damage skills are not substituted. The two-attack/two-debuff caps remain.
- Red and normal-battle pause button crops now include the actual live artwork
  from `20261015T123606_291573Z`. The old image missed Pause, so the previous
  red reset timed out before sending any pause click. The new crops are tested
  on both the recorded red screen and the normal P4 screen.
- Remember the first freshly read P4 entry percentage. At 10% or higher, play
  the normal T1 strategy, then check Weakening before spending T2 cards. Confirmed
  activation uses the middle-target route. Unavailable/skipped/unconfirmed Weakening resets
  via `P4_ENTRY_GAUGE_NO_WEAKENING`. Activation confirmation has a 20-second bound.
  Unknown entry percentage is reacquired before planning; 0% entry retains the
  existing strategy. The recorded entry value is not replaced by later readings.

- Phase 3 holds one silver/gold `freyr_1`, otherwise one `odin_1` of any normal
  rank, out of ordinary damage selections. Extra copies remain usable. This can
  replace the Odin ST opener when it is the only reserved remover available.
  A recognized far-right stance prioritizes the reserved Freyr/Odin skill if the
  right target is visually selected, or Gawain AoE as the alternative. The remover
  is queued before subsequent damage/ultimates and still respects the two-attack
  limit. Without a legal remover, fill with moves rather than spend ultimates
  into the known stance. Reservation and stance handling apply to both P3 routes.
- The red branch is detected from a red battlefield plus an anchored percentage
  above 50 while leaving P4/in the extra wave. The first candidate suspends card
  input; two distinct matching captures trigger `RED_WAVE_HIGH_GAUGE` and the
  observed forfeit/reset flow, even if the red overlay hides queue recognition.
  Normal/grey 50% frames do not trigger this rule. The log prints the percentage
  in a red reset message. This follows the user's requirement to abandon red.

- Grey now prioritizes Odin/Gawain/Hel AoE ultimates, then Freyr ultimate,
  before normal AoEs on every turn. It no longer holds Odin ult until slot four
  or switches to weak filler priorities after T1. The two-per-category limit
  remains in force. No new gauge target is imposed by this change.
- The recorded FAILED heading plus bottom green OK button are recognized.
  Confirmed results take priority over pending actions/reset recovery. After OK,
  the bot verifies battle exit, records a defeat without adding a clear, and
  returns through normal navigation to start another run. It never clicks the
  equipment "Go Now" button on the failure page.

- Modestly faster input: cursor travel 110–160 ms (previously 120–220 ms),
  card drag 180–240 ms (previously 200–280 ms), minimum action spacing 250 ms,
  battle polling 120 ms, navigation polling 250 ms. Mouse press/drag pickup
  holds, action-success confirmation, retry/animation deadlines, target bounds,
  and Stop/Pause checks are retained. These are input timings, not a promised
  reduction in full battle time; game animations and recognition still govern it.

- **Start** navigates from the shared hub/tavern footer through the Battle menu
  to Supreme Deity, selects Hell, handles registration/setup, and starts farming.
  There is no separate navigation button or stop at the Supreme Deity menu.
  Battle menu tile/footer crops come from the supplied screenshot; the old
  generic tavern/Battle files were absent. The shared-footer route still needs
  verification on an actual tavern screen. Stop/F8 and Pause remain available.
  The supplied crossed-swords **Battle** button is also recognized independently
  of the footer, along the right side at several scales. Its icon and nearby
  Battle label must both match before clicking; notification badges are excluded.
- A correct Hell team screen takes priority over pending menu navigation and
  proceeds straight to Start. Team-screen detection accepts the Hell heading
  plus all four ordered portraits; a new live Start crop fixes the missed button
  in `20261015T103907_892258Z`. Wrong/unknown teams still cannot start.
- **Final-phase Tarmiel strategy:** compare all four portrait references,
  require a score of at least 0.96 and a 0.02 lead over the next match, then
  confirm the identity on two distinct fresh frames. The log announces Tarmiel.
  Confirmed identity persists through menu/animation occlusion; a conflicting
  portrait clears it until the new identity is confirmed. These scores are image
  similarities, not calibrated probabilities or a guarantee against all errors.
- Against Tarmiel, use at most one card per unit per turn, including ultimates
  and debuffs. Other available units fill the queue, followed by moves/locks.
  Unknown portrait identity uses this same limit conservatively; confirmed other
  enemies retain the existing final priority without that restriction.
- On final T2, if confirmed T1 card history contains two or more Odin cards or
  two or more Gawain cards, prioritize optional Heal against Tarmiel (or unknown
  identity). Count cards across skill types/ultimates, excluding moves/retries.
  Unavailable/unconfirmed Heal closes/skips and continues. It is a skill-block
  risk response based on selected-card history, not visual proof of skill block
  or cleansing. The original T4 Heal remains available as before.

- Phase 3 still tries Weakening first. If unavailable, rejected, or unconfirmed
  with a recoverable menu/queue, it switches to the separate alternate strategy
  without resetting. Availability alone does not count as activation.
- Confirmed Weakening keeps the original working strategy on every Phase 3
  turn: Gawain AoE first, then Hel/Odin AoEs, then AoE ultimates, then Gawain/Odin
  card movements. This route does not reserve ultimates until T4.
- Phase 3 allows at most two normal attacks and two debuffs per entire turn.
  Card movements never reset these counts. Ultimates have a separate category.
  Spare slots use Gawain/Hel/Odin/Freyr card movements, then locks if needed.
- The following T1–T4 schedule applies only to the alternate strategy without
  confirmed Weakening; it does not replace the working Weakening route.
- T1: prefer Odin AoE, falling back to Odin single target when available without
  spending the reserved stance remover, then AoEs within the limits. The click position
  is located from the right HP medallion in fresh frames using a recorded crop.
  Only the far-right enemy is detected for P3 targeting; no left fallback.
  Click at most once, at the alternate route's T1 opening, after ready Talent.
  Skip that click if the enemy is already selected. Later turns and Talent uses
  never re-click: two distinct frames showing the blue selection crest confirm
  the target. A visible HP medallion or a previous click alone is insufficient.
  Missing selection at the opening gets bounded reacquisition. On later turns,
  missing selection skips single targets and continues AoEs, scheduled ultimates,
  and moves, without re-clicking or resetting solely for that missing target.
  Each verified turn is reported in the log.
- T1 after its preferred Odin AoE opener, and T2/T3: alternate single targets
  and AoEs based on the last confirmed normal card. T2/T3 start with single
  target. If the preferred type is unavailable or unsafe, use the other type
  before moving. Moves do not advance the alternation. Stance removal still
  takes precedence, and single targets require verified right selection.
  Two attacks plus up to two debuffs are allowed. Highest recognized
  ranks are preferred within the strong group, while preserving a lone Gawain
  AoE when Odin is available to open.
- When AoEs run out, use available single targets against the selected side
  before moving cards, still capped at two attacks/two debuffs. This also applies
  on T3 and when a scheduled T4 ultimate is missing. Without a recognized side
  location or confirmed target, do not send single-target cards.
- T4: strong AoE, another AoE, Gawain ultimate, Hel ultimate. Missing resources
  use moves in their slots. Gawain and Hel ultimates are held before T4. Ready
  Talent can be used without spending a card slot. Later turns continue with
  Gawain ultimate/AoE priority and the same category limits.
- Print the Phase 3 turn, visible crystal countdown, and turns until T4
  ultimates. An additional two-crystal crop fixes the missed T3 counter in the
  recording. Missed enemy banners can be recovered from a verified fresh queue
  and crystal decrement; contradictory turn counts enter reset recovery.
- Confirmed Phase 3 card selections are counted by identity across turns and
  printed in the log. Attempts/retries are not counted as successful selections.
  These counts do not prove damage, kills, stance cancellations, immortality
  stacks, damage-cap procs, or reflect safety. No detectors for those effects
  exist in this package, so the kill timing still needs live validation.
- If a phase survives its planned turn, play available Hel attack/debuff,
  Gawain single target, and Freyr debuff cards, then use moves/locks as necessary.
  Verified hand, queue, rank, and disabled-card checks still apply.
- Persistent missing/contradictory phase or turn context resets through the
  observed pause/forfeit flow. The launcher prints in red:
  `Can not verify current phase, let's reset!`
  HUD/animation reacquisition allows 90 seconds; repeated planning failures
  allow 10 seconds. The overall run timeout also resets. Resetting is allowed
  after Weakening and in the final phase. A reset must verify battle exit before
  starting another run.

Run the desktop-free regression checks from this directory with
`python -m unittest discover -s tests -v`.
