import { ArcType, Cartesian2, Cartesian3, Color, Ellipsoid, LabelStyle } from 'cesium'

export const MOON = Ellipsoid.MOON
export const RADIUS = MOON.maximumRadius
export const lunarPosition = (longitude, latitude, height = 0) => Cartesian3.fromDegrees(longitude, latitude, height, MOON)

export function createMoonGuides(viewer) {
  const grid = []
  const axis = []
  const line = (positions, color, width, group) => group.push(viewer.entities.add({
    polyline: { positions, width, material: Color.fromCssColorString(color), arcType: ArcType.NONE },
  }))
  // Explicit lunar positions avoid the Earth ellipsoid used by default geodesics.
  for (let lat = -60; lat <= 60; lat += 30) {
    const points = []
    for (let lon = -180; lon <= 180; lon += 2) points.push(lunarPosition(lon, lat, 6000))
    line(points, lat === 0 ? '#91d4beaa' : '#c0ccd43b', lat === 0 ? 1.6 : 1, grid)
  }
  for (let lon = -180; lon < 180; lon += 30) {
    const points = []
    for (let lat = -90; lat <= 90; lat += 2) points.push(lunarPosition(lon, lat, 6000))
    line(points, lon === 0 ? '#dec19ca0' : '#c0ccd43b', lon === 0 ? 1.6 : 1, grid)
  }
  line([new Cartesian3(0, 0, -RADIUS * 1.28), new Cartesian3(0, 0, RADIUS * 1.28)], '#a9dccc', 2, axis)
  for (const [sign, text] of [[1, 'N · 90°'], [-1, 'S · 90°']]) {
    axis.push(viewer.entities.add({
      position: new Cartesian3(0, 0, sign * RADIUS * 1.3),
      label: { text, font: '12px monospace', fillColor: Color.fromCssColorString('#cae7df'),
        outlineColor: Color.fromCssColorString('#091216'), outlineWidth: 3,
        style: LabelStyle.FILL_AND_OUTLINE, pixelOffset: new Cartesian2(0, sign * -12) },
    }))
  }
  return { grid, axis }
}
