import React, { useEffect, useRef, useState } from "react"
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay"

interface Props {
  filename?: string | null
  className?: string
}

const MeasureViewer: React.FC<Props> = ({ filename, className }) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null)
  const [error, setError] = useState<string | null>(null)

  // send a practice event to the backend
  const logPractice = async (difficulty: string) => {
    if (!filename) return
    const m = filename.match(/_measure_(\d+)(?:\.musicxml|\.mxl)?$/i)
    const measure = m ? parseInt(m[1], 10) : null
    try {
      await fetch("http://localhost:5000/api/practice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, measure, difficulty }),
      })
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Failed to log practice:", err)
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
        // Options: hide credits/title/composer/arranger metadata that OSMD would render
        // Also provide an onXMLRead fallback to strip any <credit> blocks if present.
        osmdRef.current = new OpenSheetMusicDisplay(containerRef.current, {
          backend: "svg",
          drawCredits: false,
          drawTitle: false,
          drawSubtitle: false,
          drawComposer: false,
          drawLyricist: false,
          drawPartNames: false,
          drawPartAbbreviations: false,
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
        className={className}
        // adjust height as you like (px, %, vh). overflow:auto prevents layout shifts when SVG changes height.
        // use flexbox to horizontally center the rendered SVG(s), keep top alignment
        style={{
          height: 520,
          overflow: "auto",
          width: "100%",
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start",
        }}
      />
      {error && <div style={{ color: "darkred", marginTop: 8 }}>{error}</div>}

      {/* rating / action buttons under the rendering */}
      <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 12 }}>
        <button type="button" onClick={() => logPractice("Easy")}>Easy</button>
        <button type="button" onClick={() => logPractice("Medium")}>Medium</button>
        <button type="button" onClick={() => logPractice("Hard")}>Hard</button>
        <button type="button" onClick={() => logPractice("Snooze")}>Snooze</button>
      </div>
    </div>
  )
}

export default MeasureViewer