"""Bounded transcript-to-planning adapter. No ASR changes or outbound aircraft control."""
import re
import threading
import time
from datetime import datetime
from .planning_service import PlanConflict
from .traffic_context import traffic_scope

NUMBERS={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}

def interpret(text, flights, rows):
    text=' '.join(text.strip().split())
    lowered=text.lower()
    blocked=r"\b(unable|negative|cancel(?:led)?|disregard|expect|request(?:ing)?|if|when|after|not|never|standby)\b|\bdon'?t\b|\bhold position\b|\bgo[ -]?around\b|\bmissed approach\b"
    if re.search(blocked,lowered):
        return None,'Conditional, requested, cancelled or negative message: controller review required.'
    known={str(f.get('callsign','')).strip().upper():f for f in flights if f.get('callsign')}
    known.update({r['callsign']:known.get(r['callsign'],{}) for r in rows})
    subject=next((code for code in sorted(known,key=len,reverse=True) if re.match(rf'^{re.escape(code)}(?=\W|$)',text,re.I)),None)
    if not subject:
        return None,'No unambiguous flight identifier at the start of the transcript.'
    row=next((r for r in rows if r['id']==subject),None)
    flight=known[subject]
    arrival=bool(re.search(r'\b(land(?:ing)?|arrival|approach)\b',lowered))
    departure=bool(re.search(r'\b(take[ -]?off|departure|taxi|line[ -]?up|holding point|hold short)\b',lowered))
    if arrival and departure:
        return None,'Multiple movement types in one message: review required.'
    kind='arrival' if arrival else 'departure' if departure else row['kind'] if row else None
    sequence=re.search(r'\bnumber\s+(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\b',lowered)
    if len(re.findall(r'\bnumber\b',lowered))>1 or (re.search(r'\bnumber\b',lowered) and not sequence):
        return None,'Sequence number is unsupported or ambiguous; review required.'
    if sequence and re.match(r'\s+(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|\d)\b',lowered[sequence.end():]):
        return None,'Spoken sequence number is ambiguous; review required.'
    following=re.search(r'\b(?:follow|behind)\s+([A-Z0-9]+)\b',text,re.I)
    movement=bool(sequence or following or re.search(r'\bcleared\s+(?:to\s+land|for\s+take[ -]?off)\b|\btaxi\b|\bline[ -]?up\b|\bhold short\b',lowered))
    if not kind or not movement:
        return None,'No supported arrival/departure sequence instruction in this message.'
    if kind=='departure' and flight.get('onGround') is False:
        return None,'Aircraft is already airborne; no new takeoff movement will be queued.'
    result={'callsign':subject,'kind':kind,'text':text}
    if sequence:
        value=sequence.group(1);position=int(value) if value.isdigit() else NUMBERS[value]
        if not 1<=position<=100:return None,'Sequence number must be between 1 and 100.'
        result['position']=position
    if following:
        reference=following.group(1).upper()
        if reference==subject or not any(r['id']==reference for r in rows):
            return None,'The preceding flight is not in the current sequence.'
        result['after']=reference
    if following and sequence:
        return None,'Both a sequence number and preceding flight were specified; review required.'
    mentioned={code for code in known if re.search(rf'(?<!\w){re.escape(code)}(?!\w)',text,re.I)}
    if mentioned-{subject,result.get('after')}:
        return None,'Multiple aircraft mentioned without a single supported follow instruction.'
    return result,'Recognised a bounded planning instruction; server scheduling checks still apply.'

class PlanningRadio:
    def __init__(self):
        self.lock=threading.RLock()

    def process(self, service, feed, text, role, event_id, context=None, trusted=False, at=None):
        scope=traffic_scope(feed)
        base=datetime.fromisoformat(feed['dataTimeUtc']).timestamp() if feed.get('dataTimeUtc') else 0
        with self.lock:
            for _ in range(3):
                plan=service.snapshot(scope,base)
                if any(e['id']==event_id for e in plan.get('radioEvents',[])):return plan
                proposal,reason=interpret(text,feed.get('flights',[]),plan['rows'])
                if proposal:
                    observed=next((f for f in feed.get('flights',[]) if f.get('callsign')==proposal['callsign']),{})
                    eta=observed.get('etaMinutes') if proposal['kind']=='arrival' else None
                    if isinstance(eta,(int,float)) and not isinstance(eta,bool) and 0<=eta<=1440:
                        proposal['ready_at']=base+eta*60
                if context and context.get('scope')!=scope:
                    proposal=None;reason='Transmission belongs to a different traffic session.'
                auto=bool(proposal and trusted and role=='atco' and plan.get('radioAuto',True) and plan['mode']=='normal')
                stale=at is not None and not -5<=time.time()-at<=120
                if stale:auto=False
                event={'id':event_id,'text':text,'role':role,'recordedAt':at or time.time(),
                       'proposal':proposal,'reason':reason,'status':'review' if proposal else 'ignored',
                       'source':'tower transcript' if trusted else 'unverified transcript'}
                if proposal and role=='atco':
                    if not trusted:event['reason']='Speaker, callsign, confidence or surveillance context is not verified for automatic planning; review required.'
                    elif not plan.get('radioAuto',True):event['reason']='Automatic sequence updates are switched off; review required.'
                    elif plan['mode']!='normal':event['reason']='Controller takeover or emergency plan is active; return to normal and review.'
                if proposal and role!='atco':event['reason']='Pilot report/request or unresolved speaker: review before changing the sequence.'
                if stale and proposal:event['reason']='Transcript is older than 120 seconds or has a future timestamp; review against current traffic.'
                try:
                    return service.apply(plan['version'],'radio_event',scope,base,radio_event=event,radio_apply=auto)
                except PlanConflict:continue
                except ValueError as error:
                    event.update(status='blocked',reason=str(error))
                    try:return service.apply(plan['version'],'radio_event',scope,base,radio_event=event,radio_apply=False)
                    except PlanConflict:continue
            raise PlanConflict('Plan changed during transcript processing. Refresh and retry.')

    def sync(self,service,feed,conversation):
        scope=traffic_scope(feed)
        base=datetime.fromisoformat(feed['dataTimeUtc']).timestamp() if feed.get('dataTimeUtc') else 0
        seen={e['id'] for e in service.snapshot(scope,base).get('radioEvents',[])}
        for msg in reversed(conversation.get('messages',[])):
            context=msg.get('displayContext')
            # Unscoped historical transcripts cannot be silently attached to a replay visit.
            if not context or context.get('scope')!=scope:continue
            event_id=f"speech:{context.get('runId')}:{msg['transcriptionId']}"
            if event_id in seen:continue
            match=msg.get('callsignMatch') or {}
            code=match.get('code')
            text=msg.get('transcript','')
            if code and not re.match(rf'^{re.escape(code)}(?=\W|$)',text,re.I):
                # Use the existing matcher output for spoken airline callsigns, without
                # changing speech extraction or its acceptance rules.
                spoken=match.get('heard')
                if spoken and text.lower().startswith(spoken.lower()):text=code+text[len(spoken):]
            trusted=msg.get('roleSource') in ('reviewed','labelled-channel') and bool(code) and match.get('score',0)>=100
            if msg.get('asrConfidence') is not None:
                trusted=trusted and msg['asrConfidence']>=conversation.get('supported',{}).get('minConfidence',1)
            if msg.get('liveRadio') and feed.get('source')!='live':trusted=False
            self.process(service,feed,text,msg.get('role','unknown'),event_id,context,trusted,msg.get('recordedAt'))
        return service.snapshot(scope,base)

planning_radio=PlanningRadio()
