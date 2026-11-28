import type { Metadata } from 'next';
import './globals.css';
import './marketing.css';
export const metadata: Metadata = { title: 'Vaeltrixis | Runtime control for autonomous agents', description: 'Contain runaway agents, rehearse loop policies, and recover with a self-hosted Flagsmith control plane.' };
export default function Layout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
