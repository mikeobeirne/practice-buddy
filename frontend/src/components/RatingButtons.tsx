import React, { useEffect, useState } from 'react'

type Rating = 'easy' | 'medium' | 'hard' | 'snooze'

interface Props {
  onRate: (rating: Rating) => Promise<void>
}

interface SubmissionStatus {
  loading: boolean
  success: boolean
  error: string | null
  rating: Rating | null
}

const RatingButtons: React.FC<Props> = ({ onRate }) => {
  const [status, setStatus] = useState<SubmissionStatus>({
    loading: false,
    success: false,
    error: null,
    rating: null
  })

  // Reset success state after 2 seconds
  useEffect(() => {
    if (status.success) {
      const timer = setTimeout(() => {
        setStatus(prev => ({ ...prev, success: false, rating: null }))
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [status.success])

  const handleClick = async (rating: Rating) => {
    setStatus({ loading: true, success: false, error: null, rating })
    
    try {
      await onRate(rating)
      setStatus(prev => ({ ...prev, loading: false, success: true }))
    } catch (err) {
      setStatus(prev => ({ 
        ...prev, 
        loading: false, 
        error: err instanceof Error ? err.message : 'Failed to log practice'
      }))
    }
  }

  const getButtonStyle = (buttonRating: Rating) => ({
    opacity: status.loading && status.rating !== buttonRating ? 0.5 : 1,
    cursor: status.loading ? 'not-allowed' : 'pointer',
    position: 'relative' as const,
    minWidth: '80px',
    backgroundColor: status.success && status.rating === buttonRating ? '#4CAF50' : undefined,
    color: status.success && status.rating === buttonRating ? 'white' : undefined,
  })

  return (
    <div>
      <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
        {(['easy', 'medium', 'hard', 'snooze'] as Rating[]).map(rating => (
          <button
            key={rating}
            type="button"
            onClick={() => handleClick(rating)}
            disabled={status.loading}
            style={getButtonStyle(rating)}
          >
            {status.loading && status.rating === rating ? (
              <span>⌛</span>
            ) : (
              rating.charAt(0).toUpperCase() + rating.slice(1)
            )}
          </button>
        ))}
      </div>

      {status.error && (
        <div style={{ color: "darkred", marginTop: 8, textAlign: "center" }}>
          {status.error}
        </div>
      )}
    </div>
  )
}

export default RatingButtons