export type Severity = "info" | "warning" | "error";
export type InsightSeverity = "integrity" | "structural" | "variance" | "info";

export interface AnalysisResponse {
  metadata: {
    request_id: string;
    engine_version: string;
    left_filename: string;
    right_filename: string;
  };
  analysis: AnalysisResult;
}

export interface AnalysisResult {
  comparison: Comparison;
  left_profile: DatasetProfile;
  right_profile: DatasetProfile;
  warnings: Diagnostic[];
  insights: Insight[];
}

export interface Comparison {
  alignment: {
    row_basis: "key" | "position" | "none";
    row_key: string | null;
    row_confidence: number;
  };
  schema: {
    matched: ColumnMatch[];
    added: string[];
    removed: string[];
    retyped: ColumnTypeChange[];
    order_changed: boolean;
  };
  rows: {
    changed: number;
    unchanged: number;
    added: number;
    removed: number;
    changes: RowChange[];
  };
}

export interface ColumnMatch {
  left: string;
  right: string;
  basis: string;
  confidence: number;
}

export interface ColumnTypeChange {
  left: string;
  right: string;
  from: string;
  to: string;
}

export interface RowChange {
  key: string | null;
  left_row: number;
  right_row: number;
  cells: CellChange[];
}

export interface CellChange {
  column: string;
  before: string | number | boolean | null;
  after: string | number | boolean | null;
  kind: "numeric" | "categorical" | "added" | "removed" | string;
  delta?: number;
  pct_change?: number;
}

export interface DatasetProfile {
  name: string;
  n_rows: number;
  n_columns: number;
  columns: ColumnProfile[];
}

export interface ColumnProfile {
  name: string;
  type: string;
  count: number;
  null_count: number;
  non_null_count: number;
  unique_count: number;
  stats: Record<string, unknown>;
}

export interface Diagnostic {
  severity: Severity;
  code: string;
  message: string;
  location?: string;
  confidence?: number;
}

export interface Insight {
  code: string;
  severity: InsightSeverity;
  message: string;
  evidence: string[];
}
