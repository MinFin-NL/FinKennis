import { accessToken } from './auth';

const BASE = '/api/v1';

export type DocumentStatus = 'wachtrij' | 'verwerken' | 'gereed' | 'fout';

export interface Kennisbank {
  id: string;
  naam: string;
  omschrijving: string;
  createdAt: string;
  aantalDocumenten: number;
}

export interface KbDocument {
  id: string;
  bestandsnaam: string;
  mime: string;
  grootte: number;
  status: DocumentStatus;
  foutmelding: string | null;
  aantalChunks: number;
  createdAt: string;
}

export interface Bron {
  nummer: number;
  documentId: string;
  bestandsnaam: string;
  pagina: number | null;
  kopjes: string[];
  fragment: string;
}

export interface Bericht {
  id: string;
  rol: 'user' | 'assistant';
  inhoud: string;
  bronnen: Bron[];
  createdAt: string;
}

export interface Gesprek {
  id: string;
  kennisbankId: string;
  titel: string;
  createdAt: string;
}

export interface GesprekDetail extends Gesprek {
  berichten: Bericht[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(pad: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = await accessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');

  const resp = await fetch(BASE + pad, { ...init, headers });
  if (!resp.ok) throw await toError(resp);
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

async function toError(resp: Response): Promise<ApiError> {
  // De API geeft fouten als application/problem+json.
  try {
    const p = await resp.json();
    return new ApiError(resp.status, p.detail ?? p.title ?? resp.statusText);
  } catch {
    return new ApiError(resp.status, resp.statusText);
  }
}

export const api = {
  kennisbanken: () => request<Kennisbank[]>('/kennisbanken'),
  maakKennisbank: (naam: string, omschrijving: string) =>
    request<Kennisbank>('/kennisbanken', {
      method: 'POST',
      body: JSON.stringify({ naam, omschrijving }),
    }),
  wijzigKennisbank: (id: string, naam: string, omschrijving: string) =>
    request<Kennisbank>(`/kennisbanken/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ naam, omschrijving }),
    }),
  verwijderKennisbank: (id: string) =>
    request<void>(`/kennisbanken/${id}`, { method: 'DELETE' }),

  documenten: (kbId: string) => request<KbDocument[]>(`/kennisbanken/${kbId}/documenten`),
  upload: (kbId: string, bestanden: File[]) => {
    const form = new FormData();
    bestanden.forEach((b) => form.append('bestanden', b));
    return request<{ toegevoegd: KbDocument[]; overgeslagen: string[] }>(
      `/kennisbanken/${kbId}/documenten`,
      { method: 'POST', body: form },
    );
  },
  verwijderDocument: (kbId: string, docId: string) =>
    request<void>(`/kennisbanken/${kbId}/documenten/${docId}`, { method: 'DELETE' }),

  gesprekken: (kbId: string) => request<Gesprek[]>(`/kennisbanken/${kbId}/gesprekken`),
  maakGesprek: (kbId: string) =>
    request<Gesprek>(`/kennisbanken/${kbId}/gesprekken`, { method: 'POST', body: '{}' }),
  gesprek: (id: string) => request<GesprekDetail>(`/gesprekken/${id}`),
  verwijderGesprek: (id: string) => request<void>(`/gesprekken/${id}`, { method: 'DELETE' }),
};

export interface StreamHandlers {
  bronnen: (bronnen: Bron[]) => void;
  token: (tekst: string) => void;
}

/** Stelt een vraag en leest het antwoord als server-sent events uit de POST-response. */
export async function stelVraag(
  gesprekId: string,
  inhoud: string,
  on: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = await accessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const resp = await fetch(`${BASE}/gesprekken/${gesprekId}/berichten`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ inhoud }),
    signal,
  });
  if (!resp.ok || !resp.body) throw await toError(resp);

  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let grens: number;
    while ((grens = buffer.indexOf('\n\n')) >= 0) {
      const blok = buffer.slice(0, grens);
      buffer = buffer.slice(grens + 2);
      let event = 'message';
      let data = '';
      for (const regel of blok.split('\n')) {
        if (regel.startsWith('event: ')) event = regel.slice(7);
        else if (regel.startsWith('data: ')) data += regel.slice(6);
      }
      const payload = JSON.parse(data);
      if (event === 'bronnen') on.bronnen(payload);
      else if (event === 'token') on.token(payload);
      else if (event === 'fout') throw new ApiError(502, payload.detail);
    }
  }
}
