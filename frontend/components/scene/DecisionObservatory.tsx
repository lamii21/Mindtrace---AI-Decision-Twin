"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Line, MeshTransmissionMaterial } from "@react-three/drei";
import { Suspense, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { ALL_TWINS, type TwinDefinition } from "@/lib/twins";
import { useIsMobile } from "@/lib/useIsMobile";
import { useReducedMotion } from "@/lib/useReducedMotion";

interface ObservatoryProps {
  /** Interactive mode: clicking an orbiting twin calls `onSelectTwin`. Landing-page use omits this. */
  activeTwinId?: string | null;
  onSelectTwin?: (id: string) => void;
  /** Per-twin score in [-1,1], used to vary orbit radius/brightness when available (app use). */
  scores?: Record<string, number>;
  interactive?: boolean;
}

const ORBIT_RADIUS = 2.6;

function CentralCore({ reduced, simplified }: { reduced: boolean; simplified: boolean }) {
  const mesh = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (mesh.current && !reduced) {
      mesh.current.rotation.y += delta * 0.08;
      mesh.current.rotation.x += delta * 0.03;
    }
  });
  return (
    <mesh ref={mesh}>
      <icosahedronGeometry args={[1.05, 2]} />
      {simplified ? (
        <meshPhysicalMaterial
          color="#c9bdf0"
          roughness={0.15}
          metalness={0.05}
          transparent
          opacity={0.55}
          emissive="#8d78e0"
          emissiveIntensity={0.2}
        />
      ) : (
        <MeshTransmissionMaterial
          thickness={0.6}
          roughness={0.08}
          transmission={1}
          ior={1.2}
          chromaticAberration={0.02}
          backside
          color="#c9bdf0"
          distortion={0.1}
          distortionScale={0.2}
          temporalDistortion={0.05}
        />
      )}
    </mesh>
  );
}

function OrbitNode({
  twin,
  index,
  total,
  active,
  interactive,
  onSelect,
  scoreRadius,
  reduced,
}: {
  twin: TwinDefinition;
  index: number;
  total: number;
  active: boolean;
  interactive: boolean;
  onSelect?: (id: string) => void;
  scoreRadius: number;
  reduced: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const [hovered, setHovered] = useState(false);
  const baseAngle = (index / total) * Math.PI * 2;
  const tilt = ((index % 2) * 2 - 1) * 0.35;

  useFrame(({ clock }) => {
    if (!group.current) return;
    const t = (reduced ? 0 : clock.getElapsedTime() * 0.12) + baseAngle;
    const r = scoreRadius;
    group.current.position.set(
      Math.cos(t) * r,
      Math.sin(t * 0.6 + index) * 0.5 * Math.sin(tilt + 0.6),
      Math.sin(t) * r,
    );
  });

  const scale = active ? 1.35 : hovered ? 1.15 : 1;

  return (
    <group ref={group}>
      <mesh
        scale={scale}
        onPointerOver={() => interactive && setHovered(true)}
        onPointerOut={() => interactive && setHovered(false)}
        onClick={() => interactive && onSelect?.(twin.id)}
      >
        <octahedronGeometry args={[0.26, 0]} />
        <meshStandardMaterial
          color={twin.accent}
          emissive={twin.accent}
          emissiveIntensity={active ? 1.4 : hovered ? 0.9 : 0.45}
          roughness={0.3}
          metalness={0.1}
        />
      </mesh>
      <pointLight color={twin.accent} intensity={active ? 2.2 : 0.6} distance={3} />
    </group>
  );
}

function ConnectionLines({ scoreRadius }: { scoreRadius: Record<string, number> }) {
  return (
    <>
      {ALL_TWINS.slice(1).map((twin) => (
        <Line
          key={twin.id}
          points={[
            [0, 0, 0],
            [scoreRadius[twin.id] ?? ORBIT_RADIUS, 0, 0],
          ]}
          color={twin.accent}
          transparent
          opacity={0.08}
          lineWidth={1}
        />
      ))}
    </>
  );
}

function Particles({ reduced, count }: { reduced: boolean; count: number }) {
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = 1.6 + Math.random() * 2.2;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      arr[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      arr[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.5;
      arr[i * 3 + 2] = r * Math.cos(phi);
    }
    return arr;
  }, [count]);
  const points = useRef<THREE.Points>(null);
  useFrame((_, delta) => {
    if (points.current && !reduced) points.current.rotation.y += delta * 0.015;
  });
  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.02} color="#e4ddcd" transparent opacity={0.5} sizeAttenuation />
    </points>
  );
}

