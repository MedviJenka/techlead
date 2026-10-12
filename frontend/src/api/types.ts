// Mirrors app/schemas (backend). Keep in sync until we generate types from the OpenAPI schema.

export type HealthStatus = {
  status: 'ok' | 'degraded'
  database: 'ok' | 'unavailable'
}

export type AIConfiguration = {
  tone: string
  language: string
  autonomy_level: number
  allowed_actions: string[]
  approval_required_actions: string[]
  instructions: string | null
}

// The signed-in user; `business_id` is null until they create a business (one per user).
export type Me = {
  id: string
  email: string | null
  business_id: string | null
  role: string | null
}

export type Business = {
  id: string
  name: string
  slug: string
  industry: string | null
  timezone: string
  configuration: BusinessConfiguration
  custom_field_definitions: CustomFieldDefinition[]
  ai_configuration: AIConfiguration
  created_at: string
  updated_at: string
}

// app/schemas/configuration.py: deterministic scoring, priority and follow-up settings.
export type PriorityName = 'critical' | 'high' | 'medium' | 'low'
export type Scalar = string | number | boolean
export type ConditionOp = 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'contains' | 'exists' | 'missing'
export type Condition = { fact: string; op: ConditionOp; value: Scalar | Scalar[] | null }
export type ScoringRule = { id: string; label: string; points: number; when: Condition[] }
export type BusinessConfiguration = {
  closed_statuses: string[]
  scoring: { base_score: number; ai_weight: number; rules: ScoringRule[] }
  priority: { critical: number; high: number; medium: number }
  follow_up: {
    first_response_hours: Record<PriorityName, number>
    interval_hours: Record<PriorityName, number>
    status_interval_hours: Record<string, number>
  }
  // ISO country code (e.g. "IL"): local phone numbers are stored in international format for it.
  phone_region?: string | null
}
export type CustomFieldType = 'text' | 'number' | 'boolean' | 'date' | 'select'
export type CustomFieldDefinition = { key: string; label: string; type: CustomFieldType; options: string[] }
export type BusinessSettings = {
  configuration: BusinessConfiguration
  custom_field_definitions: CustomFieldDefinition[]
}

export type BusinessCreate = {
  name: string
  slug: string
  industry?: string | null
  timezone?: string
  // An industry preset (GET /businesses/presets) fills custom fields, scoring and AI instructions.
  preset?: string | null
}
export type Preset = {
  key: string
  label: string
  industry: string
  description: string
  custom_field_definitions: CustomFieldDefinition[]
}

export type Page<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
}
export type Lead = {
  id: string
  external_id: string | null
  source: string
  status: string
  priority: string | null
  first_name: string | null
  last_name: string | null
  email: string | null
  phone: string | null
  company_name: string | null
  lead_score: number | null
  sentiment: string | null
  recommended_action: string | null
  last_contact_at: string | null
  created_at: string
  updated_at: string
  // Lead list and detail only (not the dashboard's top leads); null for closed leads.
  follow_up?: FollowUp | null
}
export type FollowUp = {
  due_at: string
  overdue: boolean
  reason: 'first_response' | 'status' | 'interval'
}
export type ScoreBreakdown = {
  base: number
  deterministic: number
  ai: number | null
  ai_weight: number
  final: number
  matched: { id: string; label: string; points: number }[]
}
export type RescoreResult = { total: number; changed: number }
// POST /leads/{id}/analyze queues a job (app/schemas/analysis.py); pending/running is "analysis pending".
export type AnalysisJobStatus = 'pending' | 'running' | 'succeeded' | 'failed'
export type AnalysisJob = {
  id: string
  lead_id: string
  trigger: 'lead_created' | 'manual'
  status: AnalysisJobStatus
  attempts: number
  max_attempts: number
  run_after: string
  last_error: string | null
  cost_usd: string | null
  created_at: string
  finished_at: string | null
}
// GET /leads/{id}/analysis: the latest job and the latest saved analysis.
export type LeadAnalysisState = { job: AnalysisJob | null; result: SavedAnalysis | null }
// The AI's saved analysis. The recommendation is advice; its priority is the AI's view.
export type SavedAnalysis = {
  analysed_at: string
  qualification: {
    qualified: boolean
    confidence: number
    intent: string
    urgency: string
    fit: string
    missing_information: string[]
    positive_signals: string[]
    negative_signals: string[]
    summary: string
  }
  ai_score: { overall_ai_score: number; reasons: string[] }
  recommendation: {
    action: string
    priority: string
    reason: string
    due_at: string | null
    requires_human_approval: boolean
    talking_points: string[]
  }
}
export type LeadDetail = Lead & {
  notes: string | null
  ai_summary: string | null
  custom_fields: Record<string, unknown>
}
export type Activity = {
  id: string
  lead_id: string
  activity_type: string
  channel: string | null
  description: string
  metadata: Record<string, unknown>
  created_at: string
}
export type Bucket = { key: string; count: number }
export type Dashboard = {
  counts: {
    total: number
    new: number
    hot: number
    qualified: number
    needs_follow_up: number
    waiting_for_proposal: number
    inactive: number
    average_score: number | null
  }
  by_source: Bucket[]
  by_status: Bucket[]
  by_score: Bucket[]
  responses: {
    median_first_response_seconds: number | null
    responded: number
    without_response: number
    pending_approvals: number
  }
  recent_activity: (Omit<Activity, 'metadata'> & { lead_name: string | null })[]
  top_leads: Lead[]
  generated_at: string
}
export type ImportResult = {
  created: number
  updated: number
  skipped: number
  failed: number
  results: {
    index: number
    external_id: string | null
    outcome: string
    lead_id: string | null
    errors: { loc: (string | number)[]; msg: string; type: string }[] | null
  }[]
}

// app/schemas/reply.py: AI-drafted replies the owner approves, edits or rejects.
export type ReplyDraftStatus = 'pending_approval' | 'awaiting_edit' | 'sending' | 'sent' | 'rejected' | 'failed'
export type ReplyDraft = {
  id: string
  lead_id: string
  channel: string
  message: string
  objective: string | null
  status: ReplyDraftStatus
  edited: boolean
  decided_via: 'whatsapp' | 'dashboard' | 'auto' | null
  last_error: string | null
  created_at: string
  decided_at: string | null
  sent_at: string | null
  // When it is sent by itself if nobody decides first (null: it waits for a decision).
  auto_send_at: string | null
  lead_name?: string | null
}
export type WhatsAppConnection = {
  phone_number_id: string
  display_phone?: string | null
  owner_phone: string
  // An undecided first reply is sent by itself after this many minutes; null: never.
  auto_send_after_minutes?: number | null
}
export type WhatsAppStatus = {
  connection: (Required<WhatsAppConnection> & { updated_at: string }) | null
  configured: boolean
  webhook_path: string
}
