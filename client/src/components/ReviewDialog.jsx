import {useEffect,useRef} from 'react';
import {createPortal} from 'react-dom';

export default function ReviewDialog({label,onCancel,children}) {
  const root=useRef(null),cancel=useRef(onCancel);
  useEffect(()=>{cancel.current=onCancel;},[onCancel]);
  useEffect(()=>{
    const previous=document.activeElement;
    const focusable=()=>[...root.current.querySelectorAll('button:not(:disabled),select,input,[tabindex="0"]')];
    focusable()[0]?.focus();
    const key=event=>{
      if(event.key==='Escape'){event.preventDefault();cancel.current();}
      if(event.key==='Tab'){
        const nodes=focusable(),first=nodes[0],last=nodes.at(-1);
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
      }
    };
    const el=root.current;el.addEventListener('keydown',key);
    return()=>{el.removeEventListener('keydown',key);if(previous?.isConnected)previous.focus();};
  },[]);
  return createPortal(<div className="sequence-review-backdrop"><div ref={root} className="sequence-review" role="dialog" aria-modal="true" aria-label={label}>{children}</div></div>,document.body);
}
