import { useEffect, useRef } from 'react'
import {
  Cartesian3,
  Ellipsoid,
  SingleTileImageryProvider,
  Viewer,
  buildModuleUrl,
} from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'

export default function MoonMap() {
  const containerRef = useRef(null)

  useEffect(() => {
    const moon = Ellipsoid.MOON

    const viewer = new Viewer(containerRef.current, {
      ellipsoid: moon,
      baseLayer: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      skyBox: false,
      skyAtmosphere: false,
      requestRenderMode: true,
    })

    // Keep the surface visible while we explore.
    // Sunlight calculations will come from the backend later.
    viewer.scene.globe.enableLighting = false

    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(0, 0, 6000000, moon),
    })

    viewer.scene.screenSpaceCameraController.minimumZoomDistance = 1000
    viewer.scene.screenSpaceCameraController.maximumZoomDistance = 15000000

    async function loadMoonTexture() {
      try {
        const imagery = await SingleTileImageryProvider.fromUrl(
          buildModuleUrl('Assets/Textures/moonSmall.jpg'),
          { ellipsoid: moon },
        )

        if (!viewer.isDestroyed()) {
          viewer.imageryLayers.addImageryProvider(imagery)
          viewer.scene.requestRender()
        }
      } catch (error) {
        console.error('Could not load the Moon texture:', error)
      }
    }

    loadMoonTexture()

    // Release the graphics resources when React removes this component.
    return () => viewer.destroy()
  }, [])

  return <div ref={containerRef} className="moon-map" />
}