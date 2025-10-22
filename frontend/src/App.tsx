import React, { useMemo, useState } from "react"
import "./App.css"
import MeasureViewer from "./components/MeasureViewer"

type SongSpec = {
  id: string
  folder: string
  base: string
  measures: number
  display?: string
}

function App() {
  // hard-coded songs with the exact string format you requested
  const songs: SongSpec[] = [
    {
      id: "alicia",
      folder: "alicia",
      base: "alicia-clair-obscur-expedition-33-main-theme-piano-solo",
      measures: 69,
      display: "Alicia — Clair Obscur (69 measures)",
    },
    {
      id: "brooke",
      folder: "",
      base: "BrookeWestSample",
      measures: 1,
      display: "Brooke West Sample (single file)",
    },
    // add more songs here using the same pattern
  ]

  const songMap = useMemo(() => {
    const m = new Map<string, SongSpec>()
    for (const s of songs) m.set(s.id, s)
    return m
  }, [songs])

  const [selectedSongId, setSelectedSongId] = useState<string>("")
  const selectedSong = selectedSongId ? songMap.get(selectedSongId) ?? null : null
  const [measureIndex, setMeasureIndex] = useState<number>(1)

  // when song changes, reset measure index to 1
  const selectSong = (id: string) => {
    setSelectedSongId(id)
    setMeasureIndex(1)
  }

  const prev = () => {
    if (!selectedSong) return
    setMeasureIndex((i) => {
      const next = i - 1
      return next < 1 ? selectedSong.measures : next
    })
  }

  const next = () => {
    if (!selectedSong) return
    setMeasureIndex((i) => {
      const next = i + 1
      return next > selectedSong.measures ? 1 : next
    })
  }

  // construct filename using the hard-coded pattern:
  // if folder is provided: `${folder}/${base}_measure_${n}.musicxml`
  // otherwise: `${base}_measure_${n}.musicxml` (or single file if measures === 1)
  const currentFilename = useMemo(() => {
    if (!selectedSong) return null
    if (selectedSong.measures <= 1) {
      // single-file song; try .musicxml first, fallback to .mxl
      return `${selectedSong.folder ? selectedSong.folder + "/" : ""}${selectedSong.base}.musicxml`
    }
    return `${selectedSong.folder ? selectedSong.folder + "/" : ""}${selectedSong.base}_measure_${measureIndex}.musicxml`
  }, [selectedSong, measureIndex])

  return (
    <div style={{ padding: 16 }}>
      <h1>Practice Buddy — Measure Viewer</h1>

      <section style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
          <select value={selectedSongId} onChange={(e) => selectSong(e.target.value)} style={{ flex: 1 }}>
            <option value="">-- choose a song --</option>
            {songs.map((s) => (
              <option key={s.id} value={s.id}>
                {s.display ?? s.base}
              </option>
            ))}
          </select>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button onClick={prev} disabled={!selectedSong || selectedSong.measures <= 1}>
              ◀
            </button>

            <div style={{ minWidth: 220, textAlign: "center" }}>
              {selectedSong ? (
                selectedSong.measures > 1 ? (
                  <span>
                    {measureIndex} / {selectedSong.measures} — {selectedSong.base}
                  </span>
                ) : (
                  <span>{selectedSong.base} (single file)</span>
                )
              ) : (
                <span style={{ color: "#666" }}>Select a song to see measures</span>
              )}
            </div>

            <button onClick={next} disabled={!selectedSong || selectedSong.measures <= 1}>
              ▶
            </button>
          </div>
        </div>

        <div style={{ border: "1px solid #ddd", padding: 8 }}>
          <MeasureViewer filename={currentFilename || null} />
          {!currentFilename && <div style={{ color: "#666", marginTop: 8 }}>Select a song and use the arrows to cycle measures.</div>}
        </div>
      </section>
    </div>
  )
}

export default App
