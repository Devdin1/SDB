"""Stop before Start when fresh setup evidence confirms the wrong lineup."""
from utilities.supreme_deity_core import Fact, Unsafe

MESSAGE = 'stopped, noticed a wrong team!'
LINEUP = 'set Odin/LRFreyr/Green Hel/Gawain'

def check_team(farmer, obs):
    def fresh(key, value):
        return obs.get(key) is value and obs.facts[key].seen == obs.time
    # The user requires the four exact ordered portraits. A replacement or
    # missing required portrait on the verified team screen must stop, even
    # when the replacement character has no template of its own.
    wrong = (fresh('setup_screen', True) and (
        fresh('setup_wrong_team', True) or fresh('setup_verified', False)
        or not all(fresh(f'setup_owner_{i}', True) for i in range(4))))
    if obs.time != getattr(farmer, '_wrong_team_time', None):
        farmer._wrong_team_frames = getattr(farmer, '_wrong_team_frames', 0) + 1 if wrong else 0
        farmer._wrong_team_time = obs.time
    if wrong:
        # Suspend Start immediately, including the first candidate capture.
        obs.facts['setup_verified'] = Fact(False, .99, obs.time, obs.frame + ':wrong team', 'inferred')
    if farmer._wrong_team_frames < 2:
        return
    farmer.stop_event.set()
    farmer._start_followup = None
    farmer._nav_pending = None
    if not getattr(farmer, '_wrong_team_reported', False):
        farmer._wrong_team_reported = True
        farmer.fighter.journal.write('wrong_team_stopped', evidence=obs.frame,
                                    lineup=LINEUP, wrong_slots=obs.get('setup_wrong_slots'))
        from termcolor import colored
        print(colored(MESSAGE, 'red'), flush=True)
        print(colored(LINEUP, 'red'), flush=True)
    raise Unsafe('Wrong team; no Start or battle input permitted')
