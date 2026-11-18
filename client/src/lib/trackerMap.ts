import type {StyleSpecification} from 'maplibre-gl';

export function streetStyle(dark: boolean): StyleSpecification {
  return {
    version: 8,
    sources: { streets: {
      type:'raster', tileSize:256, minzoom:0, maxzoom:19,
      tiles:[import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      attribution:import.meta.env.VITE_MAP_ATTRIBUTION || '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>',
    }},
    layers:[{id:'streets',type:'raster',source:'streets',paint: dark
      // Remap only the raster: light tile backgrounds become dark, labels become
      // light. Aircraft, forecasts and conflict layers retain their own colours.
      ? {'raster-saturation':-1,'raster-brightness-min':0.72,'raster-brightness-max':0.07,'raster-contrast':0}
      : {'raster-saturation':-0.25}}],
  };
}
export const STREET_LIGHT=streetStyle(false);
export const STREET_DARK=streetStyle(true);
