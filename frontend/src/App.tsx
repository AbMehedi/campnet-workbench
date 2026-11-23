import { useEffect, useState } from 'react'

type Health = { status: string; checks?: Record<string, string> }

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/v1/health/ready')
      .then((r) => r.json() as Promise<Health>)
      .then(setHealth)
      .catch(() => setError('API unreachable'))
  }, [])

  return (
    <main>
      <h1>CampNet Data Workbench</h1>
      <p>Development scaffold. Features land per the milestone roadmap.</p>
      <section aria-live="polite">
        <h2>Backend status</h2>
        {error && <p>{error}</p>}
        {!error && !health && <p>Checking…</p>}
        {health && (
          <ul>
            <li>overall: {health.status}</li>
            {Object.entries(health.checks ?? {}).map(([name, s]) => (
              <li key={name}>
                {name}: {s}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
