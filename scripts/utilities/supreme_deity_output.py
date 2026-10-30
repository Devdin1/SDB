"""Console wording and launcher text colors; no battle or input behavior."""
import re

def card_name(action):
    card = action.get('card') or {}
    name = str(card.get('id') or card.get('skill') or card.get('template') or 'unknown')
    name = name.replace('\\', '/').rsplit('/', 1)[-1]
    return name[:-4] if name.lower().endswith('.png') else name

def action_status(action, phase, turn, *, confirmed=False):
    kind = action.get('kind')
    if kind == 'move':
        message = 'Moved cards.' if confirmed else 'Moving cards.'
    elif kind == 'card':
        message = f"{'Played' if confirmed else 'Playing'} {card_name(action)} card."
    elif kind == 'talent':
        message = 'Talent confirmed.' if confirmed else "Let's use Talent."
    elif kind == 'target':
        target = {'left': 'far left enemy', 'right': 'far right enemy', 'center': 'middle boss'}.get(action.get('target'), 'enemy')
        message = f'{target.capitalize()} selection confirmed.' if confirmed else f'Selecting the {target}.'
    elif kind == 'lock':
        message = 'Locked an unused slot.' if confirmed else 'Locking an unused slot.'
    else:
        name = str(kind or 'action').replace('_', ' ')
        message = f'{name.capitalize()} confirmed.' if confirmed else f'Using {name}.'
    context = f'Phase {int(phase)} · Turn {turn} | ' if phase is not None else ''
    return '[SD] ' + context + message

def log_parts(text):
    """Use calm accent colors for Phase/Turn; preserve every character."""
    base = ('error' if any(s in text for s in (
                'stopped, noticed a wrong team!', 'set Odin/LRFreyr/Green Hel/Gawain',
                "Use 'Restart as administrator'", "Can not verify current phase, let's reset!", "Red phase detected", "Phase 4 reset:"))
            else 'success' if '[SUCCESS]' in text or text.lstrip().startswith('[CLEAR]')
            else 'warning' if any(s in text for s in (
                '[WARNING]', '[ERROR]', 'LIVE BLOCKED', 'stopped safely',
                'Wrong buff', 'we need to reset')) else '')
    pattern = r'\b(?:Phase(?: counter)?(?:\s*:\s*|\s+|\s*\()\d+(?:/\d+)?\)?|Wave\s+\d+/\d+|Turns?(?:\s*:\s*|\s+)\d+)'
    parts, start = [], 0
    for match in re.finditer(pattern, text):
        if match.start() > start:
            parts.append((text[start:match.start()], base))
        parts.append((match.group(), 'turn' if match.group().startswith('Turn') else 'phase'))
        start = match.end()
    if start < len(text):
        parts.append((text[start:], base))
    return parts
