import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'AgentBreaker | Runtime Control', description: 'Self-hosted agent circuit breaker powered by Flagsmith' };
export default function Layout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
