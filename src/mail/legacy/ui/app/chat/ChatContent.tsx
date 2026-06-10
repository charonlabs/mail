'use client';

import { useState, useEffect } from 'react';
import { useAppStore } from '@/lib/store';
import { useSSE } from '@/hooks/useSSE';
import { useChatTimeline } from '@/hooks/useChatTimeline';
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation';
import {
  Message,
  MessageContent,
  MessageResponse,
  MessageActions,
  MessageAction,
} from '@/components/ai-elements/message';
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputSubmit,
  type PromptInputMessage,
} from '@/components/ai-elements/prompt-input';
import { Loader } from '@/components/ai-elements/loader';
import { Button } from '@/components/ui/button';
import { CopyIcon, Terminal, Square, PanelLeftClose } from 'lucide-react';
import { ChatToolCall } from './ChatToolCall';
import { ChatErrorCard } from './ChatErrorCard';
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from '@/components/ai-elements/reasoning';

interface ChatContentProps {
  onCollapse?: () => void;
  className?: string;
}

export function ChatContent({ onCollapse, className }: ChatContentProps) {
  const [input, setInput] = useState('');

  const {
    isProcessing,
    connectionStatus,
    setConnectionStatus,
  } = useAppStore();

  const { sendMessage, cancelStream } = useSSE();
  const timeline = useChatTimeline();

  // Auto-connect on mount if not connected
  useEffect(() => {
    if (connectionStatus === 'disconnected') {
      setConnectionStatus('connected');
    }
  }, [connectionStatus, setConnectionStatus]);

  const handleSubmit = async (message: PromptInputMessage) => {
    if (!message.text?.trim()) return;

    await sendMessage(message.text);
    setInput('');
  };

  const handleCopy = (content: string) => {
    navigator.clipboard.writeText(content);
  };

  // Map our ChatMessage role to what Message component expects
  const mapRole = (role: 'user' | 'assistant' | 'system'): 'user' | 'assistant' => {
    return role === 'user' ? 'user' : 'assistant';
  };

  return (
    <div className={`flex flex-col h-full bg-background ${className ?? ''}`}>
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-card border border-border flex items-center justify-center">
            <Terminal className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h1 className="font-sans font-bold text-foreground tracking-tight">
              MAIL Chat
            </h1>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <div className={`w-2 h-2 rounded-full ${
                connectionStatus === 'connected' ? 'bg-green-500' :
                connectionStatus === 'connecting' ? 'bg-gold animate-pulse' :
                connectionStatus === 'error' ? 'bg-destructive' :
                'bg-muted-foreground'
              }`} />
              <span className="capitalize">{connectionStatus}</span>
            </div>
          </div>
        </div>
        {onCollapse && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onCollapse}
            className="text-muted-foreground hover:text-foreground"
          >
            <PanelLeftClose className="w-5 h-5" />
          </Button>
        )}
      </header>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full overflow-hidden">
        <Conversation className="flex-1">
          <ConversationContent className="px-4 py-6">
            {timeline.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center py-12">
                <div className="text-primary text-4xl mb-4 font-mono">///</div>
                <h2 className="text-lg font-semibold text-foreground mb-2">
                  Start a conversation
                </h2>
                <p className="text-muted-foreground text-sm max-w-md">
                  Send a message to interact with the MAIL swarm. Your messages will be routed to the configured entrypoint agent.
                </p>
              </div>
            ) : (
              timeline.map((item) => {
                if (item.type === 'message') {
                  const { message: msg, reasoning } = item.data;
                  return (
                    <div key={msg.id}>
                      {/* Show reasoning above assistant messages */}
                      {reasoning && msg.role === 'assistant' && (
                        <Reasoning
                          isStreaming={false}
                          defaultOpen={false}
                          className="mb-2"
                        >
                          <ReasoningTrigger />
                          <ReasoningContent>{reasoning}</ReasoningContent>
                        </Reasoning>
                      )}
                      <Message from={mapRole(msg.role)}>
                        <MessageContent>
                          {msg.role === 'system' ? (
                            <div className="text-destructive bg-destructive/10 border border-destructive/20 rounded px-3 py-2">
                              {msg.content}
                            </div>
                          ) : (
                            <MessageResponse>{msg.content}</MessageResponse>
                          )}
                        </MessageContent>
                        {msg.role === 'assistant' && (
                          <MessageActions>
                            <MessageAction
                              onClick={() => handleCopy(msg.content)}
                              tooltip="Copy"
                            >
                              <CopyIcon className="size-3" />
                            </MessageAction>
                          </MessageActions>
                        )}
                      </Message>
                    </div>
                  );
                }
                if (item.type === 'tool_call') {
                  // Check if this is the last tool call and we're still processing
                  const toolCallItems = timeline.filter((t) => t.type === 'tool_call');
                  const isLastToolCall = item === toolCallItems[toolCallItems.length - 1];
                  const isRunning = isProcessing && isLastToolCall && !item.data.hasResult;
                  return (
                    <ChatToolCall
                      key={item.data.event.id}
                      toolCall={item.data}
                      isRunning={isRunning}
                    />
                  );
                }
                if (item.type === 'error') {
                  return (
                    <ChatErrorCard
                      key={item.data.id}
                      event={item.data}
                    />
                  );
                }
                return null;
              })
            )}

            {/* Loading indicator */}
            {isProcessing && (
              <div className="flex items-center gap-2 text-primary">
                <Loader />
                <span className="text-sm">Processing...</span>
              </div>
            )}
          </ConversationContent>
          <ConversationScrollButton />
        </Conversation>

        {/* Input Area */}
        <div className="p-4 border-t border-border">
          <PromptInput
            onSubmit={handleSubmit}
            className="bg-card border border-border rounded-lg"
          >
            <PromptInputTextarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Send a message..."
              className="bg-transparent border-none focus:ring-0"
            />
            <PromptInputFooter className="px-3 pb-3">
              <div /> {/* Spacer */}
              {isProcessing ? (
                <Button
                  type="button"
                  size="icon-sm"
                  variant="destructive"
                  onClick={cancelStream}
                >
                  <Square className="size-4" />
                </Button>
              ) : (
                <PromptInputSubmit
                  disabled={!input.trim()}
                  className="bg-primary text-primary-foreground hover:bg-copper-light"
                />
              )}
            </PromptInputFooter>
          </PromptInput>

          <div className="mt-2 text-[10px] text-muted-foreground text-center">
            Press <kbd className="px-1 py-0.5 bg-secondary rounded text-primary">Enter</kbd> to send,{' '}
            <kbd className="px-1 py-0.5 bg-secondary rounded text-primary">Shift+Enter</kbd> for new line
          </div>
        </div>
      </div>
    </div>
  );
}
