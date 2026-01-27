import { useCallback } from 'react';
import { useAppStore } from '@/lib/store';
import { cancelActiveStream } from '@/lib/sseControl';
import { getClient } from '@/lib/api';

export function useTaskHistory() {
  const { serverUrl, loadTaskIntoChat } = useAppStore();
  const loadTask = useCallback(
    async (taskId: string) => {
      // Cancel any active stream before loading historical task
      cancelActiveStream();

      const client = getClient(serverUrl);
      const task = await client.getTask(taskId);
      loadTaskIntoChat(task);
      // Tab switches to 'chat' inside loadTaskIntoChat
    },
    [serverUrl, loadTaskIntoChat]
  );

  return { loadTask };
}
