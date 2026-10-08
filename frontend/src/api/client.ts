import { accessToken, supabase } from '../auth/supabase'

const API_BASE = `/api/${import.meta.env.VITE_API_VERSION ?? 'v1'}`

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

// Every backend error (domain, validation, HTTP, unhandled) uses this envelope; see app/core/errors.py.
type ErrorBody = {
  error?: { code: string; message: string }
}

function describe(body: ErrorBody, status: number): ApiError {
  if (body.error) return new ApiError(status, body.error.code, body.error.message)
  // Non-JSON responses (e.g. a proxy's HTML 502) never reach the API's error handlers.
  return new ApiError(status, 'http_error', `HTTP ${status}`)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await accessToken()
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...init?.headers,
    },
  })
  const body: unknown = await response.json().catch(() => ({}))
  // The backend rejected the session (expired or revoked): back to the sign-in page.
  if (response.status === 401) await supabase.auth.signOut()
  if (!response.ok) throw describe(body as ErrorBody, response.status)
  return body as T
}
