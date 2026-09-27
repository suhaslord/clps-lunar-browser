import { useEffect, useRef, useState } from 'react'
import {
  Axis, Cartesian2, Cartesian3, Color, DirectionalLight,
  Math as CesiumMath, Matrix3, Matrix4, Model, ScreenSpaceEventHandler,
  ScreenSpaceEventType, Viewer,
} from 'cesium'
import { createMoonGuides, lunarPosition, MOON, RADIUS } from './moonGuides.js'
import 'cesium/Build/Cesium/Widgets/widgets.css'

const VIEWS = { near: [0, 12], far: [180, 12], south: [0, -85] }

export default function MoonMap({ onLocationSelect, selectedLocation, showGrid, showAxis, controlsRef }) {
  const containerRef = useRef(null)
  const sceneRef = useRef(null)
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    let viewer
    try {
      viewer = new Viewer(containerRef.current, {
        ellipsoid: MOON, baseLayer: false, baseLayerPicker: false,
        geocoder: false, homeButton: false, sceneModePicker: false,
        navigationHelpButton: false, animation: false, timeline: false,
        fullscreenButton: false, infoBox: false, selectionIndicator: false,
        skyBox: false, skyAtmosphere: false, requestRenderMode: true,
        scene3DOnly: true, shouldAnimate: false,
      })
    } catch (error) {
      console.error('Could not initialize the Moon viewer', error)
      // A failed external WebGL viewer must be reflected in the UI.
      // oxlint-disable-next-line react/set-state-in-effect
      setStatus('error')
      return
    }

    // Render NASA's mesh, retaining the lunar ellipsoid for camera/picking math.
    viewer.scene.globe.show = false
    viewer.scene.backgroundColor = Color.fromCssColorString('#0a1014')
    viewer.scene.fog.enabled = false
    viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 2)
    viewer.scene.postProcessStages.fxaa.enabled = true
    const light = new DirectionalLight({ direction: new Cartesian3(-1, 0, 0), intensity: 4.0 })
    viewer.scene.light = light
    // Illustrative camera-relative light, independent of the astronomical API.
    const removeLightListener = viewer.scene.preRender.addEventListener(() => {
      const direction = Cartesian3.clone(viewer.camera.directionWC)
      Cartesian3.add(direction, Cartesian3.multiplyByScalar(viewer.camera.rightWC, 0.45, new Cartesian3()), direction)
      Cartesian3.add(direction, Cartesian3.multiplyByScalar(viewer.camera.upWC, -0.35, new Cartesian3()), direction)
      Cartesian3.normalize(direction, light.direction)
    })
    const controller = viewer.scene.screenSpaceCameraController
    controller.minimumZoomDistance = 50000
    controller.maximumZoomDistance = 14000000
    const guides = createMoonGuides(viewer)
    const point = viewer.entities.add({
      show: false,
      point: { color: Color.fromCssColorString('#a2ecd3'), pixelSize: 10, outlineColor: Color.fromCssColorString('#0d1819'), outlineWidth: 3 },
    })
    sceneRef.current = { viewer, guides, point }

    const setView = (name = 'near', animate = true) => {
      const [longitude, latitude] = VIEWS[name] || VIEWS.near
      const options = {
        destination: lunarPosition(longitude, latitude, 5400000),
        orientation: { heading: 0, pitch: -CesiumMath.PI_OVER_TWO, roll: 0 },
      }
      if (animate && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        viewer.camera.flyTo({ ...options, duration: 0.9 })
      } else viewer.camera.setView(options)
      viewer.scene.requestRender()
    }
    controlsRef.current = {
      setView,
      zoom: (direction) => {
        viewer.camera.cancelFlight()
        const height = viewer.camera.positionCartographic.height
        const distance = Math.max(height * 0.22, 30000)
        if (direction > 0) viewer.camera.zoomIn(Math.min(distance, Math.max(0, height - 50000)))
        else viewer.camera.zoomOut(Math.min(distance, Math.max(0, 14000000 - height)))
        viewer.scene.requestRender()
      },
    }
    setView('near', false)

    let moonModel
    let cancelled = false
    const clickHandler = new ScreenSpaceEventHandler(viewer.scene.canvas)
    clickHandler.setInputAction((click) => {
      if (!moonModel?.ready) return
      const position = viewer.camera.pickEllipsoid(click.position, MOON)
      if (!position) return
      const coordinate = MOON.cartesianToCartographic(position)
      onLocationSelect({
        latitude: CesiumMath.toDegrees(coordinate.latitude),
        longitude: CesiumMath.toDegrees(coordinate.longitude),
      })
    }, ScreenSpaceEventType.LEFT_CLICK)
    viewer.screenSpaceEventHandler.removeInputAction(ScreenSpaceEventType.LEFT_DOUBLE_CLICK)

    async function loadModel() {
      try {
        // Native (x,y,z) -> lunar (-z,-x,y), compared against NASA's
        // longitude-centered LROC map. Disable Cesium's extra glTF axis rotation.
        const rotation = Matrix3.fromArray([0, -1, 0, 0, 0, 1, -1, 0, 0])
        const model = await Model.fromGltfAsync({
          url: import.meta.env.BASE_URL + 'nasa-moon.glb',
          modelMatrix: Matrix4.fromRotationTranslation(rotation),
          scale: RADIUS / 1.282231258940614,
          upAxis: Axis.Z, forwardAxis: Axis.X,
          allowPicking: true,
        })
        if (cancelled) { model.destroy(); return }
        model.imageBasedLighting.imageBasedLightingFactor = new Cartesian2(0.7, 0)
        moonModel = viewer.scene.primitives.add(model)
        model.readyEvent.addEventListener(() => {
          if (!cancelled) { setStatus('ready'); viewer.scene.requestRender() }
        })
        model.errorEvent.addEventListener((error) => {
          console.error('NASA Moon model failed to render', error)
          if (!cancelled) setStatus('error')
        })
        viewer.scene.requestRender()
      } catch (error) {
        console.error('Could not load NASA Moon model', error)
        if (!cancelled) setStatus('error')
      }
    }
    loadModel()
    return () => {
      cancelled = true
      controlsRef.current = null
      sceneRef.current = null
      clickHandler.destroy()
      removeLightListener()
      viewer.destroy()
    }
  }, [onLocationSelect, controlsRef])

  useEffect(() => {
    const scene = sceneRef.current
    if (!scene) return
    scene.guides.grid.forEach((entity) => { entity.show = showGrid })
    scene.guides.axis.forEach((entity) => { entity.show = showAxis })
    scene.viewer.scene.requestRender()
  }, [showGrid, showAxis])

  useEffect(() => {
    const scene = sceneRef.current
    if (!scene) return
    scene.point.show = Boolean(selectedLocation)
    if (selectedLocation) scene.point.position = lunarPosition(selectedLocation.longitude, selectedLocation.latitude, 8000)
    scene.viewer.scene.requestRender()
  }, [selectedLocation])

  return (
    <>
      <div ref={containerRef} className="moon-map" aria-label="Interactive 3D Moon. Drag to rotate, scroll to zoom, and click to select coordinates." />
      {status !== 'ready' && (
        <div className="map-message" role="status">
          <span className="loading-orbit" aria-hidden="true" />
          <strong>{status === 'error' ? 'The Moon could not load' : 'Bringing the Moon into view'}</strong>
          <span>{status === 'error' ? 'Refresh the page to retry the local NASA model.' : 'Loading NASA’s lunar surface model…'}</span>
        </div>
      )}
    </>
  )
}
