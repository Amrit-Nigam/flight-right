const EARTH_RADIUS_NM = 3440.065;

function toRadians(deg) {
  return (Number(deg) * Math.PI) / 180;
}

function haversineNm(a, b) {
  const lat1 = toRadians(a.lat);
  const lat2 = toRadians(b.lat);
  const dLat = toRadians(b.lat - a.lat);
  const dLon = toRadians(b.lng - a.lng);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_NM * Math.asin(Math.sqrt(h));
}

function bearingDiffDeg(a, b) {
  const raw = Math.abs((Number(a) || 0) - (Number(b) || 0)) % 360;
  return raw > 180 ? 360 - raw : raw;
}

function projectPosition(aircraft, minutesAhead) {
  const lat = Number(aircraft.lat);
  const lng = Number(aircraft.lng);
  const speedKt = Number(aircraft.speedKt || 0);
  const heading = Number(aircraft.heading || 0);

  if (!Number.isFinite(lat) || !Number.isFinite(lng) || !Number.isFinite(speedKt)) {
    return { lat, lng };
  }

  const distanceNm = (speedKt * Number(minutesAhead || 0)) / 60;
  const bearing = toRadians(heading);
  const lat1 = toRadians(lat);
  const lon1 = toRadians(lng);
  const angularDistance = distanceNm / EARTH_RADIUS_NM;

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angularDistance) +
      Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing)
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1),
      Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2)
    );

  return {
    lat: (lat2 * 180) / Math.PI,
    lng: ((((lon2 * 180) / Math.PI + 540) % 360) - 180),
  };
}

function minProjectedSeparation(a, b, lookaheadMinutes = 10, stepMinutes = 1) {
  let minDistanceNm = Infinity;
  let timeToMinMinutes = 0;

  for (let t = 0; t <= lookaheadMinutes; t += stepMinutes) {
    const pa = projectPosition(a, t);
    const pb = projectPosition(b, t);
    const distanceNm = haversineNm(pa, pb);
    if (distanceNm < minDistanceNm) {
      minDistanceNm = distanceNm;
      timeToMinMinutes = t;
    }
  }

  return { minDistanceNm, timeToMinMinutes };
}

function verticalSeparationFt(a, b) {
  return Math.abs(Number(a.altitudeFt || 0) - Number(b.altitudeFt || 0));
}

function closingSpeedKt(a, b) {
  const headingDiff = toRadians(bearingDiffDeg(a.heading, b.heading));
  const va = Number(a.speedKt || 0);
  const vb = Number(b.speedKt || 0);
  return Math.sqrt(Math.max(0, va ** 2 + vb ** 2 - 2 * va * vb * Math.cos(headingDiff)));
}

module.exports = {
  bearingDiffDeg,
  closingSpeedKt,
  haversineNm,
  minProjectedSeparation,
  projectPosition,
  verticalSeparationFt,
};
