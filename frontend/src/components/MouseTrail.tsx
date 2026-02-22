"use client";

import { useEffect, useRef } from "react";

const BRAND_COLORS = ["#00D4FF", "#9B6DFF", "#00D4FF", "#7C3AED", "#22D3EE"];

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  alpha: number;
  size: number;
  color: string;
  shape: "circle" | "star";
}

function drawStar(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  const spikes = 5;
  const innerR = r * 0.45;
  let rot = (Math.PI / 2) * 3;
  const step = Math.PI / spikes;
  ctx.beginPath();
  ctx.moveTo(cx, cy - r);
  for (let i = 0; i < spikes; i++) {
    ctx.lineTo(cx + Math.cos(rot) * r, cy + Math.sin(rot) * r);
    rot += step;
    ctx.lineTo(cx + Math.cos(rot) * innerR, cy + Math.sin(rot) * innerR);
    rot += step;
  }
  ctx.lineTo(cx, cy - r);
  ctx.closePath();
}

export function MouseTrail() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const rafRef = useRef<number>(0);
  const lastPos = useRef({ x: -9999, y: -9999 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const spawnParticles = (x: number, y: number, count: number) => {
      for (let i = 0; i < count; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = Math.random() * 3.5 + 1;
        particlesRef.current.push({
          x,
          y,
          vx: Math.cos(angle) * speed * 0.6 + (Math.random() - 0.5) * 1.5,
          vy: Math.sin(angle) * speed * 0.6 - Math.random() * 2.5,
          alpha: 1,
          size: Math.random() * 9 + 4,
          color: BRAND_COLORS[Math.floor(Math.random() * BRAND_COLORS.length)],
          shape: Math.random() > 0.55 ? "star" : "circle",
        });
      }
    };

    const onMove = (e: MouseEvent) => {
      const dx = e.clientX - lastPos.current.x;
      const dy = e.clientY - lastPos.current.y;
      const speed = Math.sqrt(dx * dx + dy * dy);
      lastPos.current = { x: e.clientX, y: e.clientY };
      // more particles the faster you move
      const count = Math.min(Math.floor(speed / 4) + 2, 8);
      spawnParticles(e.clientX, e.clientY, count);
    };

    window.addEventListener("mousemove", onMove);

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particlesRef.current = particlesRef.current.filter((p) => p.alpha > 0.02);

      for (const p of particlesRef.current) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.08; // gravity
        p.vx *= 0.98; // drag
        p.alpha *= 0.92;
        p.size *= 0.97;

        const hex = Math.floor(p.alpha * 255)
          .toString(16)
          .padStart(2, "0");
        ctx.fillStyle = p.color + hex;

        if (p.shape === "star") {
          drawStar(ctx, p.x, p.y, p.size);
          ctx.fill();
        } else {
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      rafRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0 z-50"
      aria-hidden="true"
    />
  );
}
