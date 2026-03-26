import { DeckGL } from "@deck.gl/react";
import type { PickingInfo } from "@deck.gl/core";
import type { Layer } from "@deck.gl/core";
import MapLibreMap from "react-map-gl/maplibre";
import MapboxMap from "react-map-gl/mapbox";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "mapbox-gl/dist/mapbox-gl.css";

export interface MapViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch: number;
  bearing: number;
}

export interface MapContainerProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  viewState: MapViewState;
  onViewStateChange: (e: { viewState: MapViewState }) => void;
  deckLayers: Layer[];
  onDeckClick: (info: PickingInfo) => void;
  onDeckHover: (info: PickingInfo) => void;
  mapboxToken?: string;
  mapboxStyle: string;
  fallbackMapStyle: string;
}

export function MapContainer({
  containerRef,
  viewState,
  onViewStateChange,
  deckLayers,
  onDeckClick,
  onDeckHover,
  mapboxToken,
  mapboxStyle,
  fallbackMapStyle,
}: MapContainerProps) {
  return (
    <div ref={containerRef} className="absolute inset-0" role="application" aria-label="Theater map, conflict region">
      <DeckGL
        viewState={viewState}
        onViewStateChange={onViewStateChange}
        controller={{ dragRotate: false, touchRotate: false }}
        layers={deckLayers}
        onClick={onDeckClick}
        onHover={onDeckHover}
        pickingRadius={12}
        style={{ width: "100%", height: "100%" }}
        getCursor={({ isDragging, isHovering }) =>
          isDragging ? "grabbing" : isHovering ? "pointer" : "grab"
        }
      >
        {mapboxToken ? (
          <MapboxMap
            mapboxAccessToken={mapboxToken}
            mapStyle={mapboxStyle}
            reuseMaps
            dragRotate={false}
            touchPitch={false}
            maxPitch={0}
            pitchWithRotate={false}
          />
        ) : (
          <MapLibreMap
            mapLib={maplibregl}
            mapStyle={fallbackMapStyle}
            reuseMaps
            dragRotate={false}
            touchPitch={false}
            maxPitch={0}
            pitchWithRotate={false}
          />
        )}
      </DeckGL>
    </div>
  );
}
