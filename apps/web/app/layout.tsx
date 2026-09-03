import type { Metadata } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import type { ReactNode } from 'react'

import { AuthProvider } from '@/components/auth-provider'
import { QueryProvider } from '@/components/query-provider'
import { Shell } from '@/components/shell'
import { ToastProvider } from '@/components/ui/toast'
import { TooltipProvider } from '@/components/ui/tooltip'
import { fetchMeta } from '@/lib/api'
// Imported for its side effect: installs the server-side token getter that
// `lib/auth.ts` reads. This layout wraps every route, so it loads before any
// page renders. See lib/auth.ts for why the server SDK cannot be imported there.
import '@/lib/auth-server'

import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: {
    default: 'Codon Lab — protein engineering copilot',
    template: '%s — Codon Lab',
  },
  description:
    'Turn a plain-language protein engineering goal into a ranked list of specific '
    + 'mutations, where every number traces to the model, version and weights hash '
    + 'that produced it.',
  applicationName: 'Codon Lab',
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  // If the API is unreachable the page below renders its own error state, which
  // explains the failure properly. Suppressing the banner here avoids claiming
  // anything about provider state we could not actually read.
  const demoMode = await fetchMeta()
    .then((meta) => meta.demo_mode)
    .catch(() => false)

  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body>
        <AuthProvider>
          <QueryProvider>
            <TooltipProvider delayDuration={300}>
              <ToastProvider>
                <Shell demoMode={demoMode}>{children}</Shell>
              </ToastProvider>
            </TooltipProvider>
          </QueryProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
