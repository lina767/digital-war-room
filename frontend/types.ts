/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * Full analysis response returned by analyze_conflict / CEO synthesis.
 */
export interface AnalysisResult {
  conflict?: string;
  escalation_score?: number;
  threat_level?: string;
  key_findings?: string[];
  key_findings_context?: string[];
  corroborated_patterns?: {
    [k: string]: unknown;
  }[];
  scenarios?: {
    [k: string]: unknown;
  }[];
  summary?: string;
  narrative_story?: string;
  actors?: {
    [k: string]: unknown;
  }[];
  predictive?: {
    [k: string]: unknown;
  };
  compliance?: {
    [k: string]: unknown;
  };
  alerts?: {
    [k: string]: unknown;
  }[];
  satintel?: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
