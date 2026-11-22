import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Sous Windows, la lettre de lecteur peut arriver en minuscule (« c:\ », ex. terminal de VS Code) ou en majuscule selon le
// répertoire de lancement : Vite chargerait alors deux fois les mêmes modules (deux React → « Invalid hook call »).
// On fixe la racine et l'alias sur un chemin normalisé (lecteur en majuscule).
const ROOT = import.meta.dirname.replace(/^[a-z]:/, (d) => d.toUpperCase())

// En développement, /api est relayé vers l'API FastAPI (uvicorn backend.app.main:app --port 8000).
export default defineConfig({
  root: ROOT,
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(ROOT, './src') } },
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.SHOPINSIGHT_API ?? 'http://127.0.0.1:8000', changeOrigin: true } },
  },
})
