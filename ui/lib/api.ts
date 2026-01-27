import type { AgentsResponse, MessageResponse, TaskSummary, TaskWithEvents } from '@/types/mail';
import type { EvalConfig } from '@/lib/store';

export class MAILClient {
  private baseUrl: string;
  private authToken: string;

  constructor(baseUrl: string, authToken?: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.authToken = authToken || 'user:default';
  }

  private get headers(): HeadersInit {
    return {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${this.authToken}`,
    };
  }

  async getAgents(): Promise<AgentsResponse> {
    const response = await fetch(`${this.baseUrl}/ui/agents`, {
      headers: this.headers,
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch agents: ${response.statusText}`);
    }

    return response.json();
  }

  async getServerInfo(): Promise<{
    name: string;
    protocol_version: string;
    swarm: {
      name: string;
      description: string;
      entrypoint: string;
    };
    status: string;
  }> {
    const response = await fetch(`${this.baseUrl}/`, {
      headers: this.headers,
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch server info: ${response.statusText}`);
    }

    return response.json();
  }

  async getTasks(): Promise<TaskSummary[]> {
    const response = await fetch(`${this.baseUrl}/ui/tasks`, {
      headers: this.headers,
    });
    if (!response.ok) throw new Error('Failed to fetch tasks');
    return response.json();
  }

  async getTask(taskId: string): Promise<TaskWithEvents> {
    const response = await fetch(`${this.baseUrl}/ui/task/${taskId}`, {
      headers: this.headers,
    });
    if (!response.ok) throw new Error('Failed to fetch task');
    return response.json();
  }

  async getTaskSummary(taskId: string, forceRegen?: boolean): Promise<{ task_id: string; title: string | null }> {
    const url = forceRegen
      ? `${this.baseUrl}/ui/task-summary/${taskId}?force_regen=true`
      : `${this.baseUrl}/ui/task-summary/${taskId}`;
    const response = await fetch(url, {
      headers: this.headers,
    });
    if (!response.ok) throw new Error('Failed to fetch task summary');
    return response.json();
  }

  async postEvalConfig(config: EvalConfig): Promise<void> {
    const response = await fetch(`${this.baseUrl}/ui/config`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({
        eval_set: config.evalSet,
        q_idx: config.qIdx,
        model_id: config.modelId,
        reflector_model: config.reflectorModel,
        pass_threshold: config.passThreshold,
        run_reflection: config.runReflection,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to set eval config: ${response.statusText}`);
    }
  }

  async postMessage(
    body: string,
    options?: {
      subject?: string;
      entrypoint?: string;
      taskId?: string;
      stream?: boolean;
      resumeFrom?: 'user_response' | null;
    }
  ): Promise<Response> {
    const payload: Record<string, unknown> = {
      body,
      subject: options?.subject || 'User Message',
      entrypoint: options?.entrypoint,
      task_id: options?.taskId,
      stream: options?.stream ?? true,
    };

    // Add resume_from for follow-up messages
    if (options?.resumeFrom) {
      payload.resume_from = options.resumeFrom;
    }

    // Use /ui/message for dev (no auth required when debug=true)
    const response = await fetch(`${this.baseUrl}/ui/message`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Failed to post message: ${response.statusText}`);
    }

    return response;
  }

  async postMessageSync(
    body: string,
    options?: {
      subject?: string;
      entrypoint?: string;
      taskId?: string;
    }
  ): Promise<MessageResponse> {
    const response = await this.postMessage(body, {
      ...options,
      stream: false,
    });
    return response.json();
  }

  createSSEConnection(
    body: string,
    options?: {
      subject?: string;
      entrypoint?: string;
      taskId?: string;
    }
  ): EventSource | null {
    // EventSource doesn't support POST, so we use fetch with streaming
    return null;
  }

  async *streamMessage(
    body: string,
    options?: {
      subject?: string;
      entrypoint?: string;
      taskId?: string;
      resumeFrom?: 'user_response' | null;
    }
  ): AsyncGenerator<{ event: string; data: unknown }, void, unknown> {
    const response = await this.postMessage(body, {
      ...options,
      stream: true,
    });

    if (!response.body) {
      throw new Error('No response body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by double CRLF
        const events = buffer.split('\r\n\r\n');
        // Keep the last potentially incomplete event in the buffer
        buffer = events.pop() || '';

        for (const eventBlock of events) {
          if (!eventBlock.trim()) continue;

          let eventType = 'message';
          let eventData = '';

          const lines = eventBlock.split('\r\n');
          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              eventData = line.slice(5).trim();
            }
          }

          if (eventData) {
            try {
              // Server now sends proper JSON
              const parsed = JSON.parse(eventData);
              yield { event: eventType, data: parsed };
            } catch (parseError) {
              // Fallback: yield raw string data if parsing fails
              console.warn('[API] Parse failed for event:', eventType, 'Error:', parseError, 'Raw:', eventData.slice(0, 200));
              yield { event: eventType, data: eventData };
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
}

// Singleton instance
let clientInstance: MAILClient | null = null;

export function getClient(baseUrl?: string): MAILClient {
  const url = baseUrl || process.env.NEXT_PUBLIC_MAIL_SERVER_URL || 'http://localhost:8000';

  if (!clientInstance || (baseUrl && clientInstance['baseUrl'] !== url)) {
    clientInstance = new MAILClient(url);
  }

  return clientInstance;
}
