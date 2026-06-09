'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { AnimatePresence, motion } from 'motion/react';
import { useAppStore, type EvalConfig } from '@/lib/store';
import { getClient } from '@/lib/api';
import { CollapsibleChatSidebar } from '@/components/chat/CollapsibleChatSidebar';
import { ChatContent } from './chat/ChatContent';
import { AgentGraph } from '@/components/graph/AgentGraph';
import { AgentDetailPanel } from '@/components/panels/AgentDetailPanel';
import { EventsPanel } from '@/components/panels/EventsPanel';
import { EvalModeHeader } from '@/components/ui/EvalModeHeader';
import { BreachSequence } from '@/components/effects/BreachSequence';
import { MatrixRain } from '@/components/effects/MatrixRain';
import { ScreenFlicker } from '@/components/effects/ScreenFlicker';
import { useKonamiCode } from '@/hooks/useKonamiCode';
import { Loader2, AlertCircle, RefreshCw, Settings, ChevronDown, ChevronRight } from 'lucide-react';

function ConnectionOverlay() {
  const {
    serverUrl,
    setServerUrl,
    connectionStatus,
    setConnectionStatus,
    setAgents,
    isEvalMode,
    setEvalMode,
    evalConfig,
    setEvalConfig,
  } = useAppStore();

  const [inputUrl, setInputUrl] = useState(serverUrl);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showEvalConfig, setShowEvalConfig] = useState(false);

  // Local eval config state for editing
  const [localEvalConfig, setLocalEvalConfig] = useState<EvalConfig>(evalConfig);

  const handleConnect = async () => {
    setIsConnecting(true);
    setError(null);
    setConnectionStatus('connecting');

    try {
      const client = getClient(inputUrl);

      // If eval mode, send config first
      if (isEvalMode) {
        await client.postEvalConfig(localEvalConfig);
        setEvalConfig(localEvalConfig);
      }

      // Try to get server info first
      const info = await client.getServerInfo();

      // Then get agents
      const agentsData = await client.getAgents();

      setServerUrl(inputUrl);
      setAgents(agentsData.agents, agentsData.entrypoint);
      setConnectionStatus('connected');
    } catch (err) {
      setError((err as Error).message);
      setConnectionStatus('error');
    } finally {
      setIsConnecting(false);
    }
  };

  if (connectionStatus === 'connected') return null;

  return (
    <div className="absolute inset-0 bg-background/95 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="bg-card border border-border rounded-lg p-8 max-w-lg w-full mx-4 metallic-border">
        <div className="text-center mb-6">
          <h1 className="font-sans font-bold text-3xl text-metallic mb-2">
            MAIL
          </h1>
          <p className="text-muted-foreground text-sm">
            Multi-Agent Interface Layer
          </p>
        </div>

        <div className="space-y-4">
          {/* Server URL */}
          <div>
            <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-2">
              Server URL
            </label>
            <input
              type="text"
              value={inputUrl}
              onChange={(e) => setInputUrl(e.target.value)}
              placeholder="http://localhost:8000"
              className="
                w-full px-4 py-3
                bg-background border border-border
                rounded text-sm text-foreground font-mono
                placeholder:text-muted-foreground
                focus:outline-none focus:border-primary
                transition-colors
              "
            />
          </div>

          {/* Mode Toggle */}
          <div>
            <label className="block text-xs text-muted-foreground uppercase tracking-wider mb-2">
              Mode
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => setEvalMode(false)}
                className={`
                  flex-1 py-2 px-4 rounded text-sm font-medium
                  border transition-colors
                  ${!isEvalMode
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-background text-muted-foreground border-border hover:border-primary/50'
                  }
                `}
              >
                Normal
              </button>
              <button
                onClick={() => {
                  setEvalMode(true);
                  setShowEvalConfig(true);
                }}
                className={`
                  flex-1 py-2 px-4 rounded text-sm font-medium
                  border transition-colors
                  ${isEvalMode
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-background text-muted-foreground border-border hover:border-primary/50'
                  }
                `}
              >
                Eval Mode
              </button>
            </div>
          </div>

          {/* Eval Config Section */}
          {isEvalMode && (
            <div className="border border-border rounded-lg overflow-hidden">
              <button
                onClick={() => setShowEvalConfig(!showEvalConfig)}
                className="w-full flex items-center justify-between px-4 py-2 bg-background/50 hover:bg-background/80 transition-colors"
              >
                <span className="text-xs text-muted-foreground uppercase tracking-wider">
                  Evaluation Config
                </span>
                {showEvalConfig ? (
                  <ChevronDown className="w-4 h-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-muted-foreground" />
                )}
              </button>

              {showEvalConfig && (
                <div className="p-4 space-y-3 bg-background/30">
                  {/* Eval Set */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                        Eval Set
                      </label>
                      <input
                        type="text"
                        value={localEvalConfig.evalSet}
                        onChange={(e) =>
                          setLocalEvalConfig({ ...localEvalConfig, evalSet: e.target.value })
                        }
                        className="
                          w-full px-3 py-2
                          bg-background border border-border
                          rounded text-xs text-foreground font-mono
                          focus:outline-none focus:border-primary
                        "
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                        Question #
                      </label>
                      <input
                        type="number"
                        value={localEvalConfig.qIdx}
                        onChange={(e) =>
                          setLocalEvalConfig({ ...localEvalConfig, qIdx: parseInt(e.target.value) || 0 })
                        }
                        min={0}
                        className="
                          w-full px-3 py-2
                          bg-background border border-border
                          rounded text-xs text-foreground font-mono
                          focus:outline-none focus:border-primary
                        "
                      />
                    </div>
                  </div>

                  {/* Model ID */}
                  <div>
                    <label className="block text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                      Model ID
                    </label>
                    <input
                      type="text"
                      value={localEvalConfig.modelId}
                      onChange={(e) =>
                        setLocalEvalConfig({ ...localEvalConfig, modelId: e.target.value })
                      }
                      className="
                        w-full px-3 py-2
                        bg-background border border-border
                        rounded text-xs text-foreground font-mono
                        focus:outline-none focus:border-primary
                      "
                    />
                  </div>

                  {/* Reflector Model */}
                  <div>
                    <label className="block text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                      Reflector Model
                    </label>
                    <input
                      type="text"
                      value={localEvalConfig.reflectorModel}
                      onChange={(e) =>
                        setLocalEvalConfig({ ...localEvalConfig, reflectorModel: e.target.value })
                      }
                      className="
                        w-full px-3 py-2
                        bg-background border border-border
                        rounded text-xs text-foreground font-mono
                        focus:outline-none focus:border-primary
                      "
                    />
                  </div>

                  {/* Pass Threshold + Run Reflection */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                        Pass Threshold
                      </label>
                      <input
                        type="number"
                        value={localEvalConfig.passThreshold}
                        onChange={(e) =>
                          setLocalEvalConfig({
                            ...localEvalConfig,
                            passThreshold: parseFloat(e.target.value) || 0.75,
                          })
                        }
                        min={0}
                        max={1}
                        step={0.05}
                        className="
                          w-full px-3 py-2
                          bg-background border border-border
                          rounded text-xs text-foreground font-mono
                          focus:outline-none focus:border-primary
                        "
                      />
                    </div>
                    <div className="flex items-end">
                      <label className="flex items-center gap-2 cursor-pointer py-2">
                        <input
                          type="checkbox"
                          checked={localEvalConfig.runReflection}
                          onChange={(e) =>
                            setLocalEvalConfig({
                              ...localEvalConfig,
                              runReflection: e.target.checked,
                            })
                          }
                          className="w-4 h-4 rounded border-border bg-background text-primary focus:ring-primary"
                        />
                        <span className="text-xs text-foreground">Run Reflection</span>
                      </label>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 text-destructive text-sm bg-destructive/10 border border-destructive/20 rounded p-3">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <button
            onClick={handleConnect}
            disabled={isConnecting || !inputUrl.trim()}
            className="
              w-full py-3 rounded
              bg-primary text-primary-foreground font-medium
              hover:bg-copper-light
              disabled:opacity-50 disabled:cursor-not-allowed
              flex items-center justify-center gap-2
              transition-colors
            "
          >
            {isConnecting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Connecting...
              </>
            ) : (
              'Connect to Swarm'
            )}
          </button>
        </div>

        <div className="mt-6 pt-6 border-t border-border">
          <p className="text-xs text-muted-foreground text-center">
            {isEvalMode
              ? 'Connect to an evaluation server to run and visualize eval runs'
              : 'Connect to a running MAIL server to visualize the agent swarm'
            }
          </p>
        </div>
      </div>
    </div>
  );
}

function SettingsButton() {
  const { setConnectionStatus, setAgents } = useAppStore();

  const handleDisconnect = () => {
    setAgents([], '');
    setConnectionStatus('disconnected');
  };

  return (
    <div className="absolute top-4 right-4 z-20 flex items-center gap-2">
      <button
        onClick={handleDisconnect}
        className="
          p-2 rounded
          bg-card border border-border
          text-muted-foreground hover:text-foreground hover:border-primary
          transition-colors
        "
        title="Disconnect"
      >
        <RefreshCw className="w-4 h-4" />
      </button>
      <button
        className="
          p-2 rounded
          bg-card border border-border
          text-muted-foreground hover:text-foreground hover:border-primary
          transition-colors
        "
        title="Settings"
      >
        <Settings className="w-4 h-4" />
      </button>
    </div>
  );
}

export default function Home() {
  const { connectionStatus, isEvalMode, isChatExpanded, setChatExpanded } = useAppStore();
  const [mounted, setMounted] = useState(false);
  const [showBreachSequence, setShowBreachSequence] = useState(false);
  const [breachComplete, setBreachComplete] = useState(false);
  const [connectionStartTime, setConnectionStartTime] = useState<number | null>(null);
  const { activated: superBreachMode } = useKonamiCode();

  // Prevent hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

  // Track when we connect in eval mode to start the breach sequence
  useEffect(() => {
    if (connectionStatus === 'connected' && isEvalMode && !breachComplete) {
      setShowBreachSequence(true);
      setConnectionStartTime(Date.now());
    } else if (connectionStatus !== 'connected') {
      setBreachComplete(false);
      setShowBreachSequence(false);
      setConnectionStartTime(null);
    }
  }, [connectionStatus, isEvalMode, breachComplete]);

  const handleBreachComplete = useCallback(() => {
    setShowBreachSequence(false);
    setBreachComplete(true);
  }, []);

  if (!mounted) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    );
  }

  // Determine if we should apply eval-mode styling
  const isInEvalMode = isEvalMode && connectionStatus === 'connected' && breachComplete;

  // Build class names
  const mainClasses = [
    'h-screen w-screen flex flex-col overflow-hidden',
    isInEvalMode ? 'eval-mode' : '',
    superBreachMode && isInEvalMode ? 'super-breach-mode' : '',
  ].filter(Boolean).join(' ');

  return (
    <main className={mainClasses}>
      {/* BREACH SEQUENCE - The dramatic intro */}
      {showBreachSequence && (
        <BreachSequence onComplete={handleBreachComplete} />
      )}

      {/* EVAL MODE HEADER - The living status bar */}
      {isInEvalMode && connectionStartTime && (
        <EvalModeHeader connectionStartTime={connectionStartTime} superBreachMode={superBreachMode} />
      )}

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* MATRIX RAIN - Subtle background effect */}
        {isInEvalMode && (
          <MatrixRain />
        )}

        {/* SCREEN FLICKER - Event-triggered effects */}
        <ScreenFlicker />

        {/* Collapsible Chat Sidebar */}
        <CollapsibleChatSidebar />

        {/* Main Content Area - Crossfade between graph and chat */}
        <div className="flex-1 relative">
          <AnimatePresence mode="wait">
            {isChatExpanded ? (
              <motion.div
                key="chat"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="absolute inset-0"
              >
                <ChatContent onCollapse={() => setChatExpanded(false)} />
              </motion.div>
            ) : (
              <motion.div
                key="graph"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="absolute inset-0"
              >
                <ReactFlowProvider>
                  <AgentGraph />
                </ReactFlowProvider>

                {/* Settings button */}
                {connectionStatus === 'connected' && <SettingsButton />}

                {/* Agent Detail Panel */}
                <AgentDetailPanel />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Events Panel - hidden in expanded chat mode */}
        {!isChatExpanded && <EventsPanel />}
      </div>

      {/* Connection Overlay */}
      <ConnectionOverlay />
    </main>
  );
}
