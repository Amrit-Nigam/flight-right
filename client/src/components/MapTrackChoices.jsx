import {useEffect,useState,useRef} from 'react';
import {useMap} from '@/components/ui/map';
import {ageLabel} from '@/lib/trafficPresentation';

// Icons stay at reported coordinates. A separate chooser reveals coincident identities.
export default function MapTrackChoices({flights,onSelectFlight,selectedFlight}) {
  const {map}=useMap();
  const [groups,setGroups]=useState([]);
  const [open,setOpen]=useState(null);
  const lastSelection=useRef(null);
  useEffect(()=>{
    if(!map)return;
    const update=()=>{
      const points=flights.map(f=>({...f,point:map.project([f.lng,f.lat])}));
      const used=new Set(),next=[];
      for(let i=0;i<points.length;i++){
        if(used.has(i))continue;
        const indices=[i];used.add(i);
        for(let k=0;k<indices.length;k++)for(let j=0;j<points.length;j++){
          if(!used.has(j)&&Math.hypot(points[indices[k]].point.x-points[j].point.x,points[indices[k]].point.y-points[j].point.y)<28){used.add(j);indices.push(j);}
        }
        if(indices.length>1){
          const members=indices.map(n=>points[n]).sort((a,b)=>a.callsign.localeCompare(b.callsign));
          const {x,y}=members[0].point;
          if(x>=0&&y>=0&&x<map.getContainer().clientWidth&&y<map.getContainer().clientHeight)
            next.push({id:members.map(f=>f.callsign).join('|'),members,x,y});
        }
      }
      setGroups(next);
    };
    update();map.on('move',update);map.on('resize',update);
    return()=>{map.off('move',update);map.off('resize',update);};
  },[map,flights]);
  useEffect(()=>{
    if(!map || selectedFlight===lastSelection.current)return;
    lastSelection.current=selectedFlight;
    const flight=flights.find(f=>f.callsign===selectedFlight);
    if(flight&&!map.getBounds().contains([flight.lng,flight.lat]))map.easeTo({center:[flight.lng,flight.lat],duration:400});
  },[map,selectedFlight,flights]);
  const active=groups.find(g=>g.id===open);
  return <>
    {groups.map(g=><button key={g.id} className="map-overlap-count" style={{left:Math.max(5,Math.min(g.x+14,(map?.getContainer().clientWidth || 100)-60)),top:Math.max(5,g.y+14)}} aria-label={`${g.members.length} overlapping aircraft: ${g.members.map(f=>f.callsign).join(', ')}`} aria-expanded={open===g.id} onClick={()=>setOpen(open===g.id?null:g.id)}>{g.members.length} tracks</button>)}
    {active&&<section className="map-overlap-choices" aria-label="Overlapping aircraft"><header><strong>Choose a reported aircraft</strong><button aria-label="Close overlapping aircraft" onClick={()=>setOpen(null)}>×</button></header><p>Markers retain their reported positions. Zoom in to separate them.</p>{active.members.map(f=><button key={f.callsign} onClick={()=>{onSelectFlight?.(f.callsign,{surface:'map-overlap'});setOpen(null);}}><strong>{f.callsign}</strong> · {f.altitude} · {f.staleTrack?'OLD · ':''}{ageLabel(f.reportAgeSeconds)}</button>)}</section>}
  </>;
}
