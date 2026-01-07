'use client';

import { useCallback, useRef, useEffect } from 'react';
import { useAppStore } from '@/lib/store';
import { getClient } from '@/lib/api';
import type { MAILEvent } from '@/types/mail';
import { v4 as uuidv4 } from 'uuid';

export function useSSE() {
  const abortControllerRef = useRef<AbortController | null>(null);
  const {
    serverUrl,
    addEvent,
    addMessage,
    setCurrentTaskId,
    setIsProcessing,
    currentTaskId,
    entrypoint,
  } = useAppStore();

  const sendMessage = useCallback(
    async (content: string) => {
      const client = getClient(serverUrl);

      // If we have a currentTaskId, we're resuming a conversation
      const isResuming = !!currentTaskId;
      const taskId = currentTaskId || uuidv4();

      // Add user message to chat
      addMessage({
        id: uuidv4(),
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
        task_id: taskId,
      });

      setCurrentTaskId(taskId);
      setIsProcessing(true);
      // Don't change connection status - we're already connected

      // Abort any existing stream
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      try {
        let responseContent = '';

        for await (const { event, data } of client.streamMessage(content, {
          taskId,
          entrypoint: entrypoint || undefined,
          resumeFrom: isResuming ? 'user_response' : null,
        })) {
          if (abortControllerRef.current?.signal.aborted) break;

          // Handle different event types
          console.log('[SSE] Event received:', event, 'Data:', JSON.stringify(data, null, 2));

          if (event === 'task_complete') {
            const eventData = data as { response?: string; task_id?: string };
            console.log('[SSE] task_complete - response field:', eventData.response);
            responseContent = eventData.response || responseContent;

            // Add assistant response
            if (responseContent) {
              addMessage({
                id: uuidv4(),
                role: 'assistant',
                content: responseContent,
                timestamp: new Date().toISOString(),
                task_id: taskId,
              });
            } else {
              console.warn('[SSE] task_complete had no response content');
            }

            // Keep task ID for follow-up messages (resume_from: user_response)
            break;
          } else if (event === 'task_error') {
            const eventData = data as { response?: string; task_id?: string };
            addMessage({
              id: uuidv4(),
              role: 'system',
              content: `Error: ${eventData.response || 'Unknown error'}`,
              timestamp: new Date().toISOString(),
              task_id: taskId,
            });
            // Keep task ID for retry
            break;
          } else if (event !== 'ping') {
            // Add to events stream
            const eventData = data as Partial<MAILEvent>;
            const mailEvent: MAILEvent = {
              id: uuidv4(),
              event: event as MAILEvent['event'],
              timestamp: eventData.timestamp || new Date().toISOString(),
              description: eventData.description || event,
              task_id: eventData.task_id || taskId,
              extra_data: eventData.extra_data,
            };
            addEvent(mailEvent);
          }
        }
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          console.error('SSE Error:', error);
          addMessage({
            id: uuidv4(),
            role: 'system',
            content: `Error: ${(error as Error).message}`,
            timestamp: new Date().toISOString(),
            task_id: taskId,
          });
        }
      } finally {
        setIsProcessing(false);
      }
    },
    [
      serverUrl,
      currentTaskId,
      entrypoint,
      addEvent,
      addMessage,
      setCurrentTaskId,
      setIsProcessing,
    ]
  );

  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsProcessing(false);
  }, [setIsProcessing]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return { sendMessage, cancelStream };
}
