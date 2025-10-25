import React, { useEffect, useState } from 'react';

interface PracticeSession {
  id: number;
  song_id: number;
  song_title: string;
  measure_group_id: number;
  start_measure: number;
  end_measure: number;
  practiced_at: string;
  rating: 'easy' | 'medium' | 'hard' | 'snooze';
  duration_seconds?: number;
  notes?: string;
}

const PracticeSessions: React.FC = () => {
  const [sessions, setSessions] = useState<PracticeSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  const fetchSessions = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/practice-sessions');
      if (!response.ok) throw new Error('Failed to fetch sessions');
      const data = await response.json();
      setSessions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 5000);
    
    // Clean up interval on unmount
    return () => clearInterval(interval);
  }, []);

  const handleClearHistory = async () => {
    if (!window.confirm('Are you sure you want to clear all practice history? This cannot be undone.')) {
      return;
    }

    setClearing(true);
    try {
      const response = await fetch('http://localhost:5000/api/practice-sessions', {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to clear history');
      setSessions([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear history');
    } finally {
      setClearing(false);
    }
  };

  if (loading) return <div>Loading sessions...</div>;
  if (error) return <div>Error: {error}</div>;
  // console.log(sessions);

  return (
    <div className="practice-sessions">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2>Practice History</h2>
        <button 
          onClick={handleClearHistory}
          disabled={clearing || sessions.length === 0}
          style={{
            backgroundColor: '#ff4444',
            color: 'white',
            border: 'none',
            padding: '8px 16px',
            borderRadius: 4,
            cursor: clearing ? 'not-allowed' : 'pointer',
            opacity: clearing || sessions.length === 0 ? 0.5 : 1
          }}
        >
          {clearing ? 'Clearing...' : 'Clear History'}
        </button>
      </div>

      {sessions.length === 0 ? (
        <div>No practice sessions recorded yet.</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th>When</th>
              <th>Song</th>
              <th>Measure</th>
              <th>Rating</th>
              <th>Duration</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map(session => (
              <tr key={session.id} style={{ borderTop: '1px solid #ddd' }}>
                <td>{new Date(session.practiced_at).toLocaleString()}</td>
                <td>{session.song_title}</td>
                <td>
                  {session.start_measure === session.end_measure 
                    ? `M.${session.start_measure}`
                    : `M.${session.start_measure}-${session.end_measure}`
                  }
                </td>
                <td>{session.rating}</td>
                <td>{session.duration_seconds ? `${session.duration_seconds}s` : '-'}</td>
                <td>{session.notes || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default PracticeSessions;