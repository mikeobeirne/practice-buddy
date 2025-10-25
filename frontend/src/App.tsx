import React, { Suspense, use, useMemo } from "react"
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
  id: string;  
  song_id: number
  start_measure: number
  end_measure: number
}

interface MeasureRecommendation {
  id: string;  
  stats: {
    category: 'unlearned' | 'challenging' | 'proficient';
    best_rating: number;
    practice_count: number;
    last_practiced: string | null;
    due_date: string | null;
    is_group: boolean;
  };
}

// Place this before dataPromise
async function fetchRecommendation(songId: number): Promise<MeasureRecommendation | null> {
  try {
    const response = await fetch(`http://localhost:5000/api/songs/${songId}/next-measure`)
    if (!response.ok) throw new Error('Failed to get next measure')
    return await response.json()
  } catch (err) {
    console.error('Failed to get next measure:', err)
    return null
  }
}

// Create a promise that loads the initial data
const dataPromise = (async () => {
  const [songsResp, groupsResp] = await Promise.all([
    fetch("http://localhost:5000/api/songs"),
    fetch("http://localhost:5000/api/measure-groups")
  ])
  const songs = await songsResp.json()
  const measureGroups = await groupsResp.json()
  const initialSongId = songs[0]?.id || 0
  
  // Get initial recommendation if we have a song
  const initialRecommendation = await fetchRecommendation(initialSongId);
  console.log("initialRecommendation", initialRecommendation);

  return { 
    songs, 
    measureGroups, 
    initialSongId,
    initialRecommendation 
  }
})()

// Main content component uses the 'use' hook to handle async data
function AppContent() {
  const { songs, measureGroups, initialSongId, initialRecommendation } = use(dataPromise)
  
  return (
    <App 
      initialSongs={songs} 
      initialMeasureGroups={measureGroups} 
      initialSongId={initialSongId}
      initialRecommendation={initialRecommendation}
    />
  )
}

// Main App component now takes initial data as props
function App({ 
  initialSongs, 
  initialSongId,
  initialRecommendation
}: { 
  initialSongs: Song[]
  initialMeasureGroups: MeasureGroup[]
  initialSongId: number
  initialRecommendation: MeasureRecommendation | null
}) {
  const [songs] = React.useState(initialSongs)
  const [selectedSongId, setSelectedSongId] = React.useState(initialSongId)
  const [recommendation, setRecommendation] = React.useState(initialRecommendation)


  const fetchNextMeasure = async (songId: number) => {
    const data = await fetchRecommendation(songId)
    if (data) {
      setRecommendation(data)
    }
  }

  const selectSong = (id: number) => {  
    setSelectedSongId(id)
    fetchNextMeasure(id)  
  }

  // Also add useEffect to fetch next measure when song is initially loaded
  React.useEffect(() => {
    fetchNextMeasure(selectedSongId)
  }, [selectedSongId])
  
  const getMeasureInfo = (id: string) => {
    const [folder, measurePart] = id.split('|')
    const match = measurePart.match(/measure(\d+)(?:-(\d+))?/)
    if (!match) return null
    
    const start = parseInt(match[1], 10)
    const end = match[2] ? parseInt(match[2], 10) : start
    return { folder, start, end }
  }

  const measureInfo = recommendation ? getMeasureInfo(recommendation.id) : null

  // Add currentMeasureGroup derived from measureInfo
  const currentMeasureGroup = useMemo(() => {
    if (!recommendation || !measureInfo) return null;
    return {
      id: recommendation.id,
      start_measure: measureInfo.start,
      end_measure: measureInfo.end,
      folder: measureInfo.folder
    };
  }, [recommendation, measureInfo]);

  const getRatingText = (rating: number): string => {
    switch(rating) {
      case 0: return "not practiced"
      case 1: return "hard"
      case 2: return "medium"
      case 3: return "easy"
      default: return "unknown"
    }
  }

    console.log(currentMeasureGroup);
    console.log(currentMeasureGroup?.id);
  return (
    <div style={{ padding: 16 }}>
      <h1>Practice Buddy — Measure Viewer</h1>

      <section style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
          <select 
            value={selectedSongId} 
            onChange={e => selectSong(Number(e.target.value))} 
            style={{ flex: 1 }}
          >
            {songs.map(s => (
              <option key={s.id} value={s.id}>{s.title}</option>
            ))}
          </select>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <div style={{ minWidth: 220, textAlign: "center" }}>
            </div>
          </div>
        </div>

        {recommendation && measureInfo && (
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
              {measureInfo.end > measureInfo.start ? (
                <span>Measures {measureInfo.start}-{measureInfo.end}</span>
              ) : (
                <span>Measure {measureInfo.start}</span>
              )}
              {' '}({recommendation.stats.category})
            </div>
            <div>
              Best rating: {getRatingText(recommendation.stats.best_rating)}
              {recommendation.stats.practice_count > 0 && (
                <>
                  {' • '}Practiced {recommendation.stats.practice_count} times
                  {recommendation.stats.last_practiced && (
                    <>
                      {' • '}Last practiced {new Date(recommendation.stats.last_practiced).toLocaleDateString()}
                    </>
                  )}
                  {recommendation.stats.due_date && (
                    <>
                      {' • '}Due {new Date(recommendation.stats.due_date).toLocaleDateString()}
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        <div style={{ border: "1px solid #ddd", padding: 8 }}>
          <MeasureViewer 
            measureGroupId={currentMeasureGroup?.id ?? null}
            onPracticeLogged={() => {
              fetchNextMeasure(selectedSongId)
            }}
          />
        </div>
      </section>

      <section style={{ marginTop: 32 }}>
        <PracticeSessions />
      </section>
    </div>
  )
}

// Wrap the async component in Suspense
export default function AppWrapper() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <AppContent />
    </Suspense>
  )
}
