import { useEffect, useRef, useState } from "react"

function reducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches
  } catch {
    return false
  }
}

/** Valeur qui « monte » jusqu'au chiffre exact à l'affichage (effet visuel uniquement : la valeur finale est celle de l'API). */
export function CountUp({ value, format, duration = 900 }: { value: number | null | undefined; format: (v: number) => string; duration?: number }) {
  const [shown, setShown] = useState<number | null>(value ?? null)
  const from = useRef(0)
  useEffect(() => {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      setShown(value ?? null)
      return
    }
    if (reducedMotion()) {
      setShown(value)
      return
    }
    const start = performance.now()
    const a = from.current
    let raf = 0
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / duration)
      const e = 1 - Math.pow(1 - k, 3)
      setShown(k >= 1 ? value : a + (value - a) * e)
      if (k < 1) raf = requestAnimationFrame(tick)
      else from.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])
  return <span className="tabular-nums">{shown === null ? "—" : format(shown)}</span>
}
