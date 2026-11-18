import { defineConfig, mergeConfig } from 'vitest/config'

import viteConfig from './vite.config'

// Unit and component tests (npm test). Reuses the app's Vite config (aliases, plugins).
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
      unstubGlobals: true,
    },
  }),
)
