import React, { useEffect, useRef, useState } from "react"
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay"
import RatingButtons from './RatingButtons'

interface Props {
  measureGroupId: string | null
  onPracticeLogged: () => void
}

const MeasureViewer: React.FC<Props> = ({ 
  measureGroupId,
  onPracticeLogged,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const osmdRefs = useRef<OpenSheetMusicDisplay[]>([])
  const [error, setError] = useState<string | null>(null)
  const [songId, setSongId] = useState<number | null>(null)

  // Parse measure info from group ID
  const getMeasureInfo = (id: string) => {
    const [folder, measurePart] = id.split('|')
    const match = measurePart.match(/measure(\d+)(?:-(\d+))?/)
    if (!match) return null
    
    const start = parseInt(match[1], 10)
    const end = match[2] ? parseInt(match[2], 10) : start
    return { folder, start, end }
  }

  // Get filenames to load based on measure group
  const getFilesToLoad = (id: string): string[] => {
    const info = getMeasureInfo(id)
    if (!info) return []
    
    if (info.start === info.end) {
      // Single measure
      return [`${info.folder}/measure_${info.start}.musicxml`]
    } else {
      // Measure group
      return [`${info.folder}/measures_${info.start}-${info.end}.musicxml`]
    }
  }

  // Get song ID for measure group
  useEffect(() => {
    const fetchSongId = async () => {
      if (!measureGroupId) return
      const info = getMeasureInfo(measureGroupId)
      if (!info) return
      
      try {
        const resp = await fetch("http://localhost:5000/api/measure-groups")
        if (!resp.ok) throw new Error("Failed to fetch measure groups")
        const groups = await resp.json()
        const group = groups.find((g: any) => g.id === measureGroupId)
        if (group) {
          setSongId(group.song_id)
        }
      } catch (err) {
        console.error("Failed to get song ID:", err)
        setError("Failed to load song information")
      }
    }
    fetchSongId()
  }, [measureGroupId])

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
    } catch (err) {
      console.error("Failed to log practice or get next measure:", err)
    }
  }

  // Load and render measures
  useEffect(() => {
    const load = async () => {
      if (!containerRef.current || !measureGroupId) return

      try {
        // Clear previous render
        containerRef.current.innerHTML = ""
        osmdRefs.current = []

        const measureFiles = getFilesToLoad(measureGroupId)

        // Create a container for each measure
        const measureContainers = measureFiles.map((_, i) => {
          const div = document.createElement('div')
          div.style.flex = '1'
          div.style.minWidth = '300px'
          div.style.margin = '0 4px'
          containerRef.current!.appendChild(div)
          return div
        })

        // Load each measure in its own OSMD instance
        await Promise.all(measureFiles.map(async (file, i) => {
          const osmd = new OpenSheetMusicDisplay(measureContainers[i], {
            backend: "svg",
            drawCredits: false,
            drawTitle: false,
            drawSubtitle: false,
            drawComposer: false,
            drawLyricist: false,
            drawPartNames: false,
            drawPartAbbreviations: false,
            autoResize: true,
            //stretchLastSystemLine: true,
            spacingFactorSoftmax: 2,
            drawingParameters: "compact",
            measureNumberInterval: 1,
            pageFormat: "Endless"
          } as any)

          osmdRefs.current.push(osmd)

          const safePath = "/data/" + file.split("/").map(encodeURIComponent).join("/")
          const resp = await fetch(safePath, { cache: "no-store" })
          if (!resp.ok) throw new Error(`Failed to load ${safePath}`)
          const buf = await resp.arrayBuffer()
          const xml = new TextDecoder().decode(buf)

          await osmd.load(xml)
          await osmd.render()
        }))

      } catch (err: any) {
        console.error("MeasureViewer error:", err)
        setError(String(err?.message ?? err))
      }
    }

    load()
  }, [measureGroupId])

  return (
    // fixed-height outer box keeps page layout stable while the OSMD SVG inside can scroll/auto-size
    <div style={{ width: "100%", boxSizing: "border-box" }}>
      <div
        ref={containerRef}
        // adjust height as you like (px, %, vh). overflow:auto prevents layout shifts when SVG changes height.
        // use flexbox to horizontally center the rendered SVG(s), keep top alignment
        style={{
          height: 520,
          overflow: "auto",
          width: "100%",
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start",
          // Add horizontal scroll if measures overflow
          overflowX: "auto"
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