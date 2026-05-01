import WaitlistPage from './components/waitlist/WaitlistPage.jsx'

const APP_URL = import.meta.env.VITE_APP_URL || '';

export default function App() {
  return <WaitlistPage appUrl={APP_URL} />
}
