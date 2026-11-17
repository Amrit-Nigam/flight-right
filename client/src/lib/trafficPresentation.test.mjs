import test from 'node:test';
import assert from 'node:assert/strict';
import {presentFlight,reportAge,localTraffic,sortLocalTraffic,instructionError,forecastLabel} from './trafficPresentation.js';
test('position ages use the individual report, with unknown distinct from zero',()=>{
  assert.equal(reportAge({timePosition:100},280),180);
  assert.equal(reportAge({},280),null);
  assert.equal(reportAge({timePosition:300},280),0);
});
test('old reports withhold ETA and surface phase never asserts departing',()=>{
  const f={timePosition:100,status:'DEPARTING',onGround:true,eta:'~1 min'};
  const old=presentFlight(f,280),fresh=presentFlight(f,110);
  assert.equal(old.staleTrack,true);assert.match(old.displayEta,/Withheld/);
  assert.equal(fresh.staleTrack,false);assert.equal(fresh.displayEta,'~1 min');
  assert.equal(fresh.phaseLabel,'On ground / surface movement');assert.equal(f.status,'DEPARTING');
});
test('undated and missing-feed snapshots are never presented as fresh',()=>{
  assert.equal(presentFlight({},100).staleTrack,true);
  assert.equal(presentFlight({timePosition:90,staleSelection:true},100).staleTrack,true);
});
test('local scope does not mistake missing distance for airport proximity',()=>{
  assert.equal(localTraffic({}),false);assert.equal(localTraffic({distanceToVabbNm:null}),false);
  assert.equal(localTraffic({distanceToVabbNm:200}),false);assert.equal(localTraffic({distanceToVabbNm:25}),true);
  assert.equal(localTraffic({onGround:true}),false);
  assert.equal(localTraffic({onGround:true,distanceToVabbNm:180}),false);
});
test('strip priorities are stable as reported distance changes',()=>{
  const rows=[{callsign:'A1',route:'VABB–OMDB'},{callsign:'Z9',route:'OMDB–VABB'},{callsign:'S1',onGround:true}];
  assert.deepEqual(sortLocalTraffic(rows).map(f=>f.callsign),['S1','Z9','A1']);
  assert.equal(rows[0].callsign,'A1');
});
test('typed instruction bounds match server numeric limits',()=>{
  assert.match(instructionError('TURN','999'),/between 0° and 360°/);
  for(const [action,min,max] of [['TURN',0,360],['CLIMB',1000,60000],['DESCEND',1000,60000],['SPEED',100,600]]){
    assert.equal(instructionError(action,String(min)),'');assert.equal(instructionError(action,String(max)),'');
    assert.ok(instructionError(action,String(min-1)));assert.ok(instructionError(action,String(max+1)));
  }
  assert.ok(instructionError('TURN',''));assert.ok(instructionError('TURN','Infinity'));
});
test('warm-up and unavailable forecast communicate different causes',()=>{
  assert.match(forecastLabel({predictionStatus:'warming',prediction:{reportsReceived:3,requiredReports:10},elapsedSeconds:16}),/3\/10 reports · 16s/);
  assert.match(forecastLabel({predictionStatus:'unavailable',predictionError:'Forecast service unreachable'}),/unreachable/);
});
