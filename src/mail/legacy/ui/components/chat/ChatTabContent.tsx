'use client';

import { useRef, useEffect } from 'react';
import { useAppStore } from '@/lib/store';
import {
  Conversation,
  ConversationContent,
} from '@/components/ai-elements/conversation';
import {
  Message,
  MessageContent,
  MessageResponse,
} from '@/components/ai-elements/message';
import { Loader } from '@/components/ai-elements/loader';
import { Button } from '@/components/ui/button';
import { MessageSquarePlus } from 'lucide-react';

/**
 * Compact chat view for the sidebar.
 * Shows only messages (no tool calls, reasoning, or error cards).
 * Smaller text and tighter spacing for the constrained sidebar width.
 */
export function ChatTabContent() {
  const { messages, isProcessing, toggleChatExpanded } = useAppStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Map role to Message component's expected type
  const mapRole = (role: 'user' | 'assistant' | 'system'): 'user' | 'assistant' => {
    return role === 'user' ? 'user' : 'assistant';
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <Conversation className="flex-1 overflow-hidden">
        <ConversationContent className="px-3 py-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-8">
              <div className="text-primary text-2xl mb-2 font-mono">///</div>
              <p className="text-muted-foreground text-xs px-4">
                Send a message to start a conversation with the swarm
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {messages.map((msg) => (
                <Message
                  key={msg.id}
                  from={mapRole(msg.role)}
                  className="text-sm"
                >
                  <MessageContent>
                    {msg.role === 'system' ? (
                      <div className="text-destructive bg-destructive/10 border border-destructive/20 rounded px-2 py-1 text-xs">
                        {msg.content}
                      </div>
                    ) : (
                      <MessageResponse className="text-sm leading-snug">
                        {msg.content}
                      </MessageResponse>
                    )}
                  </MessageContent>
                </Message>
              ))}

              {/* Processing indicator */}
              {isProcessing && (
                <div className="flex items-center gap-2 text-primary pl-2">
                  <Loader className="size-3" />
                  <span className="text-xs">Processing...</span>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </ConversationContent>
      </Conversation>

      {/* Expand to full chat button */}
      <div className="p-3 border-t border-sidebar-border">
        <Button
          onClick={toggleChatExpanded}
          variant="outline"
          className="w-full gap-2 text-sm"
        >
          <MessageSquarePlus className="w-4 h-4" />
          Open Full Chat
        </Button>
        <div className="mt-2 text-[10px] text-muted-foreground text-center">
          Expand to send messages and see full conversation
        </div>
      </div>
    </div>
  );
}
