import { useRef, useState } from 'react'
import MoonMap from './MoonMap.jsx'

const formatCoordinate = (value, positive, negative) =>
  Math.abs(value).toFixed(4) + '° ' + (value < 0 ? negative : positive)

export default function App() {
  const [selectedLocation, setSelectedLocation] = useState(null)
  const [showGrid, setShowGrid] = useState(true)
  const [showAxis, setShowAxis] = useState(true)
  const [copyStatus, setCopyStatus] = useState('')
  const controlsRef = useRef(null)

  async function copyLocation() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(selectedLocation, null, 2))
      setCopyStatus('Coordinates copied')
    } catch {
      setCopyStatus('Copy unavailable. You can select the coordinates below.')
    }
  }

  return (
    <main className="explorer">
      <header className="app-header">
        <a className="brand" href="./" aria-label="Lunar Explorer home">
          <span className="brand-moon" aria-hidden="true" />
          <span>CLPS <span className="brand-subtitle">/ Lunar Explorer</span></span>
        </a>
        <a className="source-link" href="https://svs.gsfc.nasa.gov/14959/" target="_blank" rel="noreferrer">NASA model ↗</a>
      </header>

      <aside className="explorer-panel">
        <div className="intro">
          <p className="eyebrow">A closer look at our Moon</p>
          <h1>A world to explore.</h1>
          <p className="description">Travel across the lunar surface. Find a new perspective. Choose a place to begin.</p>
        </div>

        <section className="panel-section" aria-labelledby="perspective-title">
          <h2 id="perspective-title">Choose a perspective</h2>
          <div className="view-buttons">
            <button onClick={() => controlsRef.current?.setView('near')}>Near side <span>↗</span></button>
            <button onClick={() => controlsRef.current?.setView('far')}>Far side <span>↗</span></button>
            <button onClick={() => controlsRef.current?.setView('south')}>South pole <span>↗</span></button>
          </div>
        </section>

        <section className="panel-section" aria-labelledby="guides-title">
          <h2 id="guides-title">Map guides</h2>
          <label className="toggle-row"><span>Coordinate grid <small>Every 30°</small></span><input type="checkbox" checked={showGrid} onChange={event => setShowGrid(event.target.checked)} /></label>
          <label className="toggle-row"><span>Rotation axis <small>North / south</small></span><input type="checkbox" checked={showAxis} onChange={event => setShowAxis(event.target.checked)} /></label>
          <div className="legend"><span><i className="equator-dot" />Equator</span><span><i className="meridian-dot" />0° meridian</span></div>
        </section>

        <section className="location-card" aria-labelledby="location-title">
          <div className="location-heading"><h2 id="location-title">Selected location</h2><span className="selection-dot" /></div>
          <div aria-live="polite">
            {selectedLocation ? (
              <dl className="coordinates">
                <div><dt>Latitude</dt><dd>{formatCoordinate(selectedLocation.latitude, 'N', 'S')}</dd></div>
                <div><dt>Longitude</dt><dd>{formatCoordinate(selectedLocation.longitude, 'E', 'W')}</dd></div>
              </dl>
            ) : <p className="location-empty">Click anywhere on the Moon<br />to discover its coordinates.</p>}
          </div>
          {selectedLocation && <button className="copy-button" onClick={copyLocation}>Copy coordinates <span>↗</span></button>}
          <p className="copy-status" role="status">{copyStatus}</p>
        </section>

        <footer className="panel-footer">Surface model: NASA’s Goddard Space Flight Center.<br />Illustrative lighting · Spherical surface, without terrain relief.</footer>
      </aside>

      <section className="map-stage" aria-label="Lunar map">
        <div className="map-caption"><span className="eyebrow">The Moon</span><span>NASA / LRO surface imagery</span></div>
        <MoonMap onLocationSelect={setSelectedLocation} selectedLocation={selectedLocation} showGrid={showGrid} showAxis={showAxis} controlsRef={controlsRef} />
        <div className="map-controls" aria-label="Camera controls">
          <button aria-label="Zoom in" onClick={() => controlsRef.current?.zoom(1)}>+</button>
          <button aria-label="Zoom out" onClick={() => controlsRef.current?.zoom(-1)}>−</button>
          <button className="reset-button" onClick={() => controlsRef.current?.setView('near')}>Reset view</button>
        </div>
        <p className="map-help"><span>Drag to explore</span><span>Scroll to zoom</span><span>Click to select</span></p>
      </section>
    </main>
  )
}
