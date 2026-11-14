import { Component } from 'react'
import { useLocation } from 'react-router-dom'
import { ErrorBox } from './ui.jsx'

// One page failing must not blank the whole app. Reset when the user navigates elsewhere.
class Boundary extends Component {
  constructor(p) { super(p); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  componentDidUpdate(prev) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }) }
  componentDidCatch(error, info) { console.error('Page error:', error, info?.componentStack) }
  render() {
    if (this.state.error) return <ErrorBox message={`This page could not be shown (${this.state.error.message}). Other pages still work.`} />
    return this.props.children
  }
}

export default function ErrorBoundary({ children }) {
  const loc = useLocation()
  return <Boundary resetKey={loc.pathname}>{children}</Boundary>
}
