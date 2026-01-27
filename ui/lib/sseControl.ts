'use client';

import { useAppStore } from '@/lib/store';

let activeController: AbortController | null = null;

export function startActiveStream(): AbortController {
  if (activeController) {
    activeController.abort();
  }
  const controller = new AbortController();
  activeController = controller;
  return controller;
}

export function cancelActiveStream(): void {
  if (activeController) {
    activeController.abort();
    activeController = null;
  }
  useAppStore.getState().setIsProcessing(false);
}

export function isActiveController(controller: AbortController): boolean {
  return activeController === controller;
}
