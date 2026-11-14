import { useEffect, useRef, useState } from 'react';

type InfraredSurfaceProps = {
  src: string;
  alt: string;
  onError?: () => void;
};

const mix = (start: number, end: number, amount: number) => Math.round(start + (end - start) * amount);
const smoothstep = (value: number) => value * value * (3 - 2 * value);

export default function InfraredSurface({ src, alt, onError }: InfraredSurfaceProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const onErrorRef = useRef(onError);
  const [ready, setReady] = useState(false);
  useEffect(() => { onErrorRef.current = onError; }, [onError]);

  useEffect(() => {
    let cancelled = false;
    setReady(false);
    const image = new Image();
    image.decoding = 'async';
    image.onload = () => {
      if (cancelled || !canvasRef.current) return;
      const width = image.naturalWidth;
      const height = image.naturalHeight;
      const canvas = canvasRef.current;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context || !width || !height) return onErrorRef.current?.();
      canvas.width = width;
      canvas.height = height;
      context.drawImage(image, 0, 0);
      const pixels = context.getImageData(0, 0, width, height);
      const horizontal = new Float32Array(width * height);
      const infrared = new Uint8Array(width * height);

      for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) {
        let total = 0;
        let samples = 0;
        for (let offset = -1; offset <= 1; offset += 1) {
          const sampleX = Math.max(0, Math.min(width - 1, x + offset));
          total += pixels.data[(y * width + sampleX) * 4];
          samples += 1;
        }
        horizontal[y * width + x] = total / samples;
      }

      const histogram = new Uint32Array(256);
      for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) {
        let total = 0;
        let samples = 0;
        for (let offset = -1; offset <= 1; offset += 1) {
          const sampleY = Math.max(0, Math.min(height - 1, y + offset));
          total += horizontal[sampleY * width + x];
          samples += 1;
        }
        const value = Math.round(total / samples);
        infrared[y * width + x] = value;
        histogram[value] += 1;
      }

      const percentile = (fraction: number) => {
        const target = width * height * fraction;
        let total = 0;
        for (let value = 0; value < histogram.length; value += 1) {
          total += histogram[value];
          if (total >= target) return value;
        }
        return 255;
      };
      const low = percentile(.04);
      const high = Math.max(low + 1, percentile(.96));
      const lowColor = [248, 245, 240];
      const middleColor = [238, 119, 42];
      const highColor = [105, 34, 9];

      for (let index = 0; index < infrared.length; index += 1) {
        const normalized = smoothstep(Math.max(0, Math.min(1, (infrared[index] - low) / (high - low))));
        const firstHalf = normalized <= .62;
        const amount = firstHalf ? normalized / .62 : (normalized - .62) / .38;
        const from = firstHalf ? lowColor : middleColor;
        const to = firstHalf ? middleColor : highColor;
        pixels.data[index * 4] = mix(from[0], to[0], amount);
        pixels.data[index * 4 + 1] = mix(from[1], to[1], amount);
        pixels.data[index * 4 + 2] = mix(from[2], to[2], amount);
        pixels.data[index * 4 + 3] = 255;
      }

      context.putImageData(pixels, 0, 0);
      if (!cancelled) setReady(true);
    };
    image.onerror = () => { if (!cancelled) onErrorRef.current?.(); };
    image.src = src;
    return () => { cancelled = true; };
  }, [src]);

  return <canvas ref={canvasRef} className={ready ? 'roof-infrared-surface ready' : 'roof-infrared-surface'} role="img" aria-label={alt} />;
}
