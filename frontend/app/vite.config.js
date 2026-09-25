import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { viteStaticCopy } from 'vite-plugin-static-copy'

const cesiumSource = 'node_modules/cesium/Build/Cesium'

export default defineConfig({
  define: {
    CESIUM_BASE_URL: JSON.stringify('/cesium'),
  },

  plugins: [
    react(),

    viteStaticCopy({
      targets: [
        // Strip node_modules/cesium/Build/Cesium from the output paths.
        { src: `${cesiumSource}/Workers`, dest: 'cesium', rename: { stripBase: 4 } },
        { src: `${cesiumSource}/Assets`, dest: 'cesium', rename: { stripBase: 4 } },
        { src: `${cesiumSource}/Widgets`, dest: 'cesium', rename: { stripBase: 4 } },
        { src: `${cesiumSource}/ThirdParty`, dest: 'cesium', rename: { stripBase: 4 } },
      ],
    }),
  ],
})
