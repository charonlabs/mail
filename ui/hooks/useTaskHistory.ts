import { useCallback } from 'react';
import { useAppStore } from '@/lib/store';
import { useSSE } from '@/hooks/useSSE';
import { getClient } from '@/lib/api';

export function useTaskHistory() {
  const { serverUrl, loadTaskIntoChat } = useAppStore();
  const { cancelStream } = useSSE();

  const loadTask = useCallback(
    async (taskId: string) => {
      // Cancel any active stream before loading historical task
      cancelStream();

      const client = getClient(serverUrl);
      const task = await client.getTask(taskId);
      loadTaskIntoChat(task);
      // Tab switches to 'chat' inside loadTaskIntoChat
    },
    [serverUrl, loadTaskIntoChat, cancelStream]
  );

  return { loadTask };
}
