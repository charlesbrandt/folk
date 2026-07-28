import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Local dev without Docker (`npm run dev` from web/ui/, `uvicorn api:app
// --reload` from web/, per README.md) proxies straight to localhost:8500.
// docker-compose.yml overrides VITE_API_TARGET to the 'api' service's
// Docker-network hostname -- same /api proxy pattern as digger/transcript,
// just parameterized so it also works run standalone outside Compose.
const apiTarget = process.env.VITE_API_TARGET || 'http://localhost:8500'

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: '0.0.0.0',
    port: 5175,
    proxy: {
      '/api': {
        target: apiTarget,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
})
