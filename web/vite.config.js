import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,              // para poder abrirlo desde el celular en la misma red
    proxy: { '/api': 'http://localhost:8000' },
  },
})
