import { Suspense, useEffect, useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { Edges, Line, OrbitControls, useTexture } from '@react-three/drei';
import * as THREE from 'three';
import { shadowVector, type CellResult, type MetricPolygon, type MetricRoofGeometry, type Obstruction, type SunPosition } from '../services/sunSimulation';
import './Roof3DVisualizer.css';

type Bounds = { x: number; y: number; width: number; height: number };
type SurfaceMode = 'imagery' | 'clean';
type Point2 = { x: number; y: number };

function convexHull(points: Point2[]) {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (origin: Point2, a: Point2, b: Point2) => (a.x - origin.x) * (b.y - origin.y) - (a.y - origin.y) * (b.x - origin.x);
  const lower: Point2[] = [];
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower.at(-2)!, lower.at(-1)!, point) <= 0) lower.pop();
    lower.push(point);
  }
  const upper: Point2[] = [];
  for (const point of sorted.reverse()) {
    while (upper.length >= 2 && cross(upper.at(-2)!, upper.at(-1)!, point) <= 0) upper.pop();
    upper.push(point);
  }
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

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
  surfaceMode,
}: {
  polygon: MetricPolygon;
  centerX: number;
  centerY: number;
  roofWidthM: number;
  roofDepthM: number;
  imageryUrl: string;
  buildingHeightM: number | null;
  isInfrared: boolean;
  surfaceMode: SurfaceMode;
}) {
  const sourceTexture = useTexture(imageryUrl);
  const texture = useMemo(() => {
    const next = sourceTexture.clone();
    next.colorSpace = isInfrared ? THREE.NoColorSpace : THREE.SRGBColorSpace;
    next.anisotropy = 8;
    next.needsUpdate = true;
    return next;
  }, [isInfrared, sourceTexture]);
  const infraredMaterial = useMemo(() => {
    if (!isInfrared) return null;
    const image = sourceTexture.image as { width?: number; height?: number };
    return new THREE.ShaderMaterial({
      side: THREE.DoubleSide,
      uniforms: {
        map: { value: texture },
        texelSize: { value: new THREE.Vector2(1 / (image.width || 800), 1 / (image.height || 800)) },
      },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform sampler2D map;
        uniform vec2 texelSize;
        varying vec2 vUv;

        void main() {
          float nir = texture2D(map, vUv).r * 0.4;
          nir += texture2D(map, vUv + vec2(texelSize.x, 0.0)).r * 0.15;
          nir += texture2D(map, vUv - vec2(texelSize.x, 0.0)).r * 0.15;
          nir += texture2D(map, vUv + vec2(0.0, texelSize.y)).r * 0.15;
          nir += texture2D(map, vUv - vec2(0.0, texelSize.y)).r * 0.15;
          float value = smoothstep(0.08, 0.92, nir);
          vec3 cream = vec3(0.972, 0.956, 0.925);
          vec3 orange = vec3(0.933, 0.467, 0.165);
          vec3 umber = vec3(0.412, 0.133, 0.035);
          vec3 color = value < 0.62
            ? mix(cream, orange, value / 0.62)
            : mix(orange, umber, (value - 0.62) / 0.38);
          gl_FragColor = vec4(color, 1.0);
        }
      `,
    });
  }, [isInfrared, sourceTexture.image, texture]);
  useEffect(() => () => texture.dispose(), [texture]);
  useEffect(() => () => infraredMaterial?.dispose(), [infraredMaterial]);

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
    {surfaceMode === 'clean' ? <>
      <mesh key="clean-roof" geometry={roofGeometry} rotation={[Math.PI / 2, 0, 0]} position={[0, .025, 0]}>
        <meshBasicMaterial color="#63a878" side={THREE.DoubleSide} toneMapped={false} stencilWrite stencilRef={1} stencilFunc={THREE.AlwaysStencilFunc} stencilZPass={THREE.ReplaceStencilOp} />
      </mesh>
    </> : <>
      <mesh key="imagery-roof" geometry={roofGeometry} rotation={[Math.PI / 2, 0, 0]} position={[0, .025, 0]} receiveShadow>
        {isInfrared
          ? <primitive object={infraredMaterial!} attach="material" />
          : <meshStandardMaterial map={texture} roughness={.72} metalness={.02} side={THREE.DoubleSide} />}
      </mesh>
      {isInfrared && <mesh geometry={roofGeometry} rotation={[Math.PI / 2, 0, 0]} position={[0, .04, 0]} receiveShadow>
        <shadowMaterial color="#2b211b" transparent opacity={.22} depthWrite={false} />
      </mesh>}
    </>}
  </>;
}

function ProjectedShadow({ obstruction, sun, centerX, centerY }: { obstruction: Obstruction; sun: SunPosition; centerX: number; centerY: number }) {
  const geometry = useMemo(() => {
    const vector = shadowVector(sun, obstruction.heightM);
    if (!vector) return null;
    const corners = [
      { x: obstruction.x, y: obstruction.y },
      { x: obstruction.x + obstruction.width, y: obstruction.y },
      { x: obstruction.x + obstruction.width, y: obstruction.y + obstruction.depth },
      { x: obstruction.x, y: obstruction.y + obstruction.depth },
    ];
    const hull = convexHull([...corners, ...corners.map((point) => ({ x: point.x + vector.dx, y: point.y + vector.dy }))]);
    const shape = new THREE.Shape();
    hull.forEach((point, index) => {
      const x = point.x - centerX;
      const y = point.y - centerY;
      if (index === 0) shape.moveTo(x, y);
      else shape.lineTo(x, y);
    });
    shape.closePath();
    return new THREE.ShapeGeometry(shape);
  }, [centerX, centerY, obstruction, sun]);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  if (!geometry) return null;
  return <mesh geometry={geometry} rotation={[Math.PI / 2, 0, 0]} position={[0, .055, 0]} renderOrder={2}>
    <meshBasicMaterial color="#17251d" transparent opacity={.42} depthWrite={false} toneMapped={false} side={THREE.DoubleSide} stencilWrite stencilRef={1} stencilFunc={THREE.EqualStencilFunc} stencilFail={THREE.KeepStencilOp} stencilZFail={THREE.KeepStencilOp} stencilZPass={THREE.KeepStencilOp} />
  </mesh>;
}

function RoofSurface({ geometry, ...props }: Omit<Parameters<typeof RoofPolygonSurface>[0], 'polygon'> & { geometry: MetricRoofGeometry }) {
  return <>{geometry.map((polygon, index) => <RoofPolygonSurface key={index} polygon={polygon} {...props} />)}</>;
}

function Scene({ props, surfaceMode }: { props: Roof3DVisualizerProps; surfaceMode: SurfaceMode }) {
  const isInfrared = props.surfaceLabel.startsWith('CIR');
  const isNight = props.sun.altitude <= 0;
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
  const outlineRings = props.roofGeometry.flatMap((polygon) => [polygon.outer, ...polygon.holes]);

  return <>
    <ambientLight intensity={.78} color="#ffffff" />
    {props.sun.altitude > 0 && <directionalLight
      position={sunPosition.toArray()}
      intensity={2.2}
      color="#fff7ef"
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
    <hemisphereLight intensity={.6} color="#ffffff" groundColor="#d7d2cc" />

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
        surfaceMode={surfaceMode}
      />
      {surfaceMode === 'clean' && props.obstructions.map((obstruction, index) => <ProjectedShadow key={`shadow-${index}`} obstruction={obstruction} sun={props.sun} centerX={centerX} centerY={centerY} />)}
      {outlineRings.map((ring, index) => <Line
        key={`outline-${index}`}
        points={[...ring, ring[0]].map((point) => [point.x - centerX, .2, point.y - centerY])}
        color={isNight ? '#17251d' : surfaceMode === 'clean' ? '#236143' : '#e85d04'}
        lineWidth={isNight ? 3.2 : 2.2}
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
        castShadow={surfaceMode === 'imagery'}
        receiveShadow
      >
        <boxGeometry args={[obstruction.width * .94, obstruction.heightM, obstruction.depth * .94]} />
        {surfaceMode === 'clean'
          ? <meshBasicMaterial color="#f36b16" toneMapped={false} />
          : <meshStandardMaterial color="#d9d2ca" roughness={.68} metalness={.02} transparent opacity={.48} depthWrite={false} />}
        <Edges color={surfaceMode === 'clean' ? '#8f3000' : '#e85d04'} threshold={12} />
      </mesh>)}
    </group>

    {surfaceMode === 'imagery' && <mesh position={[0, -.05, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <planeGeometry args={[span * 3.2, span * 3.2]} />
      <shadowMaterial color="#292522" transparent opacity={.2} />
    </mesh>}

    {props.sun.altitude > 0 && <>
      <mesh position={sunPosition.toArray()}>
        <sphereGeometry args={[Math.max(.8, span * .035), 24, 24]} />
        <meshBasicMaterial color="#f36b16" />
      </mesh>
      <Line points={[sunPosition.toArray(), [0, buildingHeight, 0]]} color="#e85d04" lineWidth={1.3} dashed dashSize={1.5} gapSize={1.1} transparent opacity={.7} />
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
  const [surfaceMode, setSurfaceMode] = useState<SurfaceMode>('imagery');
  const isNight = props.sun.altitude <= 0;

  return <div className="roof-3d-view">
    <Canvas
      camera={{
        position: [span * .82, Math.max(span * .7, buildingHeight * 1.8 + 15), span * .86],
        fov: 42,
        near: .1,
        far: span * 15,
      }}
      dpr={[1, 1.75]}
      gl={{ antialias: true, alpha: false, stencil: true, toneMapping: THREE.ACESFilmicToneMapping }}
      shadows
    >
      <color attach="background" args={['#f7f5f2']} />
      <fog attach="fog" args={['#f7f5f2', span * 2.2, span * 6]} />
      <Suspense fallback={null}><Scene props={props} surfaceMode={surfaceMode} /></Suspense>
    </Canvas>
    <div className="roof-3d-hud roof-3d-hud--left">
      <span className="mono">ROOF VIEW</span>
      <strong>{props.localTime}</strong>
      <small>Drag to orbit · scroll to zoom</small>
    </div>
    <div className="roof-3d-status">
      <span>{surfaceMode === 'clean' ? 'CLEAN' : props.surfaceLabel.startsWith('CIR') ? 'NIR' : 'RGB'}</span>
      <strong>{isNight ? 'Night' : `${props.sun.altitude.toFixed(1)}° sun`}</strong>
      <small>{isNight ? `Sun below horizon · ${props.obstructions.length} measured features` : `${props.sun.azimuth.toFixed(0)}° azimuth · ${props.obstructions.length} measured features`}</small>
    </div>
    <div className="roof-surface-mode" aria-label="Roof surface style">
      <button className={surfaceMode === 'imagery' ? 'active' : ''} onClick={() => setSurfaceMode('imagery')} aria-pressed={surfaceMode === 'imagery'}>Imagery</button>
      <button className={surfaceMode === 'clean' ? 'active' : ''} onClick={() => setSurfaceMode('clean')} aria-pressed={surfaceMode === 'clean'}>Clean roof</button>
    </div>
    {props.surfaceLabel.startsWith('CIR') && surfaceMode === 'imagery' && <div className="roof-3d-cir-note"><span className="mono">NIR INTENSITY</span><small>Denoised single-spectrum view</small></div>}
  </div>;
}
