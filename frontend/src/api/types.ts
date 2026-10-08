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
  extra_skills: string[]
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
// POST /leads/{id}/analyze (app/schemas/analysis.py). The recommendation is advice; its priority is the AI's view.
export type LeadAnalysis = {
  lead: LeadDetail
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
