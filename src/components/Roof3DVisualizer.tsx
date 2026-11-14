import { Suspense, useEffect, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { Edges, Line, OrbitControls, useTexture } from '@react-three/drei';
import * as THREE from 'three';
import type { CellResult, MetricPolygon, MetricRoofGeometry, Obstruction, SunPosition } from '../services/sunSimulation';
import './Roof3DVisualizer.css';

type Bounds = { x: number; y: number; width: number; height: number };

type Roof3DVisualizerProps = {
  roofGeometry: MetricRoofGeometry;
  roofBounds: Bounds;
  roofWidthM: number;
  roofDepthM: number;
  buildingHeightM: number | null;
  obstructions: Obstruction[];
  cells: CellResult[];
  imageryUrl: string;
  surfaceLabel: string;
  sun: SunPosition;
  localTime: string;
};

function RoofPolygonSurface({
  polygon,
  centerX,
  centerY,
  roofWidthM,
  roofDepthM,
  imageryUrl,
  buildingHeightM,
  isInfrared,
}: {
  polygon: MetricPolygon;
  centerX: number;
  centerY: number;
  roofWidthM: number;
  roofDepthM: number;
  imageryUrl: string;
  buildingHeightM: number | null;
  isInfrared: boolean;
}) {
  const sourceTexture = useTexture(imageryUrl);
  const texture = useMemo(() => {
    const next = sourceTexture.clone();
    next.colorSpace = THREE.SRGBColorSpace;
    next.anisotropy = 8;
    next.needsUpdate = true;
    return next;
  }, [sourceTexture]);
  useEffect(() => () => texture.dispose(), [texture]);

  const shape = useMemo(() => {
    const next = new THREE.Shape();
    polygon.outer.forEach((point, index) => {
      const x = point.x - centerX;
      const y = point.y - centerY;
      if (index === 0) next.moveTo(x, y);
      else next.lineTo(x, y);
    });
    next.closePath();
    polygon.holes.forEach((ring) => {
      const hole = new THREE.Path();
      ring.forEach((point, index) => {
        const x = point.x - centerX;
        const y = point.y - centerY;
        if (index === 0) hole.moveTo(x, y);
        else hole.lineTo(x, y);
      });
      hole.closePath();
      next.holes.push(hole);
    });
    return next;
  }, [centerX, centerY, polygon]);

  const roofGeometry = useMemo(() => {
    const geometry = new THREE.ShapeGeometry(shape);
    const positions = geometry.attributes.position;
    const uv = new Float32Array(positions.count * 2);
    for (let index = 0; index < positions.count; index += 1) {
      uv[index * 2] = (positions.getX(index) + centerX) / roofWidthM;
      uv[index * 2 + 1] = 1 - (positions.getY(index) + centerY) / roofDepthM;
    }
    geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    return geometry;
  }, [centerX, centerY, roofDepthM, roofWidthM, shape]);

  const buildingGeometry = useMemo(() => buildingHeightM === null ? null : new THREE.ExtrudeGeometry(shape, {
    depth: buildingHeightM,
    bevelEnabled: false,
  }), [buildingHeightM, shape]);

  useEffect(() => () => {
    roofGeometry.dispose();
    buildingGeometry?.dispose();
  }, [buildingGeometry, roofGeometry]);

  return <>
    {buildingGeometry && <mesh geometry={buildingGeometry} rotation={[Math.PI / 2, 0, 0]} castShadow receiveShadow>
      <meshStandardMaterial color="#d9d4ca" roughness={.86} metalness={.02} />
    </mesh>}
    <mesh geometry={roofGeometry} rotation={[Math.PI / 2, 0, 0]} position={[0, .025, 0]} receiveShadow>
      {isInfrared
        ? <meshBasicMaterial map={texture} side={THREE.DoubleSide} toneMapped={false} />
        : <meshStandardMaterial map={texture} roughness={.72} metalness={.02} side={THREE.DoubleSide} />}
    </mesh>
  </>;
}

function RoofSurface({ geometry, ...props }: Omit<Parameters<typeof RoofPolygonSurface>[0], 'polygon'> & { geometry: MetricRoofGeometry }) {
  return <>{geometry.map((polygon, index) => <RoofPolygonSurface key={index} polygon={polygon} {...props} />)}</>;
}

function Scene({ props }: { props: Roof3DVisualizerProps }) {
  const isInfrared = props.surfaceLabel.startsWith('CIR');
  const centerX = props.roofBounds.x + props.roofBounds.width / 2;
  const centerY = props.roofBounds.y + props.roofBounds.height / 2;
  const span = Math.max(props.roofBounds.width, props.roofBounds.height, 12);
  const buildingHeight = props.buildingHeightM ?? 0;
  const altitude = THREE.MathUtils.degToRad(Math.max(.5, props.sun.altitude));
  const azimuth = THREE.MathUtils.degToRad(props.sun.azimuth);
  const sunDirection = new THREE.Vector3(
    Math.sin(azimuth) * Math.cos(altitude),
    Math.sin(altitude),
    -Math.cos(azimuth) * Math.cos(altitude),
  );
  const sunPosition = sunDirection.clone().multiplyScalar(span * 2.3);
  const cellSizeX = props.cells.length ? Math.max(.35, props.roofBounds.width / 22) : 0;
  const cellSizeZ = props.cells.length ? Math.max(.35, props.roofBounds.height / 22) : 0;
  const outlineRings = props.roofGeometry.flatMap((polygon) => [polygon.outer, ...polygon.holes]);

  return <>
    <ambientLight intensity={.72} color="#fff8ee" />
    {props.sun.altitude > 0 && <directionalLight
      position={sunPosition.toArray()}
      intensity={2.2}
      color="#fff1bd"
      castShadow
      shadow-mapSize-width={2048}
      shadow-mapSize-height={2048}
      shadow-camera-left={-span}
      shadow-camera-right={span}
      shadow-camera-top={span}
      shadow-camera-bottom={-span}
      shadow-camera-near={.1}
      shadow-camera-far={span * 6}
      shadow-bias={-.0004}
    />}
    <hemisphereLight intensity={.65} color="#fffaf3" groundColor="#d8d0c3" />

    <group position={[0, buildingHeight, 0]}>
      <RoofSurface
        geometry={props.roofGeometry}
        centerX={centerX}
        centerY={centerY}
        roofWidthM={props.roofWidthM}
        roofDepthM={props.roofDepthM}
        imageryUrl={props.imageryUrl}
        buildingHeightM={props.buildingHeightM}
        isInfrared={isInfrared}
      />
      {outlineRings.map((ring, index) => <Line
        key={`outline-${index}`}
        points={[...ring, ring[0]].map((point) => [point.x - centerX, .2, point.y - centerY])}
        color="#e85d04"
        lineWidth={2.2}
        transparent
        opacity={.94}
      />)}
      {props.obstructions.map((obstruction, index) => <mesh
        key={index}
        position={[
          obstruction.x + obstruction.width / 2 - centerX,
          obstruction.heightM / 2 + .05,
          obstruction.y + obstruction.depth / 2 - centerY,
        ]}
        castShadow
        receiveShadow
      >
        <boxGeometry args={[obstruction.width * .94, obstruction.heightM, obstruction.depth * .94]} />
        <meshStandardMaterial color="#f47b20" emissive="#c84a0a" emissiveIntensity={.12} roughness={.42} metalness={.08} transparent opacity={isInfrared ? .08 : .3} depthWrite={false} />
        <Edges color={isInfrared ? '#ff8a3d' : '#e85d04'} threshold={12} />
      </mesh>)}
      {props.cells.map((cell, index) => <mesh
        key={index}
        position={[cell.x - centerX, .12, cell.y - centerY]}
        receiveShadow
      >
        <boxGeometry args={[cellSizeX, .08, cellSizeZ]} />
        <meshStandardMaterial
          color={cell.sunlit ? '#ffad33' : '#53616a'}
          emissive={cell.sunlit ? '#d96b00' : '#26343c'}
          emissiveIntensity={isInfrared ? .05 : cell.sunlit ? .32 : .08}
          transparent
          opacity={isInfrared ? (cell.sunlit ? .22 : .28) : cell.sunlit ? .76 : .7}
          depthWrite={!isInfrared}
          roughness={.78}
        />
      </mesh>)}
    </group>

    <mesh position={[0, -.05, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <planeGeometry args={[span * 3.2, span * 3.2]} />
      <shadowMaterial color="#51606a" transparent opacity={.26} />
    </mesh>
    {props.buildingHeightM !== null && <gridHelper args={[span * 3, 30, '#e3a36f', '#ded8ce']} position={[0, 0, 0]} />}

    {props.sun.altitude > 0 && <>
      <mesh position={sunPosition.toArray()}>
        <sphereGeometry args={[Math.max(.8, span * .035), 24, 24]} />
        <meshBasicMaterial color="#fff2a0" />
      </mesh>
      <Line points={[sunPosition.toArray(), [0, buildingHeight, 0]]} color="#ffde65" lineWidth={1.6} dashed dashSize={1.5} gapSize={1.1} transparent opacity={.75} />
      <pointLight position={sunPosition.toArray()} color="#ffd96b" intensity={20} distance={span * 1.2} />
    </>}

    <OrbitControls
      target={[0, buildingHeight * .65, 0]}
      enableDamping
      dampingFactor={.075}
      minDistance={span * .45}
      maxDistance={span * 4}
      maxPolarAngle={Math.PI * .49}
      makeDefault
    />
  </>;
}

export default function Roof3DVisualizer(props: Roof3DVisualizerProps) {
  const span = Math.max(props.roofBounds.width, props.roofBounds.height, 12);
  const buildingHeight = props.buildingHeightM ?? 0;
  const shadedCells = props.cells.filter((cell) => !cell.sunlit).length;

  return <div className="roof-3d-view">
    <Canvas
      camera={{
        position: [span * .82, Math.max(span * .7, buildingHeight * 1.8 + 15), span * .86],
        fov: 42,
        near: .1,
        far: span * 15,
      }}
      dpr={[1, 1.75]}
      gl={{ antialias: true, alpha: false, toneMapping: THREE.ACESFilmicToneMapping }}
      shadows
    >
      <color attach="background" args={['#f5f2eb']} />
      <fog attach="fog" args={['#f5f2eb', span * 2.2, span * 6]} />
      <Suspense fallback={null}><Scene props={props} /></Suspense>
    </Canvas>
    <div className="roof-3d-hud roof-3d-hud--left">
      <span className="mono">ROOF VIEW</span>
      <strong>{props.localTime}</strong>
      <small>Drag to orbit · scroll to zoom</small>
    </div>
    <div className="roof-3d-hud roof-3d-hud--right">
      <div><small>SURFACE</small><strong>{props.surfaceLabel}</strong></div>
      <div><small>SUN</small><strong>{props.sun.altitude.toFixed(1)}°</strong></div>
      <div><small>AZIMUTH</small><strong>{props.sun.azimuth.toFixed(0)}°</strong></div>
      <div><small>SHADED CELLS</small><strong>{shadedCells}</strong></div>
      <div><small>ROOF FEATURES</small><strong>{props.obstructions.length}</strong></div>
    </div>
    <div className="roof-3d-legend"><span><i className="legend-sun" /> Direct sun</span><span><i className="legend-shade" /> Shade</span><span><i className="legend-height" /> Measured elevation</span></div>
    {props.surfaceLabel.startsWith('CIR') && <div className="roof-3d-cir-note"><span className="mono">CIR / IRG</span><strong>Red indicates near-infrared reflectance</strong><small>Vegetation is vivid red. Roofing, concrete, and metal may remain gray or pale.</small></div>}
  </div>;
}
