'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '@/lib/store';
import { useTaskHistory } from '@/hooks/useTaskHistory';
import { getClient } from '@/lib/api';
import { RefreshCw, Loader2 } from 'lucide-react';
import type { TaskSummary } from '@/types/mail';

function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function TaskListItem({
  task,
  onClick,
  isLoading,
  isFetchingSummary,
}: {
  task: TaskSummary;
  onClick: () => void;
  isLoading: boolean;
  isFetchingSummary: boolean;
}) {
  const timeAgo = formatTimeAgo(task.start_time);

  // Only allow clicking completed tasks (Phase 1)
  // Running tasks will be handled in Phase 2 with "Attach" feature
  const isClickable = task.completed && !isLoading;

  return (
    <button
      onClick={isClickable ? onClick : undefined}
      disabled={!isClickable}
      className={`
        w-full p-3 text-left border-b border-border/30 transition-colors
        ${isClickable ? 'hover:bg-muted/50 cursor-pointer' : 'opacity-60 cursor-not-allowed'}
      `}
      title={
        !task.completed
          ? 'Attach to running tasks coming in Phase 2'
          : isLoading
            ? 'Loading...'
            : undefined
      }
    >
      <div className="flex items-center gap-2 mb-1">
        <span
          className={`
            text-xs px-1.5 py-0.5 rounded
            ${
              task.completed
                ? 'bg-green-500/20 text-green-400'
                : task.is_running
                  ? 'bg-yellow-500/20 text-yellow-400'
                  : 'bg-muted text-muted-foreground'
            }
          `}
        >
          {task.completed ? 'Done' : task.is_running ? 'Running' : 'Paused'}
        </span>
        <span className="text-xs text-muted-foreground">{timeAgo}</span>
        {(isLoading || isFetchingSummary) && (
          <Loader2 className="w-3 h-3 animate-spin text-primary ml-auto" />
        )}
      </div>
      <p className="text-sm truncate text-foreground">
        {task.title || `Task ${task.task_id.slice(0, 8)}...`}
      </p>
      <p className="text-xs text-muted-foreground">{task.event_count} events</p>
    </button>
  );
}

export function TaskHistoryContent() {
  const { taskHistory, setTaskHistory, updateTaskTitle, serverUrl } = useAppStore();
  const { loadTask } = useTaskHistory();
  const [loading, setLoading] = useState(false);
  const [loadingTaskId, setLoadingTaskId] = useState<string | null>(null);
  const [fetchingSummaries, setFetchingSummaries] = useState<Set<string>>(new Set());

  const fetchSummariesForTasks = useCallback(async (tasks: TaskSummary[]) => {
    const client = getClient(serverUrl);

    // Find completed tasks that need summaries (null title)
    const tasksNeedingSummary = tasks.filter((t) => t.completed && t.title === null);
    if (tasksNeedingSummary.length === 0) return;

    // Track which tasks are being fetched
    setFetchingSummaries(new Set(tasksNeedingSummary.map(t => t.task_id)));

    // Fire all requests in parallel
    const summaryPromises = tasksNeedingSummary.map(async (task) => {
      try {
        const result = await client.getTaskSummary(task.task_id);
        if (result.title) {
          updateTaskTitle(task.task_id, result.title);
        }
      } catch (error) {
        console.error(`[TaskHistory] Failed to fetch summary for ${task.task_id}:`, error);
      } finally {
        setFetchingSummaries(prev => {
          const next = new Set(prev);
          next.delete(task.task_id);
          return next;
        });
      }
    });

    // Wait for all to complete (but don't block UI - updates happen as they come in)
    await Promise.allSettled(summaryPromises);
  }, [serverUrl, updateTaskTitle]);

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const client = getClient(serverUrl);
      const tasks = await client.getTasks();
      setTaskHistory(tasks);
      // Fetch summaries in parallel after loading tasks
      fetchSummariesForTasks(tasks);
    } catch (error) {
      console.error('[TaskHistory] Failed to fetch tasks:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (taskHistory.length === 0) {
      fetchTasks();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLoadTask = async (taskId: string) => {
    setLoadingTaskId(taskId);
    try {
      await loadTask(taskId);
    } catch (error) {
      console.error('[TaskHistory] Failed to load task:', error);
    } finally {
      setLoadingTaskId(null);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between p-2 border-b border-border/50">
        <span className="text-sm text-muted-foreground">{taskHistory.length} tasks</span>
        <button
          onClick={fetchTasks}
          disabled={loading}
          className="p-1 hover:bg-muted/50 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 text-muted-foreground ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {taskHistory.length === 0 && !loading ? (
          <div className="p-4 text-center text-muted-foreground text-sm">No tasks yet</div>
        ) : (
          taskHistory.map((task) => (
            <TaskListItem
              key={task.task_id}
              task={task}
              onClick={() => handleLoadTask(task.task_id)}
              isLoading={loadingTaskId === task.task_id}
              isFetchingSummary={fetchingSummaries.has(task.task_id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
