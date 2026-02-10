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

export type JobTestMeta = {
  name: string;
  group: string;
  input_rel: string;
  expected_rel: string | null;
  expected_present: boolean;
};

export type JobTestPreview = {
  input: { text: string; truncated: boolean; bytes: number };
  expected: { text: string; truncated: boolean; bytes: number; missing?: boolean } | null;
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

export type ReportArtifact = {
  schema_version?: string;
  job_id?: string;
  owner_user_id?: string;
  status?: string;
  mode?: string;
  environment?: {
    time_limit_ms?: number;
    memory_limit_mb?: number;
    cpus?: number;
    pids_limit?: number;
    max_output_bytes_per_test?: number;
    compare_mode?: string;
    cpp_std?: string;
  };
  compile?: {
    ok?: boolean;
    exit_code?: number;
    stdout_b64?: string;
    stderr_b64?: string;
    stdout_truncated?: boolean;
    stderr_truncated?: boolean;
  };
	  tests?: Array<{
	    name?: string;
	    group?: string;
	    input_rel?: string;
	    expected_rel?: string | null;
	    expected_present?: boolean;
	    verdict?: string;
	    exit_code?: number;
	    timeout?: boolean;
	    output_limit_exceeded?: boolean;
	    time_ms?: number;
	    memory_kb?: number | null;
	    stdout_b64?: string;
	    stderr_b64?: string;
	    stdout_truncated?: boolean;
	    stderr_truncated?: boolean;
	    diff?: {
      ok?: boolean;
      mode?: string;
      message?: string;
      expected_preview_b64?: string;
      actual_preview_b64?: string;
    };
  }>;
  summary?: {
    total?: number;
    judged?: number;
    run_only?: number;
    passed?: number;
    failed?: number;
    skipped?: number;
    first_failure?: string | null;
    first_failure_verdict?: string | null;
    first_failure_message?: string | null;
  };
  error?: unknown;
};
