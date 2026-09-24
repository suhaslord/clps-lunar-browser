# CLPS Lunar Browser

we're building this for NASA Space Apps 2026

basic idea is u pick a lunar landing spot + date/time and it shows where the sun and earth are from that spot. from there we can tell if theres sunlight for power and if earth is visible for comms.

## what we're tryna make

- moon map + landing site picker
- date/time controls
- sun + earth position calculations
- horizon view so u can actually see where they are
- sunlight / comm timelines
- terrain blocking later so crater rims and stuff actually matter
- real CLPS mission + landing site data

## who's doing what rn

- **suhas + rishi** - backend + sun/earth calculations
- **tap + hemanth** - website/frontend
- **dip** - horizon + timeline visualizations
- **srikar** - terrain stuff + testing/integration

not super strict tho, if someone finishes their part just help wherever

## repo layout

```
backend/        sun/earth calc + api
frontend/       main site
visualization/  horizon + timeline stuff
terrain/        terrain/horizon processing
data/           landing sites + mission data
docs/           shared api format
```

## main flow

```
landing spot + date/time
        ↓
backend calculates sun + earth position
        ↓
terrain checks if either one is blocked
        ↓
frontend shows the result
        ↓
visualizations make it easy to understand
```

## backend output

keeping one shared format so frontend/visualization can work before the full backend is done

```json
{
  "site": "Shackleton Rim",
  "latitude": -89.5,
  "longitude": 135.0,
  "time": "2026-10-03T18:00:00Z",
  "sun": {
    "azimuth": 124.2,
    "elevation": 3.7,
    "visible": true
  },
  "earth": {
    "azimuth": 241.8,
    "elevation": 7.1,
    "visible": true
  }
}
```

## working on it

make ur own branch for your part and PR it into main when its ready. try not to directly edit main unless its something tiny.

still early rn so this will prob change a lot once we start putting everything together.
