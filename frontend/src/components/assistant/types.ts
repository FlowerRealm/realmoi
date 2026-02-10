export type AppView = "portal" | "cockpit";

export interface TestCase {
  input: string;
  output: string;
}

export interface PromptData {
  problemDescription: string;
  code: string;
  testCases: TestCase[];
  model: string;
  upstreamChannel?: string;
  reasoningEffort?: "low" | "medium" | "high" | "xhigh";
  timeLimitMs: number;
  memoryLimitMb: number;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  jobId?: string;
  messageKey?: string;
  streaming?: boolean;
}

export interface JobRun {
  jobId: string;
  createdAt: number;
  userMessage?: string;
  status?: string;
  seedMainCpp?: string;
}

export interface AssistantSession {
  id: string;
  title: string;
  timestamp: number;
  prompt: PromptData;
  messages: Message[];
  runs: JobRun[];
}

export type ModelItem = {
  model: string;
  upstream_channel?: string;
  display_name?: string;
  currency?: string;
  unit?: string;
};

export type JobState = {
  job_id: string;
  owner_user_id: string;
  status: string;
  model?: string;
  reasoning_effort?: "low" | "medium" | "high" | "xhigh";
  search_mode?: string;
  created_at?: string;
  finished_at?: string | null;
  expires_at?: string | null;
  error?: unknown;
};

export type SolutionArtifact = {
  schema_version: string;
  job_id: string;
  solution_idea: string;
  seed_code_idea: string;
  seed_code_bug_reason: string;
  user_feedback_md?: string;
  seed_code_issue_type?: "wrong_approach" | "minor_bug" | "no_seed_code" | string;
  seed_code_wrong_lines?: number[];
  seed_code_fix_diff?: string;
  seed_code_full_diff?: string;
  assumptions?: string[];
  complexity?: string;
};
