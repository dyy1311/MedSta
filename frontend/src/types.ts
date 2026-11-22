export interface PlanStep {
  step_id?: string | null;
  title: string;
  method: string;
  target_columns: string[];
  chart_type: string;
  params: Record<string, unknown>;
  rationale?: string;
  /** 依赖的前序节点下标（0 起）；空=接在上一步之后（宿主补线性链） */
  depends_on?: number[];
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

/** 方案流程图节点（047）：节点=注册表工具，边=依赖 */
export interface FlowNode {
  index: number;
  id: string;
  title: string;
  method: string;
  target_columns: string[];
  params: Record<string, unknown>;
  chart_type: string;
  rationale: string;
  depends_on: number[];
}

export interface PlanFlow {
  nodes: FlowNode[];
  edges: { from: number; to: number }[];
  order: number[];
  mermaid: string;
}

export interface PlanEvent {
  type: "plan";
  message: string;
  steps: PlanStep[];
  /** 后端生成的流程图（旧后端可能没有） */
  flow?: PlanFlow;
  options: PlanOption[];
  estimand?: EstimandSpec | null;
  sap_status?: string;
}

/** 节点级交付（047）：每个工作节点完成即下发 */
export interface StepDelivery {
  index: number;
  total: number;
  updated?: boolean;
  title: string;
  method: string;
  status: "success" | "failed";
  artifact?: string | null;
  table?: { columns: string[]; rows: Record<string, unknown>[] } | null;
  result?: Record<string, unknown>;
  error?: { code: string; message: string; hint?: string } | null;
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

export interface PlotStyle {
  title?: string;
  xlabel?: string;
  ylabel?: string;
  xticks?: string;
  yticks?: string;
  /** 图上组名：0=对照组,1=试验组 或按出现顺序 对照组,试验组 */
  groups?: string;
  /** 绘图顺序：从左到右 / 图例从上到下，如 1,0 或 试验组,对照组 */
  group_order?: string;
}

export interface ReportStep {
  title: string;
  method: string;
  status: string;
  result: Record<string, unknown>;
  artifact: string | null;
  table?: { columns: string[]; rows: Record<string, unknown>[] } | null;
  error?: { code: string; message: string; hint?: string } | null;
  chart_type?: string;
  plot_style?: PlotStyle;
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
  /** 归属会话：多个会话的数据集共用一个平面数组，展示时必须按会话过滤 */
  sessionId: string;
}

/** GET /sessions/{sid}/workspace：刷新后右栏与会话区同源的快照 */
export interface WorkspaceSnapshot {
  session_id: string;
  status: string;
  active_dataset_id: string | null;
  datasets: {
    dataset_id: string;
    name: string;
    profile: TableProfile;
    type_confirmed: boolean;
    active: boolean;
  }[];
  report: ExecutionReport | null;
  report_id: string | null;
  /** 清空产出事件的 seq：回放时该序号及更早的报告不再挂回工作区 */
  outputs_cleared_seq?: number | null;
}

export interface ChartConfigRequest {
  /** 每步可选图表（后端按工具注册表下发）；缺省时前端回退全量枚举 */
  steps: { step_id: string; title: string; default_chart: string; charts?: string[] }[];
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
      /** active=true 表示该数据集已成为会话的激活工作区（切换/首次绑定） */
      active?: boolean;
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
  | { type: "chat_rejected"; reason: string }
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
  | {
      type: "type_confirmed";
      dataset_id?: string;
      profile: TableProfile;
      /** 本次变更的列（会话区据此生成可核对文案） */
      updated?: string[];
      /** 变更来源：ai=采纳建议 / manual=手动 / type_review=类型审阅 */
      source?: string;
    }
  | {
      type: "step_result";
      stage?: string;
      index: number;
      total: number;
      step: StepDelivery;
    }
  | { type: "plot_suggest"; steps: PlotSuggestStep[] }
  | { type: "workspace_outputs_cleared" }
  | ({ type: "error" } & AppErrorPayload);

export type ChatMessage =
  | { role: "user"; kind: "text"; content: string; seq?: number }
  | { role: "system"; kind: "notice"; content: string }
  | { role: "system"; kind: "thinking"; content: string }
  | ({ role: "system"; kind: "plan" } & PlanEvent)
  | {
      role: "system";
      kind: "review";
      report: ExecutionReport;
      delivered: boolean;
      /** 修正意见已提交（防重复提交，也用于锁定卡片交互） */
      submitted?: boolean;
    }
  | {
      role: "system";
      kind: "answer";
      content: string;
      caveats: string[];
      unverified: string[];
    }
  | ({ role: "system"; kind: "error" } & AppErrorPayload);