function PointerParallax({
  children,
  reduced,
}: {
  children: React.ReactNode;
  reduced: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const { viewport } = useThree();
  useFrame((state) => {
    if (!group.current || reduced) return;
    const x = (state.pointer.x * viewport.width) / 40;
    const y = (state.pointer.y * viewport.height) / 40;
    group.current.rotation.y = THREE.MathUtils.lerp(group.current.rotation.y, x, 0.04);
    group.current.rotation.x = THREE.MathUtils.lerp(group.current.rotation.x, -y, 0.04);
  });
  return <group ref={group}>{children}</group>;
}

function Scene({ activeTwinId, onSelectTwin, scores, interactive = false }: ObservatoryProps) {
  const reduced = useReducedMotion();
  const isMobile = useIsMobile();
  const scoreRadius = useMemo(() => {
    const out: Record<string, number> = {};
    for (const twin of ALL_TWINS.slice(1)) {
      const score = scores?.[twin.id];
      out[twin.id] = score === undefined ? ORBIT_RADIUS : ORBIT_RADIUS + score * 0.9;
    }
    return out;
  }, [scores]);

  return (
    <>
      <ambientLight intensity={0.25} />
      <directionalLight position={[4, 6, 4]} intensity={0.6} color="#faf8f3" />
      <pointLight position={[-4, -3, -4]} intensity={0.4} color="#3b9bff" />
      <PointerParallax reduced={reduced}>
        <CentralCore reduced={reduced} simplified={isMobile} />
        <ConnectionLines scoreRadius={scoreRadius} />
        <Particles reduced={reduced} count={isMobile ? 24 : 60} />
        {ALL_TWINS.slice(1).map((twin, i) => (
          <OrbitNode
            key={twin.id}
            twin={twin}
            index={i}
            total={ALL_TWINS.length - 1}
            active={activeTwinId === twin.id}
            interactive={interactive}
            onSelect={onSelectTwin}
            scoreRadius={scoreRadius[twin.id] ?? ORBIT_RADIUS}
            reduced={reduced}
          />
        ))}
      </PointerParallax>
    </>
  );
}

/** Flat, no-WebGL fallback - never a blank hole where the signature piece should be. */
function StaticFallback() {
  return (
    <div className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-3xl bg-atmosphere">
      <div className="h-40 w-40 rounded-full border border-lavender-400/30 bg-gradient-to-br from-lavender-500/20 to-electric-500/10 blur-[1px]" />
      {ALL_TWINS.slice(1).map((twin, i) => (
        <span
          key={twin.id}
          className="absolute h-3 w-3 rounded-full"
          style={{
            background: twin.accent,
            top: `${50 + 32 * Math.sin((i / 4) * Math.PI * 2)}%`,
            left: `${50 + 32 * Math.cos((i / 4) * Math.PI * 2)}%`,
            boxShadow: `0 0 16px ${twin.accent}`,
          }}
        />
      ))}
    </div>
  );
}

export function DecisionObservatory(props: ObservatoryProps) {
  const [webglFailed, setWebglFailed] = useState(false);
  const isMobile = useIsMobile();

  if (webglFailed) return <StaticFallback />;

  return (
    <div className="h-full w-full">
      <Canvas
        camera={{ position: [0, 0, 6.2], fov: 42 }}
        dpr={isMobile ? 1 : [1, 1.75]}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener(
            "webglcontextlost",
            (e) => {
              e.preventDefault();
              setWebglFailed(true);
            },
            false,
          );
        }}
        fallback={<StaticFallback />}
      >
        <Suspense fallback={null}>
          <Scene {...props} />
        </Suspense>
      </Canvas>
    </div>
  );
}
