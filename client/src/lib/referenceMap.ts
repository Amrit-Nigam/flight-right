import type { StyleSpecification } from 'maplibre-gl';

function referenceStyle(dark: boolean): StyleSpecification {
  return {
    version: 8,
    sources: {land:{type:'geojson',data:'/maps/land.geojson',attribution:'Natural Earth · public domain · coarse geographic reference'}},
    layers: [
      {id:'reference-ocean',type:'background',paint:{'background-color':dark?'#0b1c26':'#dce8ee'}},
      {id:'reference-land',type:'fill',source:'land',paint:{'fill-color':dark?'#223034':'#eef0e7'}},
      {id:'reference-coast',type:'line',source:'land',paint:{'line-color':dark?'#6c878c':'#8d9d96','line-width':1}},
    ],
  };
}

export const REFERENCE_LIGHT = referenceStyle(false);
export const REFERENCE_DARK = referenceStyle(true);
