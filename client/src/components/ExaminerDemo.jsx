import {useEffect,useRef,useState} from 'react';
import {API_BASE_URL,hearAudio,reviewRadioTransmission} from '@/lib/api';
import {startRecording} from '@/lib/micRecorder';

async function call(path='',payload){
  const response=await fetch(`${API_BASE_URL}/api/examiner${path}`,payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{});
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail || 'Examiner service failed');
  return data;
}

export default function ExaminerDemo({mode,onTrafficChange}){
  const [demo,setDemo]=useState(null),[open,setOpen]=useState(false),[busy,setBusy]=useState(false);
  const [error,setError]=useState(''),[speech,setSpeech]=useState(null),[text,setText]=useState('');
  const [recording,setRecording]=useState(false),[role,setRole]=useState('pilot');
  const recorder=useRef(null);
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
  useEffect(()=>{
    if(mode!=='examiner')return;
    let alive=true;
    const refresh=()=>call().then(d=>{if(alive)setDemo(d);}).catch(e=>{if(alive)setError(e.message);});
    refresh();const timer=setInterval(refresh,2500);
    return()=>{alive=false;clearInterval(timer);recorder.current?.cancel();};
  },[mode]);
  if(mode!=='examiner')return null;
  const remaining=demo?.deadline?Math.max(0,Math.ceil(demo.deadline-now/1000)):null;
  const expired=remaining===0;
  const run=async(fn)=>{setBusy(true);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}};
  const act=(action,option)=>run(async()=>{
    const next=await call('/control',{action,session:demo.session,revision:demo.revision,token:demo.token,option:option || ''});
    setDemo(next);
    await onTrafficChange?.();
    if(action==='reset'||action==='start'){setSpeech(null);setText('');}
  });
  const transcribe=async(blob)=>{
    const result=await hearAudio(blob,role,{live:false});
    setSpeech(result);setText(result.transcript || '');window.dispatchEvent(new Event('speech-heard'));
  };
  const microphone=()=>run(async()=>{
    if(recording){const blob=await recorder.current.stop();recorder.current=null;setRecording(false);await transcribe(blob);}
    else{recorder.current=await startRecording();setRecording(true);}
  });
  return <section className="examiner-demo" aria-label="Presentation controls">
    <div className="examiner-toolbar">
      <strong>{demo?`${demo.chapter+1}/8 ${demo.title}`:'Connecting'}</strong>
      <button onClick={()=>setOpen(!open)} aria-expanded={open}>{open?'Hide presentation controls':'Open presentation controls'}</button>
      {demo&&<><button disabled={busy||recording||expired} onClick={()=>act(demo.playing?'pause':'play')}>{demo.playing?'Pause':'Play'}</button><button disabled={busy||demo.playing||recording||expired} onClick={()=>act('step')}>Step +10s</button><button disabled={busy||demo.playing||recording||expired} onClick={()=>act('advance')}>Advance 60s</button><span>T+{demo.elapsed}s · {demo.playing?'running':'paused'}</span>{demo.traffic&&<span>{demo.traffic.total} aircraft · {demo.traffic.airborne} airborne · {demo.traffic.queued} runway movements</span>}{remaining!==null&&<strong role="timer">Presentation {Math.floor(remaining/60)}:{String(remaining%60).padStart(2,'0')} remaining</strong>}</>}
    </div>
    {error&&<p role="alert">{error}</p>}
    {open&&demo&&<div className="examiner-body">
      {expired?<p role="status">Presentation finished at the nine-minute limit. Review the evidence or reset for another rehearsal.</p>:<p>Eight-minute walkthrough · nine-minute hard stop · one-minute margin below the examiner’s ten-minute limit. Use Advance 60s to avoid waiting for flight motion.</p>}
      <p>{demo.guide}</p>
      <p className="text-xs">Traffic updates every 10 seconds. Pause to review a command, then Play to continue aircraft movement.</p>
      <div className="examiner-toolbar"><button disabled={busy||demo.playing||recording||expired||[1,3,5,7].includes(demo.chapter)} onClick={()=>act('next')}>Next chapter</button><button disabled={busy||recording} onClick={()=>act('start')}>Start 9-minute presentation</button><button disabled={busy||recording} onClick={()=>act('reset')}>Reset into new session</button><a href="/logs" target="_blank" rel="noreferrer">Open audit logs</a></div>
      {demo.chapter===5&&!demo.options.length&&<p>Waiting for a confirmed model resolution. Step traffic reports and inspect ML readiness and alert reasons.</p>}
      {demo.options.map(o=><article key={o.id}><strong>Proposed command</strong><p>{o.text}</p>{o.explanation&&<details><summary>Model explanation</summary>{o.explanation}</details>}<button disabled={busy||demo.playing||recording||expired} onClick={()=>act('approve',o.id)}>Approve command</button></article>)}
      {!!demo.backgroundOptions?.length&&<details><summary>Traffic conflict resolutions ({demo.backgroundOptions.length})</summary>{demo.backgroundOptions.map(o=><article key={o.id}><strong>{o.pair.join(' / ')}</strong><p>{o.text}</p><details><summary>Model explanation</summary>{o.explanation}</details><button disabled={busy||demo.playing||recording||expired} onClick={()=>act('resolve',o.id)}>Approve traffic resolution</button></article>)}</details>}
      {demo.resequence&&<details><summary>Runway recovery changes</summary><p>Before: {demo.resequence.before.map(r=>r.callsign).join(' → ')}</p><p>After: {demo.resequence.after.map(r=>r.callsign).join(' → ')}</p></details>}
      <details><summary>Speech → transcription → callsign / intent → readback</summary>
        <p>Say “Indigo one zero one, request departure” as Pilot. For altitude intent after takeoff, choose ATCO and say “Indigo one zero one, climb to five thousand feet”, then repeat as Pilot. Recordings use real ASR; corrected text is labelled review.</p>
        <div className="examiner-toolbar"><label>Speaker <select disabled={recording||busy} value={role} onChange={e=>setRole(e.target.value)}><option value="pilot">Pilot</option><option value="atco">ATCO</option><option value="unknown">Unknown</option></select></label>
          <button disabled={busy} onClick={microphone}>{recording?'Stop and transcribe':'Record microphone (max 30s)'}</button>
          <button disabled={busy||recording} onClick={()=>run(async()=>{const response=await fetch(`${API_BASE_URL}/api/examiner/sample`);if(!response.ok)throw new Error('Sample voice generation failed');await transcribe(await response.blob());})}>Transcribe pilot sample</button>
          <label>Upload WAV <input type="file" accept=".wav,audio/wav" disabled={busy||recording} onChange={e=>{const file=e.target.files?.[0];if(file)run(()=>transcribe(file));e.target.value='';}}/></label>
        </div>
        {busy&&<p role="status">Processing… speech inference may take time on CPU.</p>}
        {speech&&<article><p>Recognized: {speech.transcript || speech.reason}</p><p>Matched: {speech.callsignMatch?.code || 'unmatched'} · role: {speech.role} · readback: {speech.readback?.status || 'not applicable'}</p>
          <label>Review transcript <textarea value={text} onChange={e=>setText(e.target.value)} rows={2}/></label><button disabled={busy||!speech.transcriptionId||role==='unknown'} onClick={()=>run(async()=>{const result=await reviewRadioTransmission(speech.transcriptionId,text,role);setSpeech(result);window.dispatchEvent(new Event('speech-heard'));})}>Apply reviewed text with selected role</button>
          <details><summary>Extraction and acceptance details</summary><pre>{JSON.stringify(speech,(key,value)=>value==='synthetic'?'traffic':value,2)}</pre></details>
        </article>}
      </details>
      <details><summary>Approved command audio ({demo.approvals.length})</summary>
        {demo.approvals.map(a=><article key={a.id}><p>{a.text}</p><audio controls preload="none" src={`${API_BASE_URL}/api/examiner/audio/${demo.session}/${a.id}`}/><a href={`${API_BASE_URL}/api/examiner/audio/${demo.session}/${a.id}`} download>Download command WAV</a></article>)}
        {!demo.approvals.length&&<p>Audio becomes available after controller approval.</p>}
      </details>
    </div>}
  </section>;
}
