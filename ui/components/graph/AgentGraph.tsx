'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  ConnectionMode,
  MarkerType,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { AgentNode } from './AgentNode';
import { useAppStore } from '@/lib/store';
import type { Agent, AgentNodeData } from '@/types/mail';

// Virtual agents for eval mode
const VIRTUAL_AGENTS: Agent[] = [
  {
    name: 'Judge',
    comm_targets: [],
    enable_entrypoint: false,
    can_complete_tasks: false,
    enable_interswarm: false,
    isVirtual: true,
  },
  {
    name: 'Reflector',
    comm_targets: [],
    enable_entrypoint: false,
    can_complete_tasks: false,
    enable_interswarm: false,
    isVirtual: true,
  },
];

const nodeTypes = {
  agent: AgentNode,
};

// Force-directed layout helper
function calculateLayout(
  agents: { name: string; comm_targets: string[] }[],
  width: number,
  height: number
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const nodeCount = agents.length;

  if (nodeCount === 0) return positions;

  // Simple circular layout as starting point
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.5;

  agents.forEach((agent, i) => {
    const angle = (2 * Math.PI * i) / nodeCount - Math.PI / 2;
    positions.set(agent.name, {
      x: centerX + radius * Math.cos(angle) - 70,
      y: centerY + radius * Math.sin(angle) - 40,
    });
  });

  // Apply simple force simulation for better distribution
  const iterations = 50;
  const repulsion = 20000;
  const attraction = 0.01;

  for (let iter = 0; iter < iterations; iter++) {
    const forces = new Map<string, { fx: number; fy: number }>();

    // Initialize forces
    agents.forEach((a) => forces.set(a.name, { fx: 0, fy: 0 }));

    // Repulsion between all nodes
    for (let i = 0; i < agents.length; i++) {
      for (let j = i + 1; j < agents.length; j++) {
        const posI = positions.get(agents[i].name)!;
        const posJ = positions.get(agents[j].name)!;

        const dx = posJ.x - posI.x;
        const dy = posJ.y - posI.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);

        const force = repulsion / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        const forceI = forces.get(agents[i].name)!;
        const forceJ = forces.get(agents[j].name)!;

        forceI.fx -= fx;
        forceI.fy -= fy;
        forceJ.fx += fx;
        forceJ.fy += fy;
      }
    }

    // Attraction along edges
    agents.forEach((agent) => {
      const pos = positions.get(agent.name)!;
      agent.comm_targets.forEach((target) => {
        const targetPos = positions.get(target);
        if (targetPos) {
          const dx = targetPos.x - pos.x;
          const dy = targetPos.y - pos.y;

          const force = forces.get(agent.name)!;
          force.fx += dx * attraction;
          force.fy += dy * attraction;
        }
      });
    });

    // Center gravity
    agents.forEach((agent) => {
      const pos = positions.get(agent.name)!;
      const force = forces.get(agent.name)!;
      force.fx += (centerX - pos.x) * 0.001;
      force.fy += (centerY - pos.y) * 0.001;
    });

    // Apply forces with damping
    const damping = 0.9 - iter * 0.01;
    agents.forEach((agent) => {
      const pos = positions.get(agent.name)!;
      const force = forces.get(agent.name)!;

      pos.x += force.fx * damping;
      pos.y += force.fy * damping;

      // Keep within bounds
      pos.x = Math.max(50, Math.min(width - 200, pos.x));
      pos.y = Math.max(50, Math.min(height - 100, pos.y));
    });
  }

  return positions;
}

