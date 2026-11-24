// Zugriff auf die Schnittstelle der App. Schreibende Anfragen tragen den Kopf X-AIArena.

export class ApiError extends Error {
  status: number
  kind?: string
  constructor(message: string, status: number, kind?: string) {
    super(message)
    this.status = status
    this.kind = kind
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(method !== 'GET' ? { 'X-AIArena': '1' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('Die App antwortet nicht. Läuft `uv run aiarena4bw` noch?', 0)
  }
  const text = await response.text()
  const data = parse(text)
  if (!response.ok) {
    const detail = data && typeof data === 'object' ? data.detail : data
    throw new ApiError(typeof detail === 'string' ? detail : `Fehler ${response.status}`, response.status, data?.kind)
  }
  return data as T
}

function parse(text: string): any {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export const api = {
  get: <T = any>(path: string) => request<T>('GET', path),
  post: <T = any>(path: string, body: unknown = {}) => request<T>('POST', path, body),
  put: <T = any>(path: string, body: unknown = {}) => request<T>('PUT', path, body),
  patch: <T = any>(path: string, body: unknown = {}) => request<T>('PATCH', path, body),
  del: <T = any>(path: string) => request<T>('DELETE', path),
  /** Rohtext, z. B. CSV oder Runner-Ausgabe. */
  text: async (method: 'GET' | 'POST', path: string, body?: unknown): Promise<string> => {
    const response = await fetch(`/api${path}`, {
      method,
      headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(method !== 'GET' ? { 'X-AIArena': '1' } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    const text = await response.text()
    if (!response.ok) {
      const data = parse(text)
      const detail = data && typeof data === 'object' ? data.detail : null
      throw new ApiError(typeof detail === 'string' ? detail : `Fehler ${response.status}`, response.status)
    }
    return text
  },
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
