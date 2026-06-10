'use client';

import { useState, useRef, useEffect } from 'react';
import { useAppStore } from '@/lib/store';
import { useSSE } from '@/hooks/useSSE';
import { Send, Square, Loader2, Zap, Terminal, Play, Settings, Download, MessageSquare, History, Plus } from 'lucide-react';
import { getClient } from '@/lib/api';
import { TaskHistoryContent } from './TaskHistoryContent';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

export function ChatSidebar() {
  const [input, setInput] = useState('');
  const [copiedTaskId, setCopiedTaskId] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    messages,
    isProcessing,
    connectionStatus,
    currentTaskId,
    entrypoint,
    isEvalMode,
    evalConfig,
    serverUrl,
    sidebarTab,
    setSidebarTab,
    startNewTask,
  } = useAppStore();

  const { sendMessage, cancelStream } = useSSE();

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isProcessing) return;

    const message = input.trim();
    setInput('');
    await sendMessage(message);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

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

  return (
    <TooltipProvider delayDuration={300}>
    <div className="w-[320px] h-full flex flex-col bg-sidebar border-r border-sidebar-border">
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
                    cancelStream(); // Cancel any in-flight SSE stream first
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

      {/* Tab Navigation */}
      <div className="flex border-b border-sidebar-border">
        <button
          onClick={() => setSidebarTab('chat')}
          className={`
            flex-1 py-2 text-sm font-medium transition-colors flex items-center justify-center gap-1.5
            ${sidebarTab === 'chat'
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
            ${sidebarTab === 'history'
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
        <>
          {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="text-center py-8">
            <div className="text-primary text-3xl mb-2">///</div>
            <p className="text-muted-foreground text-sm">
              Send a message to start a conversation with the swarm
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`
                ${msg.role === 'user' ? 'ml-4' : 'mr-4'}
              `}
            >
              {/* Role label */}
              <div
                className={`
                  text-[10px] font-medium uppercase tracking-wider mb-1
                  ${msg.role === 'user' ? 'text-gold text-right' : ''}
                  ${msg.role === 'assistant' ? 'text-primary' : ''}
                  ${msg.role === 'system' ? 'text-destructive' : ''}
                `}
              >
                {msg.role}
              </div>

              {/* Message content */}
              <div
                className={`
                  p-3 rounded text-sm font-mono leading-relaxed
                  ${msg.role === 'user'
                    ? 'bg-gold/10 border border-gold/20 text-foreground'
                    : ''
                  }
                  ${msg.role === 'assistant'
                    ? 'bg-card border border-border text-foreground'
                    : ''
                  }
                  ${msg.role === 'system'
                    ? 'bg-destructive/10 border border-destructive/20 text-destructive'
                    : ''
                  }
                `}
              >
                <pre className="whitespace-pre-wrap break-words">{msg.content}</pre>
              </div>

              {/* Timestamp */}
              <div className="text-[10px] text-muted-foreground mt-1 font-mono">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </div>
            </div>
          ))
        )}

        {/* Processing indicator */}
        {isProcessing && (
          <div className="flex items-center gap-2 text-primary text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>Processing...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input - Regular mode */}
      {!isEvalMode && (
        <form onSubmit={handleSubmit} className="p-4 border-t border-sidebar-border">
          <div className="relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Send a message..."
              disabled={isProcessing}
              rows={1}
              className="
                w-full px-4 py-3 pr-12
                bg-card border border-border
                rounded text-sm text-foreground font-mono
                placeholder:text-muted-foreground
                focus:outline-none focus:border-primary
                disabled:opacity-50
                resize-none
                transition-colors
              "
            />

            <button
              type={isProcessing ? 'button' : 'submit'}
              onClick={isProcessing ? cancelStream : undefined}
              className="
                absolute right-2 top-1/2 -translate-y-1/2
                w-8 h-8 rounded
                flex items-center justify-center
                bg-primary text-primary-foreground
                hover:bg-copper-light
                disabled:opacity-50
                transition-colors
              "
              disabled={!input.trim() && !isProcessing}
            >
              {isProcessing ? (
                <Square className="w-4 h-4" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>

          <div className="mt-2 text-[10px] text-muted-foreground">
            Press <kbd className="px-1 py-0.5 bg-secondary rounded text-primary">Enter</kbd> to send,{' '}
            <kbd className="px-1 py-0.5 bg-secondary rounded text-primary">Shift+Enter</kbd> for new line
          </div>
        </form>
      )}

      {/* Input - Eval mode */}
      {isEvalMode && (
        <div className="p-4 border-t border-sidebar-border">
          {/* Eval config summary */}
          <div className="mb-3 p-3 bg-card/50 border border-border rounded text-xs font-mono">
            <div className="flex items-center gap-2 mb-2 text-muted-foreground">
              <Settings className="w-3 h-3" />
              <span className="uppercase tracking-wider">Evaluation Config</span>
            </div>
            <div className="space-y-1 text-foreground">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Set:</span>
                <span className="text-primary">{evalConfig.evalSet}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Question:</span>
                <span className="text-primary">#{evalConfig.qIdx}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Model:</span>
                <span className="text-primary truncate max-w-[150px]" title={evalConfig.modelId}>
                  {evalConfig.modelId.split('/').pop()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Reflection:</span>
                <span className={evalConfig.runReflection ? 'text-primary' : 'text-muted-foreground'}>
                  {evalConfig.runReflection ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            </div>
          </div>

          {/* Run evaluation button */}
          <button
            onClick={isProcessing ? cancelStream : () => sendMessage('')}
            disabled={connectionStatus !== 'connected'}
            className={`
              w-full py-3 rounded
              flex items-center justify-center gap-2
              font-medium text-sm
              transition-all
              ${isProcessing
                ? 'bg-destructive/20 border border-destructive/40 text-destructive hover:bg-destructive/30'
                : 'bg-primary text-primary-foreground hover:bg-copper-light'
              }
              disabled:opacity-50 disabled:cursor-not-allowed
            `}
          >
            {isProcessing ? (
              <>
                <Square className="w-4 h-4" />
                <span>ABORT EVALUATION</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                <span>RUN EVALUATION</span>
              </>
            )}
          </button>

          <div className="mt-2 text-[10px] text-muted-foreground text-center">
            Runs the configured question through the swarm with judging
            {evalConfig.runReflection && ' and reflection'}
          </div>
        </div>
      )}
        </>
      )}
    </div>
    </TooltipProvider>
  );
}
