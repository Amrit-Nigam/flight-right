import {useEffect,useState} from 'react';
export function useDisplayClock(feed,connection) {
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{const id=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(id);},[]);
  if(feed.source==='synthetic')return Date.parse(feed.dataTimeUtc)/1000;
  if(feed.source!=='replay')return now/1000;
  const at=Date.parse(feed.dataTimeUtc)/1000;
  const elapsed=connection!=='offline'&&!feed.error?Math.max(0,now-Date.parse(feed.updatedAt))/1000:0;
  return Number.isFinite(at)?at+Math.min(elapsed,45)*(feed.replay?.speed ?? 1):now/1000;
}
