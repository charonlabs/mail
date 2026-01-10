'use client';

import { useCallback } from 'react';
import { useAppStore } from '@/lib/store';
import { getClient } from '@/lib/api';
import { startActiveStream, cancelActiveStream, isActiveController } from '@/lib/sseControl';
import type { MAILEvent } from '@/types/mail';
import { v4 as uuidv4 } from 'uuid';

export function useSSE() {
  const {
    serverUrl,
    addEvent,
    addMessage,
    replaceUserMessageForTask,
    setCurrentTaskId,
    setIsProcessing,
    currentTaskId,
    entrypoint,
    isEvalMode,
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

      const controller = startActiveStream();

      try {
        let responseContent = '';

        for await (const { event, data } of client.streamMessage(content, {
          taskId,
          entrypoint: entrypoint || undefined,
          resumeFrom: isResuming ? 'user_response' : null,
        })) {
          if (controller.signal.aborted) break;

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
          } else if (event === 'eval_config') {
            const eventData = data as {
              task_id?: string;
              timestamp?: string;
              extra_data?: { question?: string };
            };
            const question = eventData.extra_data?.question;
            if (isEvalMode && question) {
              const taskIdForMsg = eventData.task_id || taskId;
              const { messages } = useAppStore.getState();
              const hasUserMessage = messages.some(
                (message) => message.role === 'user' && message.task_id === taskIdForMsg
              );

              if (hasUserMessage) {
                replaceUserMessageForTask(taskIdForMsg, question, eventData.timestamp);
              } else {
                addMessage({
                  id: uuidv4(),
                  role: 'user',
                  content: question,
                  timestamp: eventData.timestamp || new Date().toISOString(),
                  task_id: taskIdForMsg,
                });
              }
            }
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
        if (isActiveController(controller)) {
          cancelActiveStream();
        }
      }
    },
    [
      serverUrl,
      currentTaskId,
      entrypoint,
      addEvent,
      addMessage,
      replaceUserMessageForTask,
      setCurrentTaskId,
      setIsProcessing,
      isEvalMode,
    ]
  );

  const cancelStream = useCallback(() => {
    cancelActiveStream();
  }, []);

  return { sendMessage, cancelStream };
}
