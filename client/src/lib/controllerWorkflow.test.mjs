import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequestCache} from './requestCache.js';
import {flightInstructions,instructionText} from './instructionContext.js';

test('history requests deduplicate, reuse cached values and expire',async()=>{
  let time=0,calls=0,release;
  const cache=createRequestCache({ttl:10,now:()=>time});
  const fetcher=()=>{calls++;return new Promise(r=>{release=r;});};
  const first=cache.load('replay1|abc',fetcher),duplicate=cache.load('replay1|abc',fetcher);
  assert.equal(first,duplicate);await Promise.resolve();release({states:[1]});await first;
  assert.equal(calls,1);assert.deepEqual(await cache.load('replay1|abc',fetcher),{states:[1]});
  time=11;const next=cache.load('replay1|abc',()=>{calls++;return {states:[2]};});await next;assert.equal(calls,2);
  assert.equal(cache.peek('replay2|abc'),undefined);
});
test('failed refresh preserves history and allows retry; cache bounded',async()=>{
  let time=0;const cache=createRequestCache({ttl:1,limit:2,now:()=>time});
  await cache.load('a',()=>({states:[1]}));time=2;
  await assert.rejects(cache.load('a',()=>Promise.reject(new Error('offline'))));
  assert.deepEqual(cache.peek('a').value,{states:[1]});assert.match(cache.peek('a').error.message,/offline/);
  await cache.load('a',()=>({states:[2]}));assert.equal(cache.peek('a').error,null);
  await cache.load('b',()=>({}));await cache.load('c',()=>({}));assert.equal(cache.peek('a'),undefined);
});
test('instruction display isolates ICAO, callsign, run, replay cycle and accepted status',()=>{
  const context={scope:'replay:one:2026-09-04:cycle1',runId:'run1'};
  const row={id:1,matched_icao24:'abc',callsign_matched:'A1',action:'DESCEND',value:5000,applied:true,issued_at:'2026-11-16T10:00:00Z',report:{displayContext:context}};
  const history=[{...row,id:2,action:'TURN',value:90},row,{...row,id:3,applied:false,value:1000},
    {...row,id:4,report:{displayContext:{...context,runId:'run0'}}},{...row,id:5,matched_icao24:'def'},
    {...row,id:6,report:{displayContext:{...context,scope:'different'}}},{...row,id:7,callsign_matched:'OTHER'}];
  const result=flightInstructions({history,context},{icao24:'abc',callsign:'A1'});
  assert.equal(result.current.length,3);assert.equal(result.earlier.length,2);
  assert.equal(result.level,'DESCEND 5,000 ft');assert.equal(result.direction,'HDG 090°');
  assert.equal(flightInstructions({history,context},{icao24:'unknown',callsign:'A1'}).level,null);
  assert.equal(instructionText({action:'DIRECT',fix:'POINT'}),'DIRECT POINT');
});
