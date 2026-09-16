import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { StatusPage } from '@/features/status/status-panel';
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Metiquo', error, info.componentStack);
  }
  render() {
    return this.state.failed ? (
      <StatusPage error={new Error('Rendering failed')} onRetry={() => window.location.reload()} />
    ) : (
      this.props.children
    );
  }
}
