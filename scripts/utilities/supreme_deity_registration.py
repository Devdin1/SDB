"""Select only the requested coin-registration multiplier."""
from copy import deepcopy

def navigation_steps(profile, multiplier=3):
    steps=deepcopy(profile.get('navigation',[]))
    if multiplier == 3:
        return steps
    if multiplier != 1:
        raise ValueError('Registration multiplier must be 1 or 3')
    for step in steps:
        when=step.get('when',{})
        if step.get('control') == 'x3':
            when['registration_x3']=True
            step['control']='x1'
            step['post']='registration_x1'
        elif step.get('control') in ('register','apply'):
            when['registration_x3']=False
    return steps
