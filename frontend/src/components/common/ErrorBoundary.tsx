import { Component, type ErrorInfo, type ReactNode } from 'react'
export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* Never log QR tokens or account payloads. */ }
  render() {
    if (this.state.failed) return <main className="fg-app"><div className="fg-main fg-empty"><h1>Something went wrong</h1><p>We couldn’t display this page. Please reload and try again.</p><button className="fg-button fg-button--primary" onClick={() => window.location.reload()}>Reload page</button></div></main>
    return this.props.children
  }
}