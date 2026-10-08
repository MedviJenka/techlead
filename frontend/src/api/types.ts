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
  configuration: Record<string, unknown>
  custom_field_definitions: Record<string, unknown>[]
  ai_configuration: AIConfiguration
  created_at: string
  updated_at: string
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
