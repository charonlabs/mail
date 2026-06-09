'use client';

import { useState, useMemo } from 'react';
import { motion } from 'motion/react';
import { useAppStore } from '@/lib/store';
import { useSSE } from '@/hooks/useSSE';
import {
  Zap,
  Terminal,
  Download,
  MessageSquare,
  History,
  Plus,
  PanelRightOpen,
} from 'lucide-react';
import { TaskHistoryContent } from './TaskHistoryContent';
import { ChatTabContent } from './ChatTabContent';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export function CollapsibleChatSidebar() {
  const [copiedTaskId, setCopiedTaskId] = useState(false);

  const {
    connectionStatus,
    currentTaskId,
    entrypoint,
    sidebarTab,
    setSidebarTab,
    startNewTask,
    isChatExpanded,
    toggleChatExpanded,
    lastChatCollapseTime,
    messages,
    serverUrl,
  } = useAppStore();

  const { cancelStream } = useSSE();

  // Check if there are unseen messages (messages newer than last collapse time)
  const hasUnseenMessages = useMemo(() => {
    if (isChatExpanded) return false;
    if (!lastChatCollapseTime) return false;
    if (messages.length === 0) return false;

    // Check if any assistant message is newer than last collapse time
    return messages.some((msg) => {
      if (msg.role !== 'assistant') return false;
      const msgTime = new Date(msg.timestamp).getTime();
      return msgTime > lastChatCollapseTime;
    });
  }, [isChatExpanded, lastChatCollapseTime, messages]);

  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'connected':
        return 'bg-green-500';
      case 'connecting':
        return 'bg-gold animate-pulse';
      case 'error':
        return 'bg-destructive';
      default:
        return 'bg-muted-foreground';
    }
  };

  const handleDumpEvents = async () => {
    try {
      const response = await fetch(`${serverUrl}/ui/dump-events`);
      const data = await response.json();
      console.log('[DEBUG] Events dumped:', data);
      alert(`Dumped ${data.event_count} events to events_dump.jsonl`);
    } catch (error) {
      console.error('[DEBUG] Failed to dump events:', error);
      alert('Failed to dump events - check console');
    }
  };

  // Sidebar width: 320px collapsed, 250px expanded
  const sidebarWidth = isChatExpanded ? 250 : 320;

  return (
    <TooltipProvider delayDuration={300}>
      <motion.div
        className="h-full flex flex-col bg-sidebar border-r border-sidebar-border relative"
        animate={{ width: sidebarWidth }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
      >
        {/* Header */}
        <div className="p-4 border-b border-sidebar-border">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded bg-card border border-border flex items-center justify-center">
              <Terminal className="w-4 h-4 text-primary" />
            </div>
            <div>
              <h1 className="font-sans font-bold text-foreground tracking-tight">
                SWARM CONSOLE
              </h1>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <div className={`w-2 h-2 rounded-full ${getStatusColor()}`} />
                <span className="capitalize">{connectionStatus}</span>
              </div>
            </div>
          </div>

          {/* Target/Task/Dump Events and New Task button row */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              {/* Target indicator */}
              {entrypoint && (
                <div className="flex items-center gap-2 text-xs">
                  <Zap className="w-3 h-3 text-gold" />
                  <span className="text-muted-foreground">Target:</span>
                  <span className="text-gold font-medium">{entrypoint}</span>
                </div>
              )}

              {/* Active task indicator */}
              {currentTaskId && (
                <div className="mt-2 text-xs text-muted-foreground font-mono flex items-center gap-1.5">
                  <span>Task:</span>
                  <Tooltip open={copiedTaskId ? true : undefined}>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(currentTaskId);
                          setCopiedTaskId(true);
                          setTimeout(() => setCopiedTaskId(false), 1500);
                        }}
                        className="hover:text-primary transition-colors"
                      >
                        {currentTaskId.slice(0, 16)}...
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>
                      {copiedTaskId ? 'Copied!' : 'Click to copy task ID'}
                    </TooltipContent>
                  </Tooltip>
                </div>
              )}

              {/* Debug: Dump events button */}
              {connectionStatus === 'connected' && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={handleDumpEvents}
                      className="mt-2 flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors"
                    >
                      <Download className="w-3 h-3" />
                      <span>Dump Events</span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>Dump all events to JSONL file</TooltipContent>
                </Tooltip>
              )}
            </div>

            {/* New Task button */}
            {connectionStatus === 'connected' && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => {
                      cancelStream();
                      startNewTask();
                    }}
                    className="
                      flex items-center gap-1.5 pl-1.5 pr-3.5 py-1.5
                      text-xs font-medium
                      bg-primary/10 hover:bg-primary/20
                      text-primary border border-primary/30
                      rounded transition-colors
                    "
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>New</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent>Start a new task</TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>

        {/* Expanded mode: History only, no tabs */}
        {isChatExpanded ? (
          <TaskHistoryContent />
        ) : (
          <>
            {/* Tab Navigation (collapsed mode only) */}
            <div className="flex border-b border-sidebar-border">
              <button
                onClick={() => setSidebarTab('chat')}
                className={`
                  flex-1 py-2 text-sm font-medium transition-colors flex items-center justify-center gap-1.5
                  ${
                    sidebarTab === 'chat'
                      ? 'text-primary border-b-2 border-primary'
                      : 'text-muted-foreground hover:text-foreground'
                  }
                `}
              >
                <MessageSquare className="w-3.5 h-3.5" />
                Chat
              </button>
              <button
                onClick={() => setSidebarTab('history')}
                className={`
                  flex-1 py-2 text-sm font-medium transition-colors flex items-center justify-center gap-1.5
                  ${
                    sidebarTab === 'history'
                      ? 'text-primary border-b-2 border-primary'
                      : 'text-muted-foreground hover:text-foreground'
                  }
                `}
              >
                <History className="w-3.5 h-3.5" />
                History
              </button>
            </div>

            {/* Tab Content */}
            {sidebarTab === 'history' ? (
              <TaskHistoryContent />
            ) : (
              <ChatTabContent />
            )}
          </>
        )}

        {/* Floating expand button (collapsed mode only) */}
        {!isChatExpanded && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={toggleChatExpanded}
                className="
                  absolute top-4 right-4
                  w-7 h-7 rounded
                  flex items-center justify-center
                  bg-card/80 backdrop-blur-sm
                  border border-border
                  text-muted-foreground hover:text-foreground
                  hover:bg-card
                  transition-colors
                "
              >
                <PanelRightOpen className="w-4 h-4" />
                {/* Notification badge for unseen messages */}
                {hasUnseenMessages && (
                  <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-primary rounded-full animate-pulse" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent>
              {hasUnseenMessages ? 'New messages - Expand chat' : 'Expand chat'}
            </TooltipContent>
          </Tooltip>
        )}
      </motion.div>
    </TooltipProvider>
  );
}
