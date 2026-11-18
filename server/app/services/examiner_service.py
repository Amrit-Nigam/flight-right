"""Opt-in, deterministic teaching traffic. Never used by live/replay modes."""
import math
import threading
import time
import uuid
from datetime import datetime, timezone

from .normalizer import normalize

# Extra movements share the normal runway planner, not a separate display queue.
RUNWAY_MOVEMENTS = [
    ('IGO101','departure',0), ('AIC202','arrival',180), ('IGO303','departure',300),
    ('IGO505','arrival',240), ('SEJ606','departure',120), ('AXB707','arrival',360),
    ('IGO808','departure',480), ('AIC909','arrival',600), ('AKJ110','departure',720),
    ('AIC211','arrival',840), ('IGO312','departure',960),
]
ROUTES = {
    'IGO101':'VABB → VOBL','AIC202':'VIDP → VABB','IGO303':'VABB → VOHS',
    'IGO505':'VAAH → VABB','SEJ606':'VABB → VOMM','AXB707':'OMDB → VABB',
    'IGO808':'VABB → VECC','AIC909':'VOBL → VABB','AKJ110':'VABB → VOGO',
    'AIC211':'VOMM → VABB','IGO312':'VABB → VIDP','IGO401':'VAAH → VOBL',
    'AIC402':'VOHS → VIDP','IGO615':'VIDP → VOGO','SEJ716':'VAAH → VOMM',
    'AIC817':'OMDB → VOHS','IGO918':'VOGO → VIDP','AIC119':'VAAH → VOMM',
}

CHAPTERS = [
    ('Ground preparation', 'Claim IGO101 in Clearance, annotate route/runway, hand off to Ground, then Tower. Try taxi and hold-short communications in Radio.'),
    ('Departure clearance', 'IGO101 holds at runway 27. Review and approve the takeoff command; then step the simulator to watch rotation and climb.'),
    ('Departure climb', 'Step or play: IGO101 climbs to 5,000 ft. Record an altitude instruction and a pilot readback using speech.'),
    ('Arrival / occupied runway', 'AIC202 is on final; service vehicle DEMO01 occupies runway 27. Approve a go-around before continuing.'),
    ('Go-around recovery', 'AIC202 climbs away to 3,000 ft. The existing planner defers its arrival and re-sequences IGO303 ahead of it. Inspect the plan revisions.'),
    ('En-route conflict', 'IGO401 and AIC402 converge at FL300. Step distinct reports until the real alert gate confirms. Inspect ML explanations and ranked options, then approve one below.'),
    ('Resolution compliance', 'Step time to fly the approved manoeuvre with the existing response-delay/turn/climb simulator. Watch actual model reassessment; alerts are never cleared by the approval button.'),
    ('Recovery landing', 'AIC202 returns, lands and vacates. Inspect closed movements, strip handoffs, radio readbacks and the audit export.'),
]


