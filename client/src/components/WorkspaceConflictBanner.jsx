import {useEffect,useState} from 'react';
import {logAudit} from '@/lib/siteLogger';

export default function WorkspaceConflictBanner({conflict,onResolveClick}){
  const initial=conflict?.countdown || 0;
  const [clock,setClock]=useState({initial,seconds:initial});
  if(clock.initial!==initial)setClock({initial,seconds:initial});
  useEffect(()=>{if(!conflict)return;const timer=setInterval(()=>setClock(c=>({...c,seconds:Math.max(0,c.seconds-1)})),1000);return()=>clearInterval(timer);},[conflict]);
  if(!conflict)return null;
  const time=`${String(Math.floor(clock.seconds/60)).padStart(2,'0')}:${String(clock.seconds%60).padStart(2,'0')}`;
  return <section aria-label="Active conflict alert" className="workspace-alert">
    <div><strong>Predicted separation alert · {conflict.flight1} × {conflict.flight2}</strong><p>{Number(conflict.cpaNM).toFixed(2)} NM / {Math.round(conflict.cpaVerticalFt ?? 0)} ft · CPA in {time}</p></div>
    <button onClick={()=>{logAudit('banner:conflict','Resolution review opened',{pair:[conflict.flight1,conflict.flight2]});onResolveClick?.();}}>Review resolution</button>
  </section>;
}
