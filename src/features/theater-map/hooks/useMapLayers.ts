import { useCallback, useReducer } from "react";
import {
  INITIAL_LAYERS,
  layerReducer,
  type LayerAction,
  type LayerVisibility,
} from "../config/layerVisibility";

export function useMapLayers() {
  const [layers, dispatch] = useReducer(layerReducer, INITIAL_LAYERS);
  const toggleLayer = useCallback((layer: keyof LayerVisibility) => {
    dispatch({ type: "TOGGLE", layer } satisfies LayerAction);
  }, []);
  return { layers, toggleLayer, dispatchLayers: dispatch };
}

export type { LayerVisibility };
