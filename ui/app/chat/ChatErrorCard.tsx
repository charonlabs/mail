'use client';

import { AlertCircle } from 'lucide-react';
import type { MAILEvent } from '@/types/mail';

interface ChatErrorCardProps {
  event: MAILEvent;
}

export function ChatErrorCard({ event }: ChatErrorCardProps) {
  const timestamp = new Date(event.timestamp);
  const description = event.description || 'An error occurred';
  const errorMessage = event.extra_data?.error_message as string | undefined;

  return (
    <div className="my-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
      <div className="flex items-start gap-3">
        <AlertCircle className="size-5 text-destructive shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-destructive text-sm">
              Action Error
            </span>
            <span className="text-xs text-muted-foreground">
              {timestamp.toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>
          <p className="mt-1 text-sm text-destructive/90">
            {description}
          </p>
          {errorMessage && (
            <pre className="mt-2 text-xs bg-destructive/5 rounded p-2 overflow-x-auto whitespace-pre-wrap text-destructive/80">
              {errorMessage}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
