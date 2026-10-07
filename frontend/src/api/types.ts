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
