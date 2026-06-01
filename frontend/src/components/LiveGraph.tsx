import { useEffect, useRef } from 'react'

interface LiveGraphProps {
  label: string
  color?: string
  speed?: number
  active?: boolean
}

export default function LiveGraph({
  label,
  color = '#ffffff',
  speed = 0.05,
  active = true,
}: LiveGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const dataRef = useRef<number[]>(new Array(50).fill(0.5))
  const timeRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    let animId: number

    const resize = () => {
      canvas.width = canvas.parentElement!.offsetWidth
      canvas.height = canvas.parentElement!.offsetHeight
    }
    resize()
    window.addEventListener('resize', resize)

    const draw = () => {
      animId = requestAnimationFrame(draw)

      if (active) {
        timeRef.current += speed
        const noise = (Math.random() - 0.5) * 0.1
        const trend = Math.sin(timeRef.current) * 0.3 + 0.5
        const newVal = Math.max(0.1, Math.min(0.9, trend + noise))
        dataRef.current.push(newVal)
        dataRef.current.shift()
      }

      const data = dataRef.current
      ctx.fillStyle = '#050505'
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      // Midline
      ctx.strokeStyle = '#1a1a1a'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(0, canvas.height / 2)
      ctx.lineTo(canvas.width, canvas.height / 2)
      ctx.stroke()

      // Data line
      ctx.strokeStyle = color
      ctx.lineWidth = 1.5
      ctx.beginPath()
      const step = canvas.width / (data.length - 1)
      for (let i = 0; i < data.length; i++) {
        const x = i * step
        const y = canvas.height - data[i] * canvas.height
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.stroke()

      // End dot
      const lastY = canvas.height - data[data.length - 1] * canvas.height
      ctx.beginPath()
      ctx.arc(canvas.width - 2, lastY, 2, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()
    }
    draw()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
    }
  }, [color, speed, active])

  return (
    <div className="graph-box">
      <span className="graph-label">{label}</span>
      <canvas ref={canvasRef} />
    </div>
  )
}
