const API_BASE = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

type ErrorBody = {
  error?: { code: string; message: string }
  detail?: { msg: string; loc: (string | number)[] }[] | string
}

function describe(body: ErrorBody, status: number): ApiError {
  if (body.error) return new ApiError(status, body.error.code, body.error.message)
  if (Array.isArray(body.detail)) {
    const message = body.detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join('; ')
    return new ApiError(status, 'validation_error', message)
  }
  return new ApiError(status, 'http_error', typeof body.detail === 'string' ? body.detail : `HTTP ${status}`)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body: unknown = await response.json().catch(() => ({}))
  if (!response.ok) throw describe(body as ErrorBody, response.status)
  return body as T
}
