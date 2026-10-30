"""SD strategies retain the project's Card/action interface; no UI in this layer."""
from utilities.fighting_strategies import IBattleStrategy
from utilities.supreme_deity_core import Planner, Unsafe


class SupremeDeityStrategy(IBattleStrategy):
    route = "v1"

    def configure(self, config):
        self.planner = Planner(config)
        self.observation = self.state = None
        self.proposed_queue = []
        self.phase_turn = 0

    def reset_phase_turn(self):
        self.phase_turn = 0

    def increment_phase_turn(self):
        self.phase_turn += 1

    def pick_cards(self, picked_cards=None, num_units=4, **kwargs):
        hand = kwargs.pop("hand_of_cards")
        action = self.get_next_card_index(hand, picked_cards or [], **kwargs)
        return hand, [action]

    def get_next_card_index(self, hand_of_cards, picked_cards, *, phase=1, card_turn=0, **kwargs):
        self.proposed_queue = self.planner.plan(self.observation, self.state)
        action = self.proposed_queue[0]
        if action["kind"] == "card":
            return action["index"]
        if action["kind"] == "move":
            return tuple(action["indices"])
        handler = kwargs.get("handle_ui_action")
        if handler is None:
            raise Unsafe("Non-card UI action needs the fighter transaction handler")
        # The handler installs a pending transaction. Only its observed postcondition
        # advances progress; a repeated strategy call cannot reissue the click.
        handler(action)
        return None


class SupremeDeityV1Strategy(SupremeDeityStrategy):
    """Odin / LR Freyr / green Hel / Gawain, exact astra-prompt V1."""


STRATEGIES = {"v1": SupremeDeityV1Strategy}
