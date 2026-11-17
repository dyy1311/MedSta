export interface PlanStep {
  step_id?: string | null;
  title: string;
  method: string;
  target_columns: string[];
  chart_type: string;
  params: Record<string, unknown>;
  rationale?: string;
}

export type PlanAction = "confirm" | "revise" | "explain" | "custom" | "supplement";

export interface PlanOption {
  id: string;
  label: string;
  action: PlanAction;
  description?: string;
}

export interface IntercurrentEvent {
  event: string;
  strategy: string;
}

export interface EstimandSpec {
  population: string;
  variable: string;
  treatment: string;
  intercurrent_events: IntercurrentEvent[];
  summary_measure: string;
}

export interface PlanEvent {
  type: "plan";
  message: string;
  steps: PlanStep[];
  options: PlanOption[];
  estimand?: EstimandSpec | null;
  sap_status?: string;
}

/** 变量类型四槽位 */
export type ColumnType = "continuous" | "ordinal" | "categorical" | "index";

export const COLUMN_TYPE_LABELS: Record<string, string> = {
  continuous: "数值-连续型",
  ordinal: "数值-等级型",
  categorical: "类别型",
  index: "序列索引",
  datetime: "日期",
  boolean: "布尔",
  text: "文本",
};

export interface ColumnProfile {
  name: string;
  type: string;
  missing: number;
  stats: Record<string, number | string | null>;
}

export interface TableProfile {
  row_count: number;
  column_count: number;
  columns: Record<string, ColumnProfile>;
  type_confirmed: boolean;
}

export interface StepInterpretation {
  step_index: number;
  finding: string;
  caveat: string;
}

export interface Interpretation {
  summary: string;
  steps: StepInterpretation[];
  caveats: string[];
  unverified_numbers: string[];
}

export interface ReportStep {
  title: string;
  method: string;
  status: string;
  result: Record<string, unknown>;
  artifact: string | null;
  table?: { columns: string[]; rows: Record<string, unknown>[] } | null;
  error?: { code: string; message: string; hint?: string } | null;
}

export interface ExecutionReport {
  report_id?: string;
  steps: ReportStep[];
  interpretation?: Interpretation | null;
}

export interface AppErrorPayload {
  code: string;
  message: string;
  hint?: string;
  detail?: unknown;
}

export interface WorkspaceTab {
  datasetId: string;
  name: string;
  profile: TableProfile;
  reports: ExecutionReport[];
  imputed?: boolean;
}

export interface ChartConfigRequest {
  steps: { step_id: string; title: string; default_chart: string }[];
  multi_chart: boolean;
  alpha: number;
  correction: string;
  message: string;
}

export interface TypeReviewRequest {
  dataset_id?: string;
  columns: { name: string; type: string; missing: number }[];
  message: string;
}

export interface PlotSuggestStep {
  step_index: number;
  title: string;
  charts: string[];
}

export interface ToolParam {
  name: string;
  type: string;
  required: boolean;
  description: string;
  choices: string[];
}

export interface ToolCapability {
  name: string;
  title: string;
  category: string;
  description: string;
  task: string;
  applicability: string;
  slots: string[];
  params: ToolParam[];
  charts: string[];
}

export interface Capabilities {
  tools: ToolCapability[];
  charts: { name: string; label: string }[];
  planned: { name: string; title: string; description: string }[];
  methodology: string;
}

export type Phase =
  | "idle"
  | "thinking"
  | "chart_config"
  | "executing"
  | "interrupted"
  | "delivered";

export interface ColumnTypeSuggestion {
  name: string;
  suggested_type: string;
  confidence: number;
  reason: string;
}

export type WsEvent =
  | {
      type: "data_profile";
      dataset_id?: string;
      name?: string;
      type_confirmed?: boolean;
      profile: TableProfile;
    }
  | {
      /** 041 模型辅助列类型确认：建议列表（用户采纳后生效） */
      type: "column_type_suggestions";
      suggestions: ColumnTypeSuggestion[];
      skipped?: string[];
    }
  | PlanEvent
  | { type: "review_request"; report: ExecutionReport; updated?: boolean }
  | ({ type: "interpretation" } & Interpretation)
  | {
      type: "answer";
      answer: string;
      caveats: string[];
      unverified_numbers: string[];
    }
  | {
      type: "dataset_added";
      dataset_id: string;
      name: string;
      profile: TableProfile;
      imputed: boolean;
      source_dataset_id: string | null;
    }
  | { type: "delivered"; report: ExecutionReport }
  | { type: "back_to_discussion"; message: string }
  | { type: "stream"; channel: string; delta: string }
  | {
      type: "progress";
      stage: string;
      step?: number;
      total?: number;
      title?: string;
      message?: string;
    }
  | { type: "interrupted"; stage: string; message: string }
  | { type: "resumed"; stage: string; message?: string }
  | ({ type: "chart_config" } & ChartConfigRequest)
  | ({ type: "type_review" } & TypeReviewRequest)
  | { type: "type_confirmed"; dataset_id?: string; profile: TableProfile }
  | { type: "plot_suggest"; steps: PlotSuggestStep[] }
  | ({ type: "error" } & AppErrorPayload);

export type ChatMessage =
  | { role: "user"; kind: "text"; content: string }
  | { role: "system"; kind: "notice"; content: string }
  | { role: "system"; kind: "thinking"; content: string }
  | ({ role: "system"; kind: "plan" } & PlanEvent)
  | {
      role: "system";
      kind: "review";
      report: ExecutionReport;
      delivered: boolean;
    }
  | {
      role: "system";
      kind: "answer";
      content: string;
      caveats: string[];
      unverified: string[];
    }
  | ({ role: "system"; kind: "error" } & AppErrorPayload);
