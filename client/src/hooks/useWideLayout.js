import {useSyncExternalStore} from 'react';

const query='(min-width: 1100px)';
const subscribe=notify=>{
  const media=window.matchMedia(query);
  media.addEventListener('change',notify);
  return ()=>media.removeEventListener('change',notify);
};
export function useWideLayout(){
  return useSyncExternalStore(subscribe,()=>window.matchMedia(query).matches,()=>false);
}
const narrowQuery='(max-width: 759px)';
const subscribeNarrow=notify=>{
  const media=window.matchMedia(narrowQuery);
  media.addEventListener('change',notify);
  return ()=>media.removeEventListener('change',notify);
};
export function useNarrowLayout(){
  return useSyncExternalStore(subscribeNarrow,()=>window.matchMedia(narrowQuery).matches,()=>false);
}
