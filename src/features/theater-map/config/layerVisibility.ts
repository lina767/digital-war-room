export interface LayerVisibility {
  theaterEvents: boolean;
  geoint: boolean;
  sigint: boolean;
  heatmap: boolean;
  samRings: boolean;
  airRoutes: boolean;
  seaLanes: boolean;
  chokepoints: boolean;
  militaryBases: boolean;
  nuclearFacilities: boolean;
}

export type LayerAction = { type: "TOGGLE"; layer: keyof LayerVisibility };

export const INITIAL_LAYERS: LayerVisibility = {
  theaterEvents: true,
  geoint: true,
  sigint: true,
  heatmap: false,
  samRings: false,
  airRoutes: true,
  seaLanes: true,
  chokepoints: true,
  militaryBases: true,
  nuclearFacilities: true,
};

export function layerReducer(state: LayerVisibility, action: LayerAction): LayerVisibility {
  return { ...state, [action.layer]: !state[action.layer] };
}
