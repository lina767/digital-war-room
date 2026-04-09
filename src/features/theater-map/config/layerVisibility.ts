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
  blueLine: boolean;
  unifilPosts: boolean;
  villageImpact: boolean;
  idpOverlay: boolean;
}

export type LayerAction =
  | { type: "TOGGLE"; layer: keyof LayerVisibility }
  | { type: "SET"; layer: keyof LayerVisibility; value: boolean };

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
  blueLine: false,
  unifilPosts: false,
  villageImpact: false,
  idpOverlay: false,
};

export function layerReducer(state: LayerVisibility, action: LayerAction): LayerVisibility {
  if (action.type === "SET") {
    return { ...state, [action.layer]: action.value };
  }
  return { ...state, [action.layer]: !state[action.layer] };
}
