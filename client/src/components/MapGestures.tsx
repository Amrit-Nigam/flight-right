import {useEffect, useState} from 'react';
import {useMap} from '@/components/ui/map';

export default function MapGestures() {
  const {map}=useMap();
  const [wheelMode,setWheelMode]=useState('pan');
  useEffect(()=>{
    if(!map)return;
    const container=map.getCanvasContainer();
    const observe=()=>{
      const root=map.getContainer();
      root.dataset.mapZoom=String(map.getZoom());
      root.dataset.mapCenter=JSON.stringify(map.getCenter().toArray());
    };
    observe();map.on('move',observe);
    const resize=new ResizeObserver(()=>{
      if(map.getContainer().clientWidth&&map.getContainer().clientHeight)map.resize();
    });
    resize.observe(map.getContainer());
    map.scrollZoom.disable();
    const wheel=(event:WheelEvent)=>{
      // Only canvas/aircraft gestures belong to the map. UI controls keep native scrolling.
      if((event.target as Element)?.closest('input,select,textarea,[data-map-panel]'))return;
      event.preventDefault();
      const factor=event.deltaMode===1?16:event.deltaMode===2?container.clientHeight:1;
      if(event.ctrlKey || event.metaKey || wheelMode==='zoom'){
        const rect=container.getBoundingClientRect();
        const around=map.unproject([event.clientX-rect.left,event.clientY-rect.top]);
        const delta=Math.max(-1,Math.min(1,-event.deltaY*factor/150));
        map.easeTo({zoom:Math.max(map.getMinZoom(),Math.min(map.getMaxZoom(),map.getZoom()+delta)),around,duration:0});
      }else{
        map.panBy([event.deltaX*factor,event.deltaY*factor],{duration:0});
      }
    };
    container.addEventListener('wheel',wheel,{passive:false});
    return ()=>{container.removeEventListener('wheel',wheel);map.off('move',observe);resize.disconnect();};
  },[map,wheelMode]);
  return <div data-map-panel className="tracker-gesture-help" title="Pinch or Ctrl + wheel to zoom; two-finger scrolling pans the map. Outside the map, scrolling stays normal.">
    <span>Pinch / Ctrl + wheel: zoom · two-finger scroll: pan</span>
    <label>Wheel <select aria-label="Map wheel mode" value={wheelMode} onChange={e=>setWheelMode(e.target.value)}><option value="pan">Pan</option><option value="zoom">Zoom</option></select></label>
  </div>;
}
