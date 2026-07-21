export function WorkspaceShell({ inspectorOpen, children }: { inspectorOpen: boolean; children: React.ReactNode }) {
  return <div className={`workspace ${inspectorOpen ? "" : "inspector-closed"}`}>{children}</div>;
}

export function SessionSidebar({ children }: { children: React.ReactNode }) {
  return <aside className="panel session-panel">{children}</aside>;
}

export function WorkspaceHeader({ children }: { children: React.ReactNode }) {
  return <header className="panel-header">{children}</header>;
}
