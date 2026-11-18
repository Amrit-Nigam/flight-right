import test from 'node:test';
import assert from 'node:assert/strict';
import {previewSequence} from './planningPreview.js';

const plan = {gap:120, rows:[
  {id:'A',callsign:'A',earliest:0,latest:1000,target:0,pinned:false},
  {id:'B',callsign:'B',earliest:90,latest:1000,target:120,pinned:false},
]};
test('preview shows readiness and downstream time changes without mutating the plan',()=>{
  const before=JSON.stringify(plan);
  const preview=previewSequence(plan,['B','A']);
  assert.equal(preview.error,null);
  assert.deepEqual(preview.rows.map(r=>[r.id,r.previousTarget,r.target]),[['B',120,90],['A',0,210]]);
  assert.equal(JSON.stringify(plan),before);
});
test('preview reports a pinned slot blocker',()=>{
  const pinned=structuredClone(plan);pinned.rows[0].pinned=true;
  assert.match(previewSequence(pinned,['B','A']).error,/Pinned slot for A/);
});
test('preview reports an exceeded time window',()=>{
  const limited=structuredClone(plan);limited.rows[0].latest=200;
  assert.match(previewSequence(limited,['B','A']).error,/A exceeds/);
});
test('removed rows invalidate an open preview',()=>{
  assert.match(previewSequence(plan,['B','MISSING']).error,/Plan changed/);
});
