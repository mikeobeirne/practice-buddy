import React, { useEffect, useRef, useState } from "react"
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay"
import RatingButtons from './RatingButtons'

interface Props {
  filename?: string | null
  songId?: number | null
  measureGroupId?: number | null
  className?: string
  onPracticeLogged?: () => void
  onMeasureChange?: (measure: number) => void
}

const MeasureViewer: React.FC<Props> = ({ 
  filename, 
  songId,
  measureGroupId,
  className,
  onPracticeLogged,
  onMeasureChange
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null)
  const [error, setError] = useState<string | null>(null)

  // send a practice event to the backend
  const logPractice = async (rating: string) => {
    if (!songId || !measureGroupId) return
    
    try {
      // Log the practice session
      await fetch("http://localhost:5000/api/practice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          song_id: songId,
          measure_group_id: measureGroupId,
          rating 
        }),
      })
      
      // Notify parent that practice was logged
      onPracticeLogged?.()

      // Get next recommended measure
      const response = await fetch(`http://localhost:5000/api/songs/${songId}/next-measure`)
      if (!response.ok) throw new Error('Failed to get next measure')
      const data = await response.json()
      onMeasureChange?.(data.measure)
    } catch (err) {
      console.error("Failed to log practice or get next measure:", err)
    }
  }

  useEffect(() => {
    return () => {
      if (containerRef.current) containerRef.current.innerHTML = ""
      osmdRef.current = null
    }
  }, [])

  useEffect(() => {
    const load = async () => {
      if (!containerRef.current) return

      // ensure a single OSMD instance exists (create even if no filename)
      if (!osmdRef.current) {
        containerRef.current.innerHTML = ""
        osmdRef.current = new OpenSheetMusicDisplay(containerRef.current, {
          backend: "svg",
          drawCredits: false,
          drawTitle: false,
          drawSubtitle: false,
          drawComposer: false,
          drawLyricist: false,
          drawPartNames: false,
          drawPartAbbreviations: false,
          autoResize: true,
          stretchLastSystemLine: true,     // Makes the measure stretch full width
          spacingFactorSoftmax: 2,         // Lower value = more compact spacing
          drawingParameters: "compact",     // Use compact mode for tighter spacing
          measureNumberInterval: 1,         // Show every measure number
          pageFormat: "Endless"            // Ensures horizontal layout
        } as any)
      }
      const osmd = osmdRef.current!

      setError(null)

      // if no filename yet, we've initialized OSMD and can return early
      if (!filename) return

      try {
        // clear previous render/output before loading new file
        try { osmd.clear && osmd.clear() } catch { /* ignore */ }
        if (containerRef.current) containerRef.current.innerHTML = ""

        const safePath = "/data/" + filename.split("/").map(encodeURIComponent).join("/")
        const resp = await fetch(safePath, { cache: "no-store" })

        const contentType = resp.headers.get("content-type") ?? ""
        if (contentType.includes("text/html")) {
          throw new Error(`Requested ${safePath} returned HTML (file not found).`)
        }

        const buf = await resp.arrayBuffer()
        const u8 = new Uint8Array(buf)
        // detect ZIP header 'PK'
        if (u8[0] === 0x50 && u8[1] === 0x4b) {
          throw new Error("Detected compressed .mxl (zip). Please produce uncompressed .musicxml files or enable client unzip support.")
        }

        if (!resp.ok) throw new Error(`Fetch failed: ${resp.status}`)

        const xml = new TextDecoder().decode(u8)

        await osmd.load(xml)
        await osmd.render()
      } catch (err: any) {
        // eslint-disable-next-line no-console
        console.error("MeasureViewer error:", err)
        setError(String(err?.message ?? err))
        if (containerRef.current) containerRef.current.innerHTML = `<div style="color:darkred">Error loading ${filename}</div>`
      }
    }

    load()
  }, [filename])

  return (
    // fixed-height outer box keeps page layout stable while the OSMD SVG inside can scroll/auto-size
    <div style={{ width: "100%", boxSizing: "border-box" }}>
      <div
        ref={containerRef}
        className={className}  // Now className is defined
        // adjust height as you like (px, %, vh). overflow:auto prevents layout shifts when SVG changes height.
        // use flexbox to horizontally center the rendered SVG(s), keep top alignment
        style={{
          height: 520,
          overflow: "auto",
          width: "50%",
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start",
        }}
      />
      {error && <div style={{ color: "darkred", marginTop: 8 }}>{error}</div>}

      <div style={{ marginTop: 12 }}>
        <RatingButtons onRate={logPractice} />
      </div>
    </div>
  )
}

export default MeasureViewer