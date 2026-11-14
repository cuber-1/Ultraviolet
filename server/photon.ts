import { randomUUID } from 'node:crypto';

export type PhotonPlatform = 'imessage' | 'sms' | 'telegram' | 'email' | 'whatsapp_business';

type PhotonConfig = { apiKey: string; projectId: string; agentUserId: string };

function config(): PhotonConfig | null {
  const apiKey = process.env.PHOTON_API_KEY;
  const projectId = process.env.PHOTON_PROJECT_ID;
  const agentUserId = process.env.PHOTON_AGENT_USER_ID;
  return apiKey && projectId && agentUserId ? { apiKey, projectId, agentUserId } : null;
}

export function photonStatus() {
  return { configured: Boolean(config()), provider: 'Photon 2.0 beta' };
}

async function post<T>(path: string, value: unknown): Promise<T> {
  const configured = config();
  if (!configured) throw new Error('Photon messaging is not configured. Set PHOTON_API_KEY, PHOTON_PROJECT_ID, and PHOTON_AGENT_USER_ID.');
  const response = await fetch(`https://api.photon.codes/v1/projects/${configured.projectId}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${configured.apiKey}`,
      'Content-Type': 'application/json',
      'idempotency-key': randomUUID(),
    },
    body: JSON.stringify(value),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({})) as { title?: string; detail?: string; code?: string };
    throw new Error(problem.detail || problem.title || problem.code || `Photon returned ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

export async function createPhotonConversation(platform: PhotonPlatform, handle: string) {
  const configured = config();
  if (!configured) throw new Error('Photon messaging is not configured. Set PHOTON_API_KEY, PHOTON_PROJECT_ID, and PHOTON_AGENT_USER_ID.');
  const user = await post<{ id: string }>('/users', { platform, handle });
  const space = await post<{ id: string }>('/spaces', { platform, participantIds: [configured.agentUserId, user.id] });
  return { userId: user.id, spaceId: space.id };
}

export async function sendPhotonMessage(spaceId: string, text: string) {
  const configured = config();
  if (!configured) throw new Error('Photon messaging is not configured.');
  return post<{ id: string; status: string }>('/messages', {
    spaceId,
    senderId: configured.agentUserId,
    content: { type: 'text', format: 'plain', text },
  });
}
