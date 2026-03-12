import { useState } from 'react'
import './App.css'

function App() {
  const [count, setCount] = useState(0)

  return (
    <>
      <pre>{`
    _
  _/ }
 `(/ )
 /`-'
/|\\`-
  |
  |
`}</pre>
      <div style={{ width: 100, height: 100, backgroundColor: 'red' }} />
      <h1>Vite + React</h1>
      <div className="card">
        <button onClick={() => setCount((count) => count + 1)}>
          COUNT IS {count}
        </button>
      </div>
    </>
  )
}

export default App
