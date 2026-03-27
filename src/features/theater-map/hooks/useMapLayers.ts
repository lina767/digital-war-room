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
  const setLayer = useCallback((layer: keyof LayerVisibility, value: boolean) => {
    dispatch({ type: "SET", layer, value } satisfies LayerAction);
  }, []);
  return { layers, toggleLayer, setLayer, dispatchLayers: dispatch };
}

export type { LayerVisibility };
