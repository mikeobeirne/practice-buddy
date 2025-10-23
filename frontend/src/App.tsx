import React, { useEffect, useMemo, useState } from "react"
import "./App.css"
import MeasureViewer from "./components/MeasureViewer"
import PracticeSessions from "./components/PracticeSessions"

// types for our API responses
interface Song {
  id: number
  title: string
  source_file: string
  total_measures: number
}

interface MeasureGroup {
  id: number
  song_id: number
  start_measure: number
  end_measure: number
}

interface MeasureRecommendation {
  measure: number;
  stats: {
    category: 'unlearned' | 'challenging' | 'proficient';
    best_rating: number;
    practice_count: number;
    last_practiced: string | null;
    due_date: string | null;
  };
}

function App() {
  const [songs, setSongs] = useState<Song[]>([])
  const [measureGroups, setMeasureGroups] = useState<MeasureGroup[]>([])
  const [selectedSongId, setSelectedSongId] = useState<number | null>(null)
  const [measureIndex, setMeasureIndex] = useState<number>(1)
  const [recommendation, setRecommendation] = useState<MeasureRecommendation | null>(null)

  // fetch songs and measure groups on mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [songsResp, groupsResp] = await Promise.all([
          fetch("http://localhost:5000/api/songs"),
          fetch("http://localhost:5000/api/measure-groups")
        ])
        const songsData = await songsResp.json()
        const groupsData = await groupsResp.json()
        setSongs(songsData)
        setMeasureGroups(groupsData)
        // Select first song by default if available
        if (songsData.length > 0) {
          setSelectedSongId(songsData[0].id)
        }
      } catch (err) {
        console.error("Failed to fetch data:", err)
      }
    }
    fetchData()
  }, [])

  // selected song details
  const selectedSong = selectedSongId ? songs.find(s => s.id === selectedSongId) : null

  // find measure group ID for current song+measure
  const currentMeasureGroup = useMemo(() => {
    if (!selectedSongId || !measureIndex) return null
    return measureGroups.find(mg => 
      mg.song_id === selectedSongId && 
      mg.start_measure === measureIndex && 
      mg.end_measure === measureIndex
    ) || null
  }, [selectedSongId, measureIndex, measureGroups])

  // construct filename for current selection
  const currentFilename = useMemo(() => {
    if (!selectedSong) return null
    // Get normalized folder name from source_file
    const songFolder = selectedSong.source_file.split("/")[0]
    // Use simplified measure filename format
    return `${songFolder}/measure_${measureIndex}.musicxml`
  }, [selectedSong, measureIndex])

  const selectSong = (id: number | null) => {
    setSelectedSongId(id)
    setMeasureIndex(1)
  }

  const prev = () => {
    if (!selectedSong) return
    setMeasureIndex(i => {
      const next = i - 1
      return next < 1 ? selectedSong.total_measures : next
    })
  }

  // Modify the fetchNextMeasure function to store recommendation
  const fetchNextMeasure = async (songId: number) => {
    try {
      const response = await fetch(`http://localhost:5000/api/songs/${songId}/next-measure`)
      if (!response.ok) throw new Error('Failed to get next measure')
      const data: MeasureRecommendation = await response.json()
      setMeasureIndex(data.measure)
      setRecommendation(data)
    } catch (err) {
      console.error('Failed to get next measure:', err)
    }
  }

  // Remove autoAdvance state and modify the next function
  const next = () => {
    if (!selectedSong) return
    setMeasureIndex(prev => 
      prev < selectedSong.total_measures ? prev + 1 : prev
    )
  }

  const getRatingText = (rating: number): string => {
    switch(rating) {
      case 0: return "not practiced"
      case 1: return "hard"
      case 2: return "medium"
      case 3: return "easy"
      default: return "unknown"
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <h1>Practice Buddy — Measure Viewer</h1>

      <section style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
          <select 
            value={selectedSongId || ""} 
            onChange={e => selectSong(e.target.value ? Number(e.target.value) : null)} 
            style={{ flex: 1 }}
          >
            <option value="">-- choose a song --</option>
            {songs.map(s => (
              <option key={s.id} value={s.id}>{s.title}</option>
            ))}
          </select>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button onClick={prev} disabled={!selectedSong}>◀</button>
            <div style={{ minWidth: 220, textAlign: "center" }}>
              {selectedSong ? (
                <span>
                  {measureIndex} / {selectedSong.total_measures} — {selectedSong.title}
                </span>
              ) : (
                <span style={{ color: "#666" }}>Select a song to see measures</span>
              )}
            </div>
            <button onClick={next} disabled={!selectedSong}>▶</button>
          </div>
        </div>

        <div style={{ border: "1px solid #ddd", padding: 8 }}>
          <MeasureViewer 
            filename={currentFilename}
            songId={selectedSongId}
            measureGroupId={currentMeasureGroup?.id}
            onMeasureChange={setMeasureIndex}
          />
        </div>
      </section>

      {recommendation && recommendation.measure === measureIndex && (
        <div style={{ 
          marginTop: 8, 
          padding: 12,
          borderRadius: 4,
          backgroundColor: recommendation.stats.category === 'unlearned' ? '#fff3e0' :
                          recommendation.stats.category === 'challenging' ? '#e3f2fd' :
                          '#e8f5e9',
          fontSize: '0.9em'
        }}>
          <div style={{ fontWeight: 'bold', marginBottom: 4 }}>
            Measure {recommendation.measure} ({recommendation.stats.category})
          </div>
          <div>
            Best rating: {getRatingText(recommendation.stats.best_rating)}
            {recommendation.stats.practice_count > 0 && (
              <>
                {' • '}Practiced {recommendation.stats.practice_count} times
                {' • '}Last practiced {new Date(recommendation.stats.last_practiced!).toLocaleDateString()}
                {' • '}Due {new Date(recommendation.stats.due_date!).toLocaleDateString()}
              </>
            )}
          </div>
        </div>
      )}

      <section style={{ marginTop: 32 }}>
        <PracticeSessions />
      </section>
    </div>
  )
}

export default App
