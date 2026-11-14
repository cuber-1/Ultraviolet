import assert from 'node:assert/strict';
import { predictableShadowLength, sharedMeetingArea, simulate, type SimulationResult } from '../src/services/sunSimulation.ts';
import { insideMetricGeometry, roofWktToMetricGeometry } from '../src/services/roofGeometry.ts';

assert.ok(Math.abs(predictableShadowLength(10, 45) - 10) < 1e-9, 'a 10 m obstruction at 45 degrees must cast a 10 m shadow');

const result = simulate({
  date: '2026-03-20', minute: 9 * 60, timezoneOffsetHours: 0,
  lat: 0, lon: 0, roofAreaSqft: 10_000, roofWidthM: 30.48, roofDepthM: 30.48,
  selection: { x: 0, y: 0, width: 30.48, height: 30.48 },
  obstructions: [{ x: 12, y: 12, width: 4, depth: 4, heightM: 8 }], targetHours: 6,
});
assert.equal(result.cells.length, 400);
const renderedSunArea = result.cells.filter((cell) => cell.sunlit).length * result.totalAreaSqft / result.cells.length;
assert.ok(Math.abs(renderedSunArea - (result.directAreaSqft ?? 0)) < 1e-8, 'reported coverage and overlay cells must use identical geometry');
assert.ok((result.directAreaSqft ?? 0) < result.totalAreaSqft, 'the predictable obstruction must shade part of the roof');

const complexRoof = roofWktToMetricGeometry('MULTIPOLYGON (((-0.0001 -0.0001, 0.0001 -0.0001, 0.0001 0.0001, -0.0001 0.0001, -0.0001 -0.0001), (-0.00003 -0.00003, 0.00003 -0.00003, 0.00003 0.00003, -0.00003 0.00003, -0.00003 -0.00003)), ((0.0002 -0.00005, 0.0003 -0.00005, 0.0003 0.00005, 0.0002 0.00005, 0.0002 -0.00005)))', 0, 0, 50);
assert.equal(complexRoof.length, 2, 'MULTIPOLYGON roof WKT must retain separate proposed surfaces');
assert.equal(complexRoof[0].holes.length, 1, 'roof WKT holes must remain excluded from the surface');
assert.equal(insideMetricGeometry(50, 50, complexRoof), false, 'a point in a roof courtyard or opening must not enter the sunlight grid');
assert.equal(insideMetricGeometry(42, 42, complexRoof), true, 'a point on the complex roof surface must enter the sunlight grid');
const complexResult = simulate({
  date: '2026-03-20', minute: 12 * 60, timezoneOffsetHours: 0,
  lat: 0, lon: 0, roofAreaSqft: 10_000, roofWidthM: 100, roofDepthM: 100,
  roofGeometry: complexRoof, selection: { x: 0, y: 0, width: 100, height: 100 },
  obstructions: [], targetHours: 6,
});
assert.ok(complexResult.cells.length > 0 && complexResult.cells.length < 400, 'sunlight cells must be clipped to complex WKT surfaces and holes');

const make = (hours: number[]): SimulationResult => ({
  sun: { altitude: 45, azimuth: 180 }, totalAreaSqft: 100, directAreaSqft: 50,
  meetingTargetAreaSqft: 50, estimatedHours: 6, resolutionMinutes: 30, geometryAvailable: true,
  cells: hours.map((value, index) => ({ x: index, y: 0, sunlit: true, hours: value })),
});
assert.equal(sharedMeetingArea([make([7, 7, 0, 0]), make([0, 0, 7, 7])]), 0, 'disjoint suitable areas must not be reported as shared area');

console.log('Sun simulation checks passed: shadow length, overlay/metric parity, complex WKT clipping, and shared-cell intersection.');