export function AgentGraph() {
  const {
    agents,
    entrypoint,
    selectedAgent,
    setSelectedAgent,
    events,
    agentLastViewed,
    isEvalMode,
  } = useAppStore();

  // Combine real agents with virtual agents when in eval mode
  const allAgents = useMemo(() => {
    if (isEvalMode) {
      return [...agents, ...VIRTUAL_AGENTS];
    }
    return agents;
  }, [agents, isEvalMode]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const nodePositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());

  // Calculate event counts per agent (includes both caller and recipient events)
  const eventCounts = useMemo(() => {
    const counts = new Map<string, number>();
    events.forEach((event) => {
      // Count events where agent is the caller
      const caller = event.extra_data?.caller;
      if (caller && typeof caller === 'string') {
        counts.set(caller, (counts.get(caller) || 0) + 1);
      }

      // Also count events where agent is a recipient (for messages)
      if (event.event === 'new_message' && event.extra_data?.full_message) {
        const msg = event.extra_data.full_message as {
          message?: {
            recipient?: { address?: string };
            recipients?: Array<{ address?: string }>;
          };
        };
        const recipient = msg.message?.recipient?.address;
        const recipients = msg.message?.recipients?.map(r => r.address) || [];

        if (recipient && recipient !== caller) {
          counts.set(recipient, (counts.get(recipient) || 0) + 1);
        }
        recipients.forEach(r => {
          if (r && r !== caller) {
            counts.set(r, (counts.get(r) || 0) + 1);
          }
        });
      }
    });
    return counts;
  }, [events]);

  // Calculate which agents have unseen activity
  const agentsWithUnseenActivity = useMemo(() => {
    const unseen = new Set<string>();

    events.forEach((event) => {
      const eventTime = new Date(event.timestamp).getTime();

      // Check if caller has unseen activity
      const caller = event.extra_data?.caller as string | undefined;
      if (caller) {
        const lastViewed = agentLastViewed[caller] || 0;
        if (eventTime > lastViewed) {
          unseen.add(caller);
        }
      }

      // Check if recipient has unseen activity (for messages)
      if (event.event === 'new_message' && event.extra_data?.full_message) {
        const msg = event.extra_data.full_message as {
          message?: {
            recipient?: { address?: string };
            recipients?: Array<{ address?: string }>;
          };
        };
        const recipient = msg.message?.recipient?.address;
        const recipients = msg.message?.recipients?.map(r => r.address) || [];

        if (recipient) {
          const lastViewed = agentLastViewed[recipient] || 0;
          if (eventTime > lastViewed) {
            unseen.add(recipient);
          }
        }
        recipients.forEach(r => {
          if (r) {
            const lastViewed = agentLastViewed[r] || 0;
            if (eventTime > lastViewed) {
              unseen.add(r);
            }
          }
        });
      }
    });

    return unseen;
  }, [events, agentLastViewed]);

  // Create nodes and edges from agents
  useEffect(() => {
    if (agents.length === 0) return;

    // Calculate positions for real agents only
    const realAgents = agents.filter(a => !a.isVirtual);
    const positions = calculateLayout(realAgents, 1000, 750);

    // Position virtual agents at the bottom
    if (isEvalMode) {
      const virtualAgentSpacing = 200;
      const bottomY = 550; // Below the main graph
      const centerX = 400;

      VIRTUAL_AGENTS.forEach((agent, i) => {
        const x = centerX + (i - (VIRTUAL_AGENTS.length - 1) / 2) * virtualAgentSpacing - 70;
        positions.set(agent.name, { x, y: bottomY });
      });
    }

    // Create nodes
    const prevPositions = nodePositionsRef.current;
    const resolvedPositions = new Map<string, { x: number; y: number }>();

    const newNodes: Node[] = allAgents.map((agent) => {
      const pos = prevPositions.get(agent.name) || positions.get(agent.name) || { x: 0, y: 0 };
      resolvedPositions.set(agent.name, pos);
      const virtualType = agent.name === 'Judge' ? 'judge' : agent.name === 'Reflector' ? 'reflector' : undefined;

      const nodeData: AgentNodeData = {
        name: agent.name,
        isEntrypoint: agent.enable_entrypoint || agent.name === entrypoint,
        canComplete: agent.can_complete_tasks,
        isInterswarm: agent.enable_interswarm,
        isActive: agentsWithUnseenActivity.has(agent.name),
        eventCount: eventCounts.get(agent.name) || 0,
        isVirtual: agent.isVirtual,
        virtualType,
        isEvalMode,
      };

      return {
        id: agent.name,
        type: 'agent',
        position: pos,
        data: nodeData,
        selected: selectedAgent === agent.name,
      };
    });

    setNodes(newNodes);
    nodePositionsRef.current = resolvedPositions;

  }, [agents, allAgents, entrypoint, agentsWithUnseenActivity, selectedAgent, eventCounts, isEvalMode, setNodes, setEdges]);

  // Keep node positions in sync for edge routing + new node placement.
  useEffect(() => {
    if (nodes.length === 0) return;
    nodePositionsRef.current = new Map(nodes.map((node) => [node.id, node.position]));
  }, [nodes]);

  // Recompute edges when nodes move so anchors stay on the nearest side.
  useEffect(() => {
    if (agents.length === 0 || nodes.length === 0) {
      setEdges([]);
      return;
    }

    const positions = new Map(nodes.map((node) => [node.id, node.position]));
    const realAgents = agents.filter((agent) => !agent.isVirtual);
    const realAgentNames = new Set(realAgents.map((agent) => agent.name));
    const realAgentMap = new Map(realAgents.map((agent) => [agent.name, agent]));
    const seenPairs = new Set<string>();
    const positionKey = (pos: Position) => {
      switch (pos) {
        case Position.Left:
          return 'left';
        case Position.Right:
          return 'right';
        case Position.Top:
          return 'top';
        case Position.Bottom:
          return 'bottom';
        default:
          return 'left';
      }
    };

    const newEdges: Edge[] = [];
    realAgents.forEach((agent) => {
      agent.comm_targets.forEach((target) => {
        if (!realAgentNames.has(target)) return;

        const pairKey = agent.name < target ? `${agent.name}::${target}` : `${target}::${agent.name}`;
        if (seenPairs.has(pairKey)) return;
        seenPairs.add(pairKey);

        const targetAgent = realAgentMap.get(target);
        const isBidirectional = Boolean(targetAgent?.comm_targets.includes(agent.name));
        const isActive =
          agentsWithUnseenActivity.has(agent.name) || agentsWithUnseenActivity.has(target);
        const sourcePos = positions.get(agent.name);
        const targetPos = positions.get(target);
        if (!sourcePos || !targetPos) return;

        const dx = targetPos.x - sourcePos.x;
        const dy = targetPos.y - sourcePos.y;
        let sourcePosition = Position.Right;
        let targetPosition = Position.Left;

        if (Math.abs(dx) >= Math.abs(dy)) {
          sourcePosition = dx >= 0 ? Position.Right : Position.Left;
          targetPosition = dx >= 0 ? Position.Left : Position.Right;
        } else {
          sourcePosition = dy >= 0 ? Position.Bottom : Position.Top;
          targetPosition = dy >= 0 ? Position.Top : Position.Bottom;
        }

        const edge: Edge = {
          id: pairKey,
          source: agent.name,
          target: target,
          type: 'default',
          sourceHandle: `source-${positionKey(sourcePosition)}`,
          targetHandle: `target-${positionKey(targetPosition)}`,
          animated: isActive,
          style: {
            stroke: isActive ? 'var(--edge-active)' : 'var(--edge-inactive)',
            strokeWidth: isActive ? 2 : 1,
          },
        };

        if (!isBidirectional) {
          edge.markerEnd = {
            type: MarkerType.ArrowClosed,
            color: isActive ? 'var(--edge-active)' : 'var(--edge-inactive)',
            width: 15,
            height: 15,
          };
        }

        newEdges.push(edge);
      });
    });

    setEdges(newEdges);
  }, [agents, nodes, agentsWithUnseenActivity, setEdges]);

  // Handle node click
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedAgent(node.id === selectedAgent ? null : node.id);
    },
    [selectedAgent, setSelectedAgent]
  );

  // Handle pane click to deselect
  const onPaneClick = useCallback(() => {
    setSelectedAgent(null);
  }, [setSelectedAgent]);

  return (
    <div className="w-full h-full grid-pattern">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        connectionMode={ConnectionMode.Loose}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={2}
        deleteKeyCode={null}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          color="var(--grid-color)"
          gap={20}
          size={1}
        />
        <Controls
          showInteractive={false}
          className="!shadow-none"
        />
      </ReactFlow>

      {/* Empty state */}
      {agents.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <div className="text-primary text-5xl mb-4 font-sans font-bold tracking-tight">
              MAIL
            </div>
            <div className="text-muted-foreground text-sm font-mono">
              Connect to a swarm to view agents
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
