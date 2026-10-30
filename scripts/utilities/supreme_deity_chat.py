"""Bounded chat-overlay cleanup, independent of battle action transactions."""
def handle_chat_popup(fighter, obs, offset, perform, *, farmer=None):
    active = getattr(fighter, '_chat_popup_since', None)
    if obs.get('chat_popup') is not True:
        if active is not None:
            elapsed = max(0., obs.time-active)
            pending = fighter.sd.pending
            if pending:
                for key in ('started', 'transaction_started'):
                    if key in pending:pending[key] += elapsed
            for key in ('_waiting_since', '_run_started'):
                if getattr(fighter,key,None) is not None:
                    setattr(fighter,key,getattr(fighter,key)+elapsed)
            if farmer is not None:
                farmer._navigation_started += elapsed
                if getattr(farmer,'_nav_pending',None):
                    step,started=farmer._nav_pending
                    farmer._nav_pending=(step,started+elapsed)
                farmer._start_followup=None
                if getattr(farmer,'_stamina_pending',False):farmer._last_nav_click += elapsed
            fighter._chat_popup_since = None
            fighter.journal.write('chat_popup_cleared', evidence=obs.frame, blocked_seconds=elapsed)
        return False
    if active is None:
        fighter._chat_popup_since=obs.time
        fighter._chat_popup_frames=0
        fighter._chat_popup_time=None
        fighter._chat_popup_attempts=0
        fighter._chat_popup_last_click=None
        fighter.journal.write('chat_popup_detected', evidence=obs.frame)
    if farmer is not None:farmer._start_followup=None
    if obs.time != fighter._chat_popup_time:
        fighter._chat_popup_time=obs.time
        fighter._chat_popup_frames += 1
    last=fighter._chat_popup_last_click
    if obs.time-fighter._chat_popup_since > 8 or (fighter._chat_popup_attempts >= 3
                                                  and last is not None and obs.time-last >= 1):
        fighter.failure='Chat popup could not be dismissed; battle left open.'
        fighter.journal.write('chat_popup_failed', reason=fighter.failure, evidence=obs.frame)
        return True
    if (fighter._chat_popup_frames < 2 or fighter.stop_event.is_set()
            or not fighter.config.get('live',False) or last is not None and obs.time-last < 1):
        return True
    rect=fighter.perception.control_rect('chat_close')
    fighter.mouse.click(rect,offset,perform)
    fighter.last_action=fighter.clock.now()
    fighter._chat_popup_last_click=obs.time
    fighter._chat_popup_attempts += 1
    fighter._chat_popup_frames=0
    fighter.journal.write('chat_popup_close', attempt=fighter._chat_popup_attempts,
                          evidence=obs.frame, rectangle=rect)
    print('[SD] Closing chat popup.',flush=True)
    return True