class ExaminerService:
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        self.session = 'examiner-' + uuid.uuid4().hex[:12]
        self.chapter = 0
        self.elapsed = 0
        self.clock = 0
        self.playing = True
        self.traffic_elapsed = 0
        self.departure_at = None
        self.goaround_at = None
        self.revision = 0
        self.approvals = []
        self.manoeuvre = None
        self.resolution_start = None
        self.base = math.floor(time.time() / 10) * 10
        self.deadline = None
        self.background_commands = {}
        self.resequence = None

    def status(self):
        title, guide = CHAPTERS[self.chapter]
        return dict(ok=True, session=self.session, chapter=self.chapter, title=title, guide=guide,
                    elapsed=self.elapsed, playing=self.playing, revision=self.revision,
                    chapters=[c[0] for c in CHAPTERS], approvals=self.approvals,
                    synthetic=True, limit=self.limit(), deadline=self.deadline, resequence=self.resequence,
                    remainingSeconds=max(0,int(self.deadline-time.time())) if self.deadline else None,
                    dataTimeUtc=self.iso(self.timestamp()))

    def limit(self):
        return [120, 0, 200, 0, 90, 40, 240, 100][self.chapter]

    @staticmethod
    def iso(at):
        return datetime.fromtimestamp(at, timezone.utc).isoformat()

    def timestamp(self):
        return self.base + self.traffic_elapsed

    def advance(self):
        self.traffic_elapsed += 10
        self.elapsed += 10
        self.revision += 1

    def status_replay(self):
        return dict(session=self.session, cycle=0, dataTimeUtc=self.iso(self.timestamp()),
                    speed=1, synthetic=True)

    def states(self, offset=0):
        # Local coordinates are illustrative, not surveyed taxiways or procedures.
        t = max(0, self.elapsed + offset)
        chapter = self.chapter
        rows = []
        def add(code, key, lat, lng, alt, speed, heading, vr=0, ground=False):
            row = normalize(dict(callsign=code, icao24=key, lat=lat, lng=lng,
                altitudeFt=alt, speedKt=speed, heading=heading, verticalRateFpm=vr,
                onGround=ground, source='synthetic', timePosition=self.timestamp()+offset))
            row.update(aircraft='B738' if code.startswith(('SEJ','AXB','AKJ')) else 'A320', route=ROUTES.get(code),
                       originCountry='India',provenance='Traffic session',
                       routeSource='Flight plan',
                       aircraftSource='Aircraft information',aircraftDescription='Boeing 737-800' if code.startswith(('SEJ','AXB','AKJ')) else 'Airbus A320',
                       bearingFromVabbDeg=round(math.degrees(math.atan2((lng-72.866)*math.cos(math.radians(lat)),lat-19.09))%360),
                       distanceToVabbNm=round(math.hypot((lat-19.09)*60,(lng-72.866)*60*math.cos(math.radians(lat))),1))
            rows.append(row)
        if chapter <= 1:
            taxi=min(t,120) if chapter==0 else 120
            add('IGO101','de0101',19.090,72.88-taxi*.00004167,38,8 if taxi<120 else 0,270,ground=True)
        else:
            u=max(0,self.traffic_elapsed+offset-self.departure_at) if self.departure_at is not None else 200
            roll=min(u,27.5)
            distance_nm=(4*roll*roll+220*max(0,u-27.5))/3600
            add('IGO101','de0101',19.090,72.875-distance_nm/(60*math.cos(math.radians(19.09))), min(5000,38+max(0,u-15)*35),
                min(220,u*8),270,2100 if 15<u<157 else 0,u<15)
        if chapter < 3:
            angle=(self.traffic_elapsed+offset)*150/(3600*2)
            add('AIC202','de0202',19.12+2*math.cos(angle)/60,73.05+2*math.sin(angle)/(60*math.cos(math.radians(19.12))),3000,150,(math.degrees(angle)+90)%360)
        elif chapter == 3:
            add('AIC202','de0202',19.090,72.96-t*.0005,max(300,900-t*10),145,270,-600 if t<60 else 0)
            add('DEMO01','de0001',19.090,72.864,38,0,0,ground=True)
        elif chapter < 7:
            u=max(0,self.traffic_elapsed+offset-self.goaround_at) if self.goaround_at is not None else t
            add('AIC202','de0202',19.090+max(0,u-45)*.0002,72.96-u*.0006,
                min(3000,900+u*30),180,270 if u<45 else 300,1800 if u<70 else 0)
        else:
            u=min(t,100)
            add('AIC202','de0202',19.090+max(0,u-80)*.0001,72.96-u*.001, max(38,900-u*18),
                max(0,145-u*1.45),270,-1080 if u<48 else 0,u>=48)
        add('IGO303','de0303',19.095,72.862,38,0,270,ground=True)
        self.background_states(add, offset)
        if chapter in (5,6):
            from ml_pipeline.utils.resolution_engine import Manoeuvre, simulate_manoeuvre
            for code,key,lon,heading in [('IGO401','de0401',72.65,90),('AIC402','de0402',73.22,270)]:
                initial=dict(latitude=19.50,longitude=lon,altitude_m=9144.,velocity_ms=230.,
                             heading_deg=heading,vertical_rate_ms=0.,callsign=code)
                # Chapter five waits for approval; both aircraft still move on each step.
                seconds = self.elapsed + offset if chapter==5 else self.resolution_start + self.elapsed + offset
                action=Manoeuvre(**self.manoeuvre) if chapter==6 and self.manoeuvre['aircraft']==code else None
                if chapter==6:
                    prior=simulate_manoeuvre(initial,None,[self.resolution_start])[self.resolution_start]
                    initial.update(latitude=prior[0],longitude=prior[1],altitude_m=prior[2])
                    seconds=max(0,self.elapsed+offset)
                if seconds < 0:
                    distance=230*seconds
                    lat=19.50; lng=lon+distance*math.sin(math.radians(heading))/(111320*math.cos(math.radians(lat))); alt=9144.
                else:
                    lat,lng,alt=simulate_manoeuvre(initial,action,[int(seconds)])[int(seconds)]
                display_heading=heading
                if action and action.kind=='heading':
                    display_heading=(heading+math.copysign(min(abs(action.magnitude),max(0,seconds-38)*3),action.magnitude))%360
                vr=0.; speed=230*1.94384
                if action and seconds>0:
                    before=max(0,int(seconds)-5)
                    p=simulate_manoeuvre(initial,action,[before])[before]
                    dt=seconds-before
                    vr=(alt-p[2])*3.28084*60/dt
                    speed=math.hypot((lat-p[0])*111320,(lng-p[1])*111320*math.cos(math.radians(lat)))/dt*1.94384
                add(code,key,lat,lng,alt*3.28084,speed,display_heading,vr)
        return rows

    def background_states(self, add, offset):
        from ml_pipeline.utils.resolution_engine import Manoeuvre, simulate_manoeuvre
        age=self.traffic_elapsed+offset
        # Arrival holding patterns maintain motion without silently landing queued flights.
        for i,(code,lat,lng,alt) in enumerate([
            ('IGO505',19.18,73.13,4500),('AXB707',19.35,73.25,6000),
            ('AIC909',18.95,73.18,7500),('AIC211',19.50,72.95,9000),
            ('IGO615',18.85,72.45,11000),('SEJ716',19.52,72.45,40000),('AIC817',19.30,73.40,47000)]):
            radius=3 if i<4 else 7
            speed=165 if i<4 else 360
            angle=age*speed/(3600*radius)+i*.8
            north=radius*math.cos(angle);east=radius*math.sin(angle)
            add(code,f'de{510+i:04d}',lat+north/60,lng+east/(60*math.cos(math.radians(lat))),
                alt,speed,(math.degrees(angle)+90)%360)
        for i,code in enumerate(('SEJ606','IGO808','AKJ110','IGO312')):
            add(code,f'de{610+i:04d}',19.093+i*.0016,72.873+i*.0012,38,0,270,ground=True)
        # A second real assessed encounter can be inspected/resolved at any chapter.
        for code,key,lon,heading in [('IGO918','de0918',72.35,90),('AIC119','de0119',73.25,270)]:
            initial=dict(latitude=18.75,longitude=lon,altitude_m=18000/3.28084,
                         velocity_ms=180.,heading_deg=heading,vertical_rate_ms=0.,callsign=code)
            accepted=self.background_commands.get(code)
            action=None
            seconds=age
            if accepted and age>=accepted['at']:
                initial=accepted['state'];seconds=age-accepted['at'];action=Manoeuvre(**accepted['manoeuvre'])
            if seconds<0:
                lat=initial['latitude'];lng=initial['longitude']+seconds*initial['velocity_ms']*math.sin(math.radians(heading))/(111320*math.cos(math.radians(lat)));alt=initial['altitude_m']
            else:
                lat,lng,alt=simulate_manoeuvre(initial,action,[int(seconds)])[int(seconds)]
            speed=initial['velocity_ms']*1.94384;vr=0
            if action:
                heading=initial['heading_deg']
                if action.kind=='heading':heading=(heading+math.copysign(min(abs(action.magnitude),max(0,seconds-38)*3),action.magnitude))%360
                if seconds>0:
                    before=max(0,int(seconds)-5);dt=seconds-before
                    prev=simulate_manoeuvre(initial,action,[before])[before]
                    vr=(alt-prev[2])*3.28084*60/dt
                    speed=math.hypot((lat-prev[0])*111320,(lng-prev[1])*111320*math.cos(math.radians(lat)))/dt*1.94384
            add(code,key,lat,lng,alt*3.28084,speed,heading,vr)


examiner_service = ExaminerService()
