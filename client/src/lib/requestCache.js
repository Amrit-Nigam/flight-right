export function createRequestCache({ttl=10000,limit=80,now=Date.now}={}) {
  const entries=new Map();
  return {
    peek:key=>entries.get(key),
    load(key,fetcher){
      const old=entries.get(key);
      if(old?.pending)return old.pending;
      if(old?.value && now()-old.at<ttl)return Promise.resolve(old.value);
      const entry=old || {};
      entries.delete(key); entries.set(key,entry);
      entry.pending=Promise.resolve().then(fetcher).then(value=>{entry.value=value;entry.at=now();entry.error=null;return value;}).catch(error=>{entry.error=error;throw error;}).finally(()=>{entry.pending=null;});
      while(entries.size>limit){const victim=[...entries].find(([,item])=>!item.pending);if(!victim)break;entries.delete(victim[0]);}
      return entry.pending;
    },
    clear:()=>entries.clear(),
  };
}
